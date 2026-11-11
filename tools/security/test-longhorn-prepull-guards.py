#!/usr/bin/env python3
"""Run only the prepull echo/sleep command, never the share-manager server."""

import json
from pathlib import Path
import subprocess
import time


def run(*args):
    p = subprocess.run(["podman", *args], text=True, capture_output=True, timeout=90)
    if not (p.returncode == 0):
        raise AssertionError(p.stderr[-2000:])
    return p.stdout.strip()


def main():
    root = Path(__file__).resolve().parents[2]
    entry = next(
        e
        for e in json.loads((root / "longhorn/component-security-catalog.json").read_text())[
            "entries"
        ]
        if e["name"] == "longhorn-manager"
    )
    if not (entry["container"] == "pre-pull-share-manager-image"):
        raise AssertionError
    if not (entry["command"] == ["sh", "-c", "echo share-manager image pulled && sleep infinity"]):
        raise AssertionError
    image = "harbor.andreybondarenko.com/dockerhub/longhornio/longhorn-share-manager@sha256:53950f78b7af38b8a943c298cd3020622191a4661a13036f69d83c154cc8690d"
    cid = run(
        "run",
        "-d",
        "--network=none",
        "--user=65534:65534",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--entrypoint=sh",
        image,
        *entry["command"][1:],
    )
    try:
        time.sleep(2)
        if not (run("inspect", "--format={{.State.Running}}", cid) == "true"):
            raise AssertionError
        if not ("share-manager image pulled" in run("logs", cid)):
            raise AssertionError
        status = run("exec", cid, "cat", "/proc/1/status")
        fields = dict(line.split(":", 1) for line in status.splitlines() if ":" in line)
        if not (fields["Uid"].split() == ["65534"] * 4):
            raise AssertionError
        if not (fields["Gid"].split() == ["65534"] * 4):
            raise AssertionError
        if not (all(int(fields[k].strip(), 16) == 0 for k in ["CapEff", "CapPrm", "CapBnd"])):
            raise AssertionError
        if not (fields["NoNewPrivs"].strip() == "1" and fields["Seccomp"].strip() == "2"):
            raise AssertionError
        print(
            "PASS: exact deployed image and echo/sleep command, UID/GID 65534, zero capabilities, NNP, default seccomp"
        )
    finally:
        run("rm", "-f", cid)


if __name__ == "__main__":
    main()
