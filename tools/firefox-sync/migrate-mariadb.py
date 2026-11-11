#!/usr/bin/env python3
"""Prepare/verify a stopped Firefox Sync MySQL -> MariaDB logical migration.

Default: print the plan, without API calls. --import-data writes to the empty
candidate only; --verify compares all table values without printing records.
Neither mode scales workloads, changes Services, nor changes GitOps settings.
"""

import argparse
import hashlib
import json
import subprocess

NS = "firefox-sync"
SCHEMAS = ("syncstorage", "tokenserver")


def kubectl(*args):
    """Build a kubectl argument vector without executing it."""
    return ["kubectl", *args]


def resource(kind, name, namespace=NS):
    """Fetch one namespaced resource as JSON without exposing command diagnostics."""
    return json.loads(
        subprocess.check_output(
            kubectl("get", kind, name, "-n", namespace, "-o", "json"), stderr=subprocess.DEVNULL
        )
    )


def db_command(target, *args, dump=False):
    """Build an in-container database command that expands credentials only there."""
    deployment = "mariadb" if target else "mysql"
    container = deployment
    client = "mariadb" if target else "mysql"
    if dump:
        client = "mysqldump"
    password = "MARIADB_ROOT_PASSWORD" if target else "MYSQL_ROOT_PASSWORD"
    # Expand credentials inside the container only; never retrieve the Secret.
    shell = f'MYSQL_PWD="${password}" exec {client} --socket=/tmp/mysql.sock -uroot "$@"'
    return kubectl(
        "exec",
        "-i",
        "-n",
        NS,
        f"deployment/{deployment}",
        "-c",
        container,
        "--",
        "sh",
        "-c",
        shell,
        "db-client",
        *args,
    )


def query(target, sql):
    """Execute SQL through the selected database client and return output lines."""
    return (
        subprocess.check_output(
            db_command(target, "-NB", "-e", "SET time_zone='+00:00'; " + sql),
            stderr=subprocess.DEVNULL,
        )
        .decode()
        .splitlines()
    )


def quote(name):
    """Quote a SQL identifier by escaping embedded backticks."""
    return "`" + name.replace("`", "``") + "`"


def tables(target):
    """Return a consistently sorted inventory of base tables in the reviewed schemas."""
    rows = query(
        target,
        "SELECT TABLE_SCHEMA,TABLE_NAME FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA IN ('syncstorage','tokenserver') "
        "AND TABLE_TYPE='BASE TABLE' ORDER BY TABLE_SCHEMA,TABLE_NAME",
    )
    # INFORMATION_SCHEMA collations differ between engines (notably underscores
    # and digits). Compare metadata in Python's stable byte-compatible order.
    return sorted(tuple(row.split("\t")) for row in rows)


def check_frozen():
    """Reject active Sync or GitOps, unexpected storage, and unreviewed database versions."""
    app = resource("application", "firefox-sync", "argocd")
    automated = app["spec"].get("syncPolicy", {}).get("automated")
    if automated is not None and automated.get("enabled", True):
        raise RuntimeError("Pause Argo auto-sync before importing or comparing frozen data")
    if app.get("operation") or app.get("status", {}).get("operationState", {}).get("phase") in (
        "Running",
        "Terminating",
    ):
        raise RuntimeError("An Argo operation is still active")
    deployment = resource("deployment", "firefox-sync")
    if deployment["spec"].get("replicas", 1) != 0:
        raise RuntimeError("Stop Firefox Sync before importing or comparing frozen data")
    pods = json.loads(
        subprocess.check_output(
            kubectl("get", "pods", "-n", NS, "-l", "app=firefox-sync", "-o", "json"),
            stderr=subprocess.DEVNULL,
        )
    )
    if pods["items"]:
        raise RuntimeError(
            "Wait for all Firefox Sync pods, including terminating pods, to disappear"
        )
    service = resource("service", "mysql")
    if service["spec"]["selector"] != {"app": "mysql"}:
        raise RuntimeError("The production Service must still select the original MySQL")
    source = resource("deployment", "mysql")
    target = resource("deployment", "mariadb")

    def claims(deploy):
        return {
            v["persistentVolumeClaim"]["claimName"]
            for v in deploy["spec"]["template"]["spec"]["volumes"]
            if "persistentVolumeClaim" in v
        }

    if claims(source) != {"mysql-data"} or claims(target) != {"mariadb-data"}:
        raise RuntimeError("Unexpected source/target PVC; never reuse the MySQL datadir")
    if not query(False, "SELECT VERSION()")[0].startswith("8.4."):
        raise RuntimeError("Expected source MySQL 8.4")
    if not query(True, "SELECT VERSION()")[0].startswith("12.3.3-MariaDB"):
        raise RuntimeError("Expected candidate MariaDB 12.3.3")


def import_data():
    """Stream the reviewed schemas into an empty candidate without local dump files."""
    if tables(True):
        raise RuntimeError("Candidate already contains tables; refusing overwrite or partial retry")
    expected = tables(False)
    if not expected or {schema for schema, _ in expected} != set(SCHEMAS):
        raise RuntimeError("Both source schemas must contain tables")
    # No system tables, account dumps, local dump files or blind SQL replacements.
    args = (
        "--single-transaction",
        "--skip-lock-tables",
        "--no-tablespaces",
        "--set-gtid-purged=OFF",
        "--column-statistics=0",
        "--hex-blob",
        "--skip-add-drop-table",
        "--databases",
        *SCHEMAS,
    )
    with subprocess.Popen(
        db_command(False, *args, dump=True), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
    ) as source:
        try:
            with subprocess.Popen(
                db_command(True),
                stdin=source.stdout,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ) as target:
                source.stdout.close()
                target_status = target.wait()
        except BaseException:
            source.terminate()
            raise
        source_status = source.wait()
    if source_status or target_status:
        raise RuntimeError(
            "Import failed; keep Sync stopped. Candidate may be partial; do not retry over it"
        )


def validate_table(schema, table):
    """Limit metadata lookups to reviewed schemas and nonempty ASCII table identifiers."""
    if schema not in SCHEMAS:
        raise RuntimeError("Unexpected database schema")
    if (
        not isinstance(table, str)
        or not table
        or not all(c.isascii() and (c.isalnum() or c == "_") for c in table)
    ):
        raise RuntimeError("Unexpected table identifier")


def fingerprint(target, schema, table):
    # Hash values on the database side; transfer only row hashes, never payloads.
    """Return column names, row count, and an aggregate digest of server-side row hashes."""
    validate_table(schema, table)
    # B608: the schema is allowlisted and the table is a validated ASCII identifier.
    columns = query(
        target,
        "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
        f"WHERE TABLE_SCHEMA='{schema}' AND TABLE_NAME='{table}' "  # nosec B608
        "ORDER BY ORDINAL_POSITION",
    )
    fields = ",".join(
        f"IF({quote(c)} IS NULL,'N',CONCAT('V',HEX(CAST({quote(c)} AS BINARY))))" for c in columns
    )
    # B608: fields use fixed expressions and quote() escapes every column identifier.
    sql = (
        "SET time_zone='+00:00'; "
        f"SELECT SHA2(CONCAT_WS(':',{fields}),256) AS row_hash "  # nosec B608
        f"FROM {quote(schema)}.{quote(table)} ORDER BY BINARY row_hash"
    )
    digest = hashlib.sha256()
    count = 0
    with subprocess.Popen(
        db_command(target, "-NB", "-e", sql), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
    ) as process:
        for line in process.stdout:
            if len(line.strip()) != 64:
                raise RuntimeError("Invalid row fingerprint")
            digest.update(line)
            count += 1
        if process.wait():
            raise RuntimeError("Fingerprint query failed")
    return columns, count, digest.hexdigest()


def verify():
    """Compare both databases and reject differing table inventories or value fingerprints."""
    source_tables, target_tables = tables(False), tables(True)
    if not source_tables or source_tables != target_tables:
        raise RuntimeError("Source/candidate table inventories differ")
    for schema, table in source_tables:
        validate_table(schema, table)
        source = fingerprint(False, schema, table)
        if source != fingerprint(True, schema, table):
            raise RuntimeError(f"Data mismatch: {schema}.{table}; keep Sync stopped")
        print(f"{schema}.{table}: {source[1]} rows, value fingerprints match")


def main():
    """Print a no-operation plan or execute the selected guarded migration phase."""
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--import-data", action="store_true", help="WRITE to an empty candidate, then verify"
    )
    mode.add_argument(
        "--verify", action="store_true", help="Read-only comparison while Sync is stopped"
    )
    args = parser.parse_args()
    if not (args.import_data or args.verify):
        print(
            "Plan: pause Argo, start isolated MariaDB on mariadb-data, stop Sync, "
            "take a recoverable backup, stream both schemas, compare all row values, "
            "test Sync against MariaDB, then promote the Service through GitOps. "
            "See docs/migrations/firefox-sync-mariadb/README.md. No API calls made."
        )
        return
    check_frozen()
    if args.import_data:
        import_data()
    verify()
    print("Data comparison passed. Runtime Sync/Firefox verification is still required.")


if __name__ == "__main__":
    try:
        main()
    except subprocess.SubprocessError:
        raise SystemExit(
            (
                "Database/Kubernetes command failed; "
                "details suppressed to protect data. Keep "
                "Sync stopped."
            )
        ) from None
    except RuntimeError as error:
        raise SystemExit(str(error)) from None
