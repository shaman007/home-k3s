#!/usr/bin/env python3
"""Rootless disposable SSH/rsync and Collabora startup probes; no production data."""

from pathlib import Path
import subprocess
import tempfile
import time
import urllib.request
import yaml

ROOT = Path(__file__).resolve().parents[2]


def run(args):
    """Run the probe command and fail when its expected execution does not succeed."""
    return subprocess.run(
        args, check=True, capture_output=True, text=True, timeout=120
    ).stdout.strip()


def main():
    """Rootless disposable SSH/rsync and Collabora startup probes; no production data."""
    backup = yaml.safe_load((ROOT / "backup-rsync/deployment-backup-rsync.yaml").read_text())
    c = backup["spec"]["template"]["spec"]["containers"][0]
    caps = c["securityContext"]["capabilities"]
    if not (caps["drop"] == ["ALL"] and c["securityContext"]["allowPrivilegeEscalation"] is False):
        raise AssertionError
    with tempfile.TemporaryDirectory(prefix="ssh-guard-") as directory:
        d = Path(directory)
        # Disposable test identity; private key stays in this mode-0700 directory
        # and is deleted on exit. Never read any production authorized keys.
        run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(d / "key")])
        keys = d / "keys"
        keys.mkdir()
        (keys / "backup").write_text((d / "key.pub").read_text())
        hook = yaml.safe_load(
            (ROOT / "backup-rsync/config-map-authorized-keys-setup.yaml").read_text()
        )["data"]["copy-backup-key"]
        (d / "hook").write_text(hook)
        (d / "hook").chmod(0o755)
        args = [
            "podman",
            "run",
            "-d",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "-p",
            "127.0.0.1::22",
            "-v",
            str(keys) + ":/mnt/authorized-keys:ro,Z",
            "-v",
            str(d / "hook") + ":/etc/entrypoint.d/10-copy-backup-key:ro,Z",
        ]
        for cap in caps["add"]:
            args += ["--cap-add=" + cap]
        for env in c["env"]:
            args += ["-e", env["name"] + "=" + env["value"]]
        cid = run(args + [c["image"]])
        try:
            port = run(["podman", "port", cid, "22/tcp"]).split(":")[-1]
            ssh = [
                "ssh",
                "-i",
                str(d / "key"),
                "-p",
                port,
                "-o",
                "StrictHostKeyChecking=no",
                "-o",
                "UserKnownHostsFile=/dev/null",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=2",
            ]
            src = d / "source"
            src.mkdir()
            (src / "sentinel").write_text("guard-test\n")
            (src / "link").symlink_to("sentinel")
            command = [
                "rsync",
                "-a",
                "-e",
                " ".join(ssh),
                str(src) + "/",
                "backup@127.0.0.1:guard-test/",
            ]
            last = None
            for _ in range(20):
                try:
                    run(command)
                    break
                except subprocess.CalledProcessError as error:
                    last = error
                    time.sleep(1)
            else:
                raise RuntimeError("SSH/rsync startup failed: " + last.stderr[-1000:])
            out = d / "download"
            out.mkdir()
            run(
                ["rsync", "-a", "-e", " ".join(ssh), "backup@127.0.0.1:guard-test/", str(out) + "/"]
            )
            if not (out / "sentinel").read_text() == "guard-test\n":
                raise AssertionError
            if not (out / "link").is_symlink():
                raise AssertionError
            status = run(["podman", "exec", cid, "cat", "/proc/1/status"])
            # Linux capability numbers: CHOWN, DAC_OVERRIDE, FOWNER, SETGID,
            # SETUID, NET_BIND_SERVICE, SYS_CHROOT.
            for line in [
                "CapEff:\t00000000000404cb",
                "CapBnd:\t00000000000404cb",
                "NoNewPrivs:\t1",
                "Seccomp:\t2",
            ]:
                if not line in status:
                    raise AssertionError(status)
            print(
                "Backup SSH: actual entrypoint/hook, key authentication and rsync round trip passed"
            )
        finally:
            run(["podman", "rm", "-f", cid])

    app = yaml.safe_load((ROOT / "argocd/application-collabora.yaml").read_text())
    values = yaml.safe_load(app["spec"]["source"]["helm"]["values"])
    sc = values["securityContext"]
    if not sc["runAsUser"] == sc["runAsGroup"] == 1001:
        raise AssertionError
    if not (sc["runAsNonRoot"] and sc["privileged"] is False):
        raise AssertionError
    if not sc["allowPrivilegeEscalation"] is True:
        raise AssertionError
    if not sc["capabilities"] == {"drop": ["ALL"], "add": ["CHOWN", "FOWNER", "SYS_CHROOT"]}:
        raise AssertionError
    image = values["image"]["repository"] + ":26.04.5.2.1"
    args = ["podman", "run", "-d", "--user=1001:1001", "--cap-drop=ALL", "-p", "127.0.0.1::9980"]
    for cap in sc["capabilities"]["add"]:
        args += ["--cap-add=" + cap]
    cid = run(args + [image, "--o:ssl.enable=false", "--o:ssl.termination=true"])
    try:
        port = run(["podman", "port", cid, "9980/tcp"]).split(":")[-1]
        for _ in range(60):
            try:
                with urllib.request.urlopen(
                    "http://127.0.0.1:" + port + "/hosting/discovery", timeout=2
                ) as response:
                    if not b"wopi-discovery" in response.read():
                        raise AssertionError
                break
            except (OSError, AssertionError):
                time.sleep(1)
        else:
            raise RuntimeError(
                "Collabora discovery failed: " + run(["podman", "logs", cid])[-2000:]
            )
        # Starting a spare document child exercises the file-capability jail setup.
        result = subprocess.run(
            ["podman", "logs", cid], check=True, capture_output=True, text=True, timeout=10
        )
        logs = result.stdout + result.stderr
        if not ("New child [" in logs and "jailId:" in logs):
            raise AssertionError("No document-jail child observed")
        print("Collabora: UID/GID 1001 startup, WOPI discovery and document-jail child passed")
    finally:
        run(["podman", "rm", "-f", cid])


if __name__ == "__main__":
    main()
