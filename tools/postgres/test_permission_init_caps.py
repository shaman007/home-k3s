#!/usr/bin/env python3
"""Run the exact permission-init commands on disposable tmpfs data.

No Kubernetes access, production credentials, host data mounts or real databases
are used. Requires Podman and the pinned BusyBox mirror image.
"""

import argparse
from pathlib import Path
import subprocess
import yaml

ROOT = Path(__file__).resolve().parents[2]
APPLICATIONS = ["immich", "keycloak", "dawarich", "mastodon", "bitwarden"]
IMAGE = "harbor.andreybondarenko.com/dockerhub/busybox:1.38"


def main():
    """Run the exact permission-init commands on disposable tmpfs data."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--image",
        default=IMAGE,
        help="Image/digest to execute; manifest declarations are checked separately",
    )
    args = parser.parse_args()
    for name in APPLICATIONS:
        manifest = yaml.safe_load((ROOT / name / f"stateful-set-{name}-postgres.yaml").read_text())
        gid = manifest["spec"]["template"]["spec"]["securityContext"]["runAsGroup"]
        if not gid == 999:
            raise AssertionError
        init = next(
            c
            for c in manifest["spec"]["template"]["spec"]["initContainers"]
            if c["name"] == "volume-permissions"
        )
        if not init["image"] == IMAGE:
            raise AssertionError
        if not init["securityContext"]["runAsUser"] == 0:
            raise AssertionError
        if not init["securityContext"]["allowPrivilegeEscalation"] is False:
            raise AssertionError
        if not init["securityContext"]["capabilities"] == {
            "drop": ["ALL"],
            "add": ["CHOWN", "DAC_OVERRIDE"],
        }:
            raise AssertionError
        if not (
            init["command"][:2] == ["sh", "-c"]
            and len(init["command"]) == 3
            and (not init.get("args"))
        ):
            raise AssertionError
        if not [(m["name"], m["mountPath"], m.get("subPath")) for m in init["volumeMounts"]] == [
            ("data", "/var/lib/postgresql/data", "data")
        ]:
            raise AssertionError
        # Seed restrictive, already-owned data, including a nonempty directory.
        # The tested script must traverse it and preserve contents and modes.
        setup = (
            "set -eu\nmkdir -p "
            "/var/lib/postgresql/data/base/nested "
            "/var/lib/postgresql/data/shared\nprintf "
            "'16\\n' > /var/lib/postgresql/data/PG_VER"
            "SION\nprintf 'existing-data-sentinel\\n' > "
            "/var/lib/postgresql/data/base/nested/sen"
            "tinel\nchmod 700 /var/lib/postgresql/data "
            "/var/lib/postgresql/data/base "
            "/var/lib/postgresql/data/base/nested\nchm"
            "od 600 /var/lib/postgresql/data/PG_VERSI"
            "ON /var/lib/postgresql/data/base/nested/"
            "sentinel\nchmod 2770 "
            "/var/lib/postgresql/data/shared\nchown -R "
            "999:999 /var/lib/postgresql/data\n"
        )
        verify = """
test "$(cat /var/lib/postgresql/data/PG_VERSION)" = 16
test "$(cat /var/lib/postgresql/data/base/nested/sentinel)" = existing-data-sentinel
test "$(stat -c '%u:%g:%a' /var/lib/postgresql/data)" = 999:999:700
test "$(stat -c '%u:%g:%a' /var/lib/postgresql/data/base/nested)" = 999:999:700
test "$(stat -c '%u:%g:%a' /var/lib/postgresql/data/base/nested/sentinel)" = 999:999:600
test "$(stat -c '%u:%g:%a' /var/lib/postgresql/data/shared)" = 999:999:2770
test "$(stat -c '%u:%g' /var/run/postgresql)" = 999:999
grep -E '^(CapEff|CapBnd|NoNewPrivs|Seccomp):' /proc/self/status
"""
        command = [
            "podman",
            "run",
            "--rm",
            "--network=none",
            "--user",
            f"0:{gid}",
            "--group-add=999",
            "--cap-drop=ALL",
            "--cap-add=CHOWN",
            "--cap-add=DAC_OVERRIDE",
            "--security-opt=no-new-privileges",
            "--tmpfs",
            "/var/lib/postgresql/data:rw,mode=0700",
            args.image,
            "sh",
            "-c",
            setup + init["command"][2] + verify,
        ]
        result = subprocess.run(command, text=True, capture_output=True, timeout=30, check=False)
        if not result.returncode == 0:
            raise AssertionError(name + ": " + result.stdout + result.stderr)
        for expected in [
            "CapEff:\t0000000000000003",
            "CapBnd:\t0000000000000003",
            "NoNewPrivs:\t1",
            "Seccomp:\t2",
        ]:
            if not expected in result.stdout:
                raise AssertionError((name, result.stdout))
        print(
            (
                f"{name}"
                f": exact init succeeded with "
                f"CHOWN/DAC_OVERRIDE only; contents, "
                f"ownership and modes preserved"
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
