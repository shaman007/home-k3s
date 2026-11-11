"""Verify guarded Firefox Sync database migration and data-comparison behavior."""

import importlib.util
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

import yaml

ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location(
    "migrate_mariadb", ROOT / "tools/firefox-sync/migrate-mariadb.py"
)
migration = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(migration)


class MigrationTests(unittest.TestCase):
    """Require frozen data, empty candidates, and matching values for database migration."""

    def test_invalid_metadata_is_rejected_before_database_commands(self):
        """Reject injected, empty, foreign, or non-ASCII names at the SQL boundary."""
        cases = [
            ("mysql", "bso"),
            ("syncstorage' OR 1=1 --", "bso"),
            ("syncstorage", "bso' OR 1=1 --"),
            ("syncstorage", "bso; DROP TABLE bso"),
            ("syncstorage", ""),
            ("syncstorage", "bѕo"),
            ("syncstorage", None),
        ]
        for schema, table in cases:
            with (
                self.subTest(schema=schema, table=table),
                patch.object(migration, "query") as query,
                patch.object(migration.subprocess, "Popen") as process,
            ):
                with self.assertRaisesRegex(RuntimeError, "Unexpected"):
                    migration.fingerprint(False, schema, table)
                query.assert_not_called()
                process.assert_not_called()

    def test_reviewed_schema_and_ascii_table_names_are_accepted(self):
        """Keep both application schemas and underscore/digit table names supported."""
        for schema in migration.SCHEMAS:
            for table in ("bso", "__diesel_schema_migrations", "batch_upload_items2"):
                with self.subTest(schema=schema, table=table):
                    migration.validate_table(schema, table)

    def test_valid_fingerprint_uses_scoped_metadata_and_quoted_columns(self):
        """Keep valid fingerprint queries working and unusual column names quoted."""
        process = MagicMock()
        process.__enter__.return_value = process
        process.stdout = [b"a" * 64 + b"\n"]
        process.wait.return_value = 0
        with (
            patch.object(migration, "query", return_value=["value`column"]) as query,
            patch.object(migration.subprocess, "Popen", return_value=process) as execute,
        ):
            columns, count, digest = migration.fingerprint(False, "syncstorage", "bso")
        self.assertEqual(columns, ["value`column"])
        self.assertEqual(count, 1)
        self.assertEqual(len(digest), 64)
        metadata_query = query.call_args.args[1]
        self.assertIn("TABLE_SCHEMA='syncstorage' AND TABLE_NAME='bso'", metadata_query)
        sql = execute.call_args.args[0][-1]
        self.assertIn("`value``column`", sql)
        self.assertIn("FROM `syncstorage`.`bso`", sql)

    def test_metadata_order_is_independent_of_database_collation(self):
        """Compare table metadata in a stable order across database collations."""
        with patch.object(
            migration,
            "query",
            side_effect=[
                [
                    "syncstorage\t__diesel_schema_migrations",
                    "syncstorage\tbatch_upload_items",
                    "syncstorage\tbatch_uploads",
                ],
                [
                    "syncstorage\tbatch_uploads",
                    "syncstorage\tbatch_upload_items",
                    "syncstorage\t__diesel_schema_migrations",
                ],
            ],
        ):
            self.assertEqual(migration.tables(False), migration.tables(True))

    def test_default_plan_does_not_access_cluster(self):
        """Keep the default invocation free of cluster access."""
        with patch("sys.argv", ["migrate"]), patch.object(migration, "check_frozen") as check:
            migration.main()
        check.assert_not_called()

    def test_populated_candidate_is_never_overwritten(self):
        """Reject a populated candidate before starting any import process."""
        with (
            patch.object(migration, "tables", return_value=[("syncstorage", "bso")]),
            patch.object(migration.subprocess, "Popen") as process,
        ):
            with self.assertRaisesRegex(RuntimeError, "refusing overwrite"):
                migration.import_data()
        process.assert_not_called()

    def test_either_pipeline_failure_blocks_acceptance(self):
        """Reject an import when either the source or target process fails."""
        for source_status, target_status in [(1, 0), (0, 1)]:
            with self.subTest(source=source_status, target=target_status):
                source, target = MagicMock(), MagicMock()
                source.__enter__.return_value = source
                target.__enter__.return_value = target
                source.wait.return_value = source_status
                target.wait.return_value = target_status
                with (
                    patch.object(
                        migration,
                        "tables",
                        side_effect=[[], [("syncstorage", "bso"), ("tokenserver", "nodes")]],
                    ),
                    patch.object(migration.subprocess, "Popen", side_effect=[source, target]),
                ):
                    with self.assertRaisesRegex(RuntimeError, "Import failed"):
                        migration.import_data()

    def test_import_dump_is_limited_to_app_databases(self):
        """Limit dump arguments to application schemas and preserve source safety flags."""
        source, target = MagicMock(), MagicMock()
        source.__enter__.return_value = source
        target.__enter__.return_value = target
        source.wait.return_value = target.wait.return_value = 0
        with (
            patch.object(
                migration,
                "tables",
                side_effect=[[], [("syncstorage", "bso"), ("tokenserver", "nodes")]],
            ),
            patch.object(migration.subprocess, "Popen", side_effect=[source, target]) as process,
        ):
            migration.import_data()
        command = process.call_args_list[0].args[0]
        self.assertEqual(command[-3:], ["--databases", "syncstorage", "tokenserver"])
        self.assertIn("--set-gtid-purged=OFF", command)
        self.assertIn("--no-tablespaces", command)

    def test_active_gitops_blocks_import(self):
        """Reject migration work while automatic GitOps synchronization is enabled."""
        app = {"spec": {"syncPolicy": {"automated": {}}}}
        with patch.object(migration, "resource", return_value=app):
            with self.assertRaisesRegex(RuntimeError, "Pause Argo"):
                migration.check_frozen()

    def test_running_sync_blocks_import(self):
        """Require the Sync deployment to be stopped before migration work."""
        with patch.object(
            migration, "resource", side_effect=[{"spec": {}}, {"spec": {"replicas": 1}}]
        ):
            with self.assertRaisesRegex(RuntimeError, "Stop Firefox Sync"):
                migration.check_frozen()

    def test_terminating_pods_block_import(self):
        """Wait for terminating Sync pods to disappear before accepting a frozen state."""
        with (
            patch.object(
                migration, "resource", side_effect=[{"spec": {}}, {"spec": {"replicas": 0}}]
            ),
            patch.object(
                migration.subprocess,
                "check_output",
                return_value=b'{"items":[{"metadata":{"deletionTimestamp":"now"}}]}',
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "terminating"):
                migration.check_frozen()

    def test_value_mismatch_blocks_acceptance(self):
        """Reject differing row fingerprints instead of accepting a partial migration."""
        with (
            patch.object(migration, "tables", return_value=[("syncstorage", "bso")]),
            patch.object(
                migration, "fingerprint", side_effect=[(["id"], 1, "a"), (["id"], 1, "b")]
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "Data mismatch"):
                migration.verify()

    def test_different_table_inventory_blocks_acceptance(self):
        """Reject differing source and candidate table inventories."""
        with patch.object(
            migration, "tables", side_effect=[[("syncstorage", "bso")], [("tokenserver", "nodes")]]
        ):
            with self.assertRaisesRegex(RuntimeError, "inventories differ"):
                migration.verify()

    def test_credentials_expand_only_inside_container(self):
        """Keep database password expansion inside the selected database container."""
        cmd = migration.db_command(True, "-NB", "-e", "SELECT 1")
        self.assertIn(
            'MYSQL_PWD="$MARIADB_ROOT_PASSWORD"', cmd[cmd.index("-c", cmd.index("--")) + 1]
        )
        self.assertNotIn("secret", cmd)
        self.assertIn("--socket=/tmp/mysql.sock", " ".join(cmd))

    def test_candidate_never_mounts_source_volume_or_matches_production_service(self):
        """Keep candidate storage and service identity separate from production."""
        base = ROOT / "docs/migrations/firefox-sync-mariadb"
        pvc, deployment = list(yaml.safe_load_all((base / "candidate.yaml").read_text()))
        self.assertEqual(pvc["metadata"]["name"], "mariadb-data")
        pod = deployment["spec"]["template"]
        self.assertEqual(pod["metadata"]["labels"], {"app": "mariadb"})
        self.assertEqual(
            pod["spec"]["volumes"][0]["persistentVolumeClaim"]["claimName"], "mariadb-data"
        )
        container = pod["spec"]["containers"][0]
        self.assertFalse(any("mysqlx" in arg for arg in container["args"]))
        self.assertIn("@sha256:", container["image"])
        fresh_pvc, fresh_db, service, rehearsal, _, _ = list(
            yaml.safe_load_all((base / "rehearsal.yaml").read_text())
        )
        self.assertEqual(fresh_pvc["metadata"]["name"], "mariadb-rehearsal-data")
        self.assertEqual(
            fresh_db["spec"]["template"]["spec"]["volumes"][0]["persistentVolumeClaim"][
                "claimName"
            ],
            "mariadb-rehearsal-data",
        )
        self.assertEqual(service["spec"]["selector"], {"app": "mariadb-rehearsal"})
        self.assertEqual(
            rehearsal["spec"]["template"]["metadata"]["labels"],
            {"app": "firefox-sync-mariadb-check"},
        )
        env = rehearsal["spec"]["template"]["spec"]["containers"][0]["env"]
        urls = [e["value"] for e in env if e["name"].endswith("__DATABASE_URL")]
        self.assertEqual(len(urls), 2)
        self.assertTrue(all("@mariadb-rehearsal:3306/" in url for url in urls))


if __name__ == "__main__":
    unittest.main()
