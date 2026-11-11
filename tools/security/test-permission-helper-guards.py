#!/usr/bin/env python3
"""Test permission helpers on disposable tmpfs; optionally smoke-test installers.

No production data, credentials, services or Kubernetes objects are used.
--installers downloads public packages but does not run media-fetch/upload jobs.
"""

import argparse
from pathlib import Path
import subprocess
import yaml

ROOT = Path(__file__).resolve().parents[2]


def run(command, label, timeout=60):
    result = subprocess.run(command, text=True, capture_output=True, timeout=timeout, check=False)
    if not result.returncode == 0:
        raise AssertionError(label + ": " + result.stdout[-2000:] + result.stderr[-2000:])
    return result.stdout


def helper(path, name, caps, mount, setup, checks, expected_mask):
    doc = yaml.safe_load((ROOT / path).read_text())
    container = next(
        c for c in doc["spec"]["template"]["spec"]["initContainers"] if c["name"] == name
    )
    sc = container["securityContext"]
    if not (sc["readOnlyRootFilesystem"] and sc["allowPrivilegeEscalation"] is False):
        raise AssertionError
    if not sc["capabilities"] == {"drop": ["ALL"], "add": caps}:
        raise AssertionError
    command = [
        "podman",
        "run",
        "--rm",
        "--network=none",
        "--read-only",
        "--user",
        "0:0",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--tmpfs",
        mount + ":rw,mode=0700",
    ]
    command.extend("--cap-add=" + cap for cap in caps)
    # Kubernetes command replaces the image's entrypoint (important for Postfix).
    command += [
        "--entrypoint",
        container["command"][0],
        container["image"],
        container["command"][1],
        setup + "\n" + container["command"][-1] + "\n" + checks + "\n"
        'grep -E "^(CapEff|CapBnd|NoNewPrivs|Seccomp):" /proc/self/status',
    ]
    output = run(command, path)
    for expected in [
        "CapEff:\t" + expected_mask,
        "CapBnd:\t" + expected_mask,
        "NoNewPrivs:\t1",
        "Seccomp:\t2",
    ]:
        if not expected in output:
            raise AssertionError((path, output))
    print(
        path
        + ": exact helper passed; reduced caps, read-only root, contents/ownership/modes verified",
        flush=True,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installers", action="store_true")
    args = parser.parse_args()
    setup = """set -eu
mkdir -p /data/closed/nested
printf 'sentinel\\n' > /data/closed/nested/file
chmod 700 /data/closed /data/closed/nested
chmod 600 /data/closed/nested/file
chown -R 999:999 /data
"""
    checks = """test "$(cat /data/closed/nested/file)" = sentinel
test "$(stat -c '%u:%g:%a' /data/closed/nested/file)" = 65532:65532:600
test "$(stat -c '%u:%g:%a' /data/closed/nested)" = 65532:65532:700
"""
    for path in ["hister/deployment-hister.yaml", "hister/tools/job-hister-reindex.yaml"]:
        helper(
            path,
            "fix-data-permissions",
            ["CHOWN", "DAC_OVERRIDE"],
            "/data",
            setup,
            checks,
            "0000000000000003",
        )
    helper(
        "mail/deployment-postfix.yaml",
        "init-postfix-queue-perms",
        ["CHOWN", "FOWNER"],
        "/var/lib/postfix",
        "set -eu; chmod 700 /var/lib/postfix",
        "test \"$(stat -c '%u:%g:%a' /var/lib/postfix)\" = 100:102:755",
        "0000000000000009",
    )
    if not args.installers:
        return
    job = yaml.safe_load((ROOT / "mastodon/cron-job-bookmarked-media-sync.yaml").read_text())
    pod = job["spec"]["jobTemplate"]["spec"]["template"]["spec"]
    tests = [
        (
            pod["initContainers"][0],
            ["apk add --no-cache ca-certificates coreutils curl jq kubectl"],
            (
                "kubectl version --client >/dev/null; "
                "curl --version >/dev/null; jq --version "
                ">/dev/null"
            ),
        ),
        (
            pod["containers"][0],
            [
                "npm install -g @immich/cli@3.0.2",
                "apk add --no-cache ca-certificates coreutils curl jq",
            ],
            "immich --version",
        ),
    ]
    for container, installers, smoke in tests:
        if not container["securityContext"]["capabilities"] == {"drop": ["ALL"]}:
            raise AssertionError
        if not container["securityContext"]["allowPrivilegeEscalation"] is False:
            raise AssertionError
        for installer in installers:
            if not installer in [line.strip() for line in container["command"][-1].splitlines()]:
                raise AssertionError
        # Never execute login, fetch, upload, description updates or job API calls.
        script = (
            "set -eu\n"
            + "\n".join(installers)
            + "\n"
            + smoke
            + '\ngrep -E "^(CapEff|CapBnd|NoNewPrivs|Seccomp):" /proc/self/status'
        )
        command = [
            "podman",
            "run",
            "--rm",
            "--user",
            "0:0",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--entrypoint",
            container["command"][0],
            container["image"],
            container["command"][1],
            script,
        ]
        output = run(command, container["name"], timeout=300)
        for expected in [
            "CapEff:\t0000000000000000",
            "CapBnd:\t0000000000000000",
            "NoNewPrivs:\t1",
            "Seccomp:\t2",
        ]:
            if not expected in output:
                raise AssertionError(output)
        print(
            container["name"] + ": exact installer/client smoke test passed with zero capabilities",
            flush=True,
        )


if __name__ == "__main__":
    main()
