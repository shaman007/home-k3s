#!/usr/bin/env python3
"""Test exact deployed MySQL with disposable data, no network or production secrets."""

import subprocess
import time
import uuid
from pathlib import Path
import yaml

IMAGE = "harbor.andreybondarenko.com/dockerhub/mysql@sha256:257388edf9c84dbc04c763625446d5f3fa6ed60d1b0873bc552c614ba0a7ab4e"


def run(*args):
    p = subprocess.run(["podman", *args], capture_output=True, text=True, timeout=180, check=False)
    if p.returncode:
        raise RuntimeError(p.stderr[-2000:])
    return p.stdout.strip()


def main():
    patch = yaml.safe_load(Path(__file__).with_name("lenka-mysql-security.patch.yaml").read_text(encoding="utf-8"))
    sc = patch["spec"]["template"]["spec"]["containers"][0]["securityContext"]
    if not (sc["runAsUser"] == sc["runAsGroup"] == 999 and sc["runAsNonRoot"]):
        raise AssertionError
    if not sc["capabilities"] == {"drop": ["ALL"]}:
        raise AssertionError
    if not (not sc["allowPrivilegeEscalation"] and (not sc["privileged"])):
        raise AssertionError
    if not sc["seccompProfile"] == {"type": "RuntimeDefault"}:
        raise AssertionError
    volume = run("volume", "create", "lenka-mysql-guard-" + uuid.uuid4().hex)
    cid = None
    try:
        # Model current PVC root ownership without touching any production volume.
        run(
            "run",
            "--rm",
            "--network=none",
            "--cap-drop=ALL",
            "--cap-add=CHOWN",
            "-v",
            volume + ":/fixture",
            "--entrypoint=sh",
            IMAGE,
            "-ec",
            "chmod 755 /fixture; chown 999:0 /fixture",
        )
        cid = run(
            "run",
            "-d",
            "--network=none",
            "--user=999:999",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "-e",
            "MYSQL_ALLOW_EMPTY_PASSWORD=yes",
            "-v",
            volume + ":/var/lib/mysql:nocopy",
            IMAGE,
        )

        def sql(statement):
            return run(
                "exec", cid, "mysql", "-uroot", "--batch", "--skip-column-names", "-e", statement
            )

        def ready():
            for _ in range(120):
                try:
                    # Wait for final server, not the entrypoint's temporary init server.
                    if run("exec", cid, "cat", "/proc/1/comm") == "mysqld":
                        sql("SELECT 1")
                        return
                except RuntimeError:
                    pass
                time.sleep(1)
            raise RuntimeError("MySQL did not become ready; inspect disposable container")

        ready()
        sql(
            "CREATE DATABASE guard_fixture; CREATE TABLE guard_fixture.probe (id INT PRIMARY KEY); INSERT INTO guard_fixture.probe VALUES (42)"
        )
        if not sql("SELECT id FROM guard_fixture.probe") == "42":
            raise AssertionError
        status = run("exec", cid, "cat", "/proc/1/status")
        fields = dict(line.split(":", 1) for line in status.splitlines() if ":" in line)
        if not fields["Uid"].split() == ["999"] * 4:
            raise AssertionError
        if not fields["Gid"].split() == ["999"] * 4:
            raise AssertionError
        if not all((int(fields[k].strip(), 16) == 0 for k in ["CapEff", "CapPrm", "CapBnd"])):
            raise AssertionError
        if not (fields["NoNewPrivs"].strip() == "1" and fields["Seccomp"].strip() == "2"):
            raise AssertionError
        run("stop", "--time=45", cid)
        run("start", cid)
        ready()
        if not sql("SELECT id FROM guard_fixture.probe") == "42":
            raise AssertionError
        sql("UPDATE guard_fixture.probe SET id=43")
        if not sql("SELECT id FROM guard_fixture.probe") == "43":
            raise AssertionError
        print(
            "PASS: non-root initialization, SQL writes, graceful restart, persisted data, zero capabilities, NNP and default seccomp"
        )
    finally:
        if cid:
            run("rm", "-f", cid)
        run("volume", "rm", volume)


if __name__ == "__main__":
    main()
