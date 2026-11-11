#!/usr/bin/env python3
"""Probe mail daemons with disposable config/storage; never submit a message.

Production images and Git configuration are used with a temporary TLS identity,
fixture-only user and local auth backend. No production secrets or data mounts.
"""

from pathlib import Path
import imaplib
import base64
import socket
import ssl
import tempfile
import time
import yaml

from probe_commands import run_command

ROOT = Path(__file__).resolve().parents[2]
CAPS = [
    "CHOWN",
    "DAC_OVERRIDE",
    "FOWNER",
    "FSETID",
    "KILL",
    "SETGID",
    "SETUID",
    "NET_BIND_SERVICE",
    "SYS_CHROOT",
]


def run(args):
    """Run the probe command and fail when its expected execution does not succeed."""
    return run_command(args, check=True, capture_output=True, text=True, timeout=90).stdout.strip()


def command(name):
    """Read the deployed mail container image and command from its manifest."""
    doc = yaml.safe_load((ROOT / ("mail/deployment-" + name + ".yaml")).read_text())
    c = doc["spec"]["template"]["spec"]["containers"][0]
    caps = CAPS if name == "dovecot" else [cap for cap in CAPS if cap != "SYS_CHROOT"]
    if not c["securityContext"]["capabilities"] == {"drop": ["ALL"], "add": caps}:
        raise AssertionError
    if not c["securityContext"]["allowPrivilegeEscalation"] is False:
        raise AssertionError
    if not c["securityContext"]["readOnlyRootFilesystem"] is True:
        raise AssertionError
    args = ["podman", "run", "-d", "--cap-drop=ALL", "--security-opt=no-new-privileges"]
    if c["securityContext"]["readOnlyRootFilesystem"]:
        # Match Kubernetes: do not let Podman add implicit writable /tmp or /run.
        args += ["--read-only", "--read-only-tmpfs=false"]
    args += ["--cap-add=" + cap for cap in caps]
    return args, c


def bind(args, path, destination):
    """Add a read-only, SELinux-relabeled fixture bind mount to the container arguments."""
    args += ["-v", str(path) + ":" + destination + ":ro,Z"]


def port(cid, number):
    """Resolve the host port published for a fixture container TCP port."""
    return int(run(["podman", "port", cid, str(number) + "/tcp"]).split(":")[-1])


def retry(action):
    """Retry a transient connection or IMAP failure within a bounded attempt count."""
    for _ in range(20):
        try:
            return action()
        except (OSError, imaplib.IMAP4.error):
            time.sleep(1)
    return action()


def main():
    """Probe mail daemons with disposable config/storage; never submit a message."""
    containers, volumes = [], []
    with tempfile.TemporaryDirectory(prefix="mail-capability-") as directory:
        d = Path(directory)
        try:
            run(
                [
                    "openssl",
                    "req",
                    "-x509",
                    "-newkey",
                    "rsa:2048",
                    "-nodes",
                    "-days",
                    "1",
                    "-subj",
                    "/CN=guard.invalid",
                    "-addext",
                    "subjectAltName=IP:127.0.0.1",
                    "-keyout",
                    str(d / "tls.key"),
                    "-out",
                    str(d / "tls.crt"),
                ]
            )
            config = yaml.safe_load((ROOT / "mail/config-map-dovecot-cf.yaml").read_text())["data"]
            args, container = command("dovecot")
            args += [
                "-p",
                "127.0.0.1::993",
                "-p",
                "127.0.0.1::587",
                "--tmpfs",
                "/var/mail:rw,mode=0777",
                "--tmpfs",
                "/run/dovecot:rw,mode=0755",
                "--tmpfs",
                "/var/lib/dovecot:rw,mode=0755",
                "--tmpfs",
                "/tmp:rw,mode=0777,size=256m",
            ]
            mapping = {
                "config": "dovecot.conf",
                **{
                    key: "conf.d/" + key + ".conf"
                    for key in [
                        "10-auth",
                        "10-mail",
                        "10-master",
                        "10-ssl",
                        "15-lda",
                        "20-lmtp",
                        "20-managesieve",
                        "90-sieve",
                    ]
                },
                "mastodon-registration-bounces.sieve": (
                    "sieve-before/mastodon-registration-bounces.sieve"
                ),
            }
            for key, destination in mapping.items():
                p = d / key
                p.write_text(config[key])
                p.chmod(0o644)
                bind(args, p, "/etc/dovecot/" + destination)
            (d / "passwd").write_text("guard:{PLAIN}disposable-guard-password\n")
            (d / "passwd").chmod(0o644)
            bind(args, d / "passwd", "/etc/dovecot/passwd")
            for item in ["tls.key", "tls.crt"]:
                bind(args, d / item, "/etc/dovecot/ssl/" + item)
            entrypoint = container["command"]
            args += ["--entrypoint", entrypoint[0]]
            dovecot = run(args + [container["image"]] + entrypoint[1:] + container["args"])
            containers.append(dovecot)
            if not run(["podman", "exec", dovecot, "stat", "-c", "%a", "/tmp"]) == "1777":
                raise AssertionError
            context = ssl.create_default_context(cafile=str(d / "tls.crt"))

            def imap():
                client = imaplib.IMAP4_SSL(
                    "127.0.0.1", port(dovecot, 993), ssl_context=context, timeout=3
                )
                try:
                    if not client.login("guard", "disposable-guard-password")[0] == "OK":
                        raise AssertionError
                    if not client.select("INBOX", readonly=True)[0] == "OK":
                        raise AssertionError
                    if not client.noop()[0] == "OK":
                        raise AssertionError
                finally:
                    client.logout()

            retry(imap)
            print(
                "Dovecot: TLS, fixture authentication and read-only INBOX selection passed",
                flush=True,
            )

            config = yaml.safe_load((ROOT / "mail/config-map-main-cf.yaml").read_text())["data"]
            services = [
                line.split()
                for line in config["master"].splitlines()
                if line.strip() and not line.lstrip().startswith(("#", "-"))
            ]
            services = [
                row
                for row in services
                if len(row) >= 8 and row[1] in ["inet", "unix", "unix-dgram", "fifo", "pass"]
            ]
            if not (services and all((row[4] == "n" for row in services))):
                raise AssertionError("Review SYS_CHROOT if enabling Postfix chroot")
            args, container = command("postfix")
            args += ["--network=container:" + dovecot]
            # Named volumes are seeded from the image, like an initialized queue PVC.
            for destination in ["/var/spool/postfix", "/var/lib/postfix"]:
                volume = run(["podman", "volume", "create"])
                volumes.append(volume)
                args += ["-v", volume + ":" + destination]
            for key, destination in [
                ("config", "main.cf"),
                ("master", "master.cf"),
                ("access", "sender_access"),
                ("virtual", "virtual"),
            ]:
                value = config[key]
                if key == "config":
                    value = value.replace(
                        "dovecot-sasl.mail.svc.cluster.local:1234", "127.0.0.1:1234"
                    )
                    # No production dependency calls; only EHLO/STARTTLS/NOOP/QUIT.
                    value += "\nsmtpd_milters =\nnon_smtpd_milters =\n"
                p = d / ("postfix-" + key)
                p.write_text(value)
                p.chmod(0o644)
                bind(args, p, "/etc/postfix/" + destination)
            for item in ["tls.key", "tls.crt"]:
                bind(args, d / item, "/var/certs/" + item)
            args += [
                "--entrypoint",
                "/usr/bin/sh",
                container["image"],
                "-ec",
                "chown 100:102 /var/lib/postfix && chmod 755 /var/lib/postfix; "
                "exec dumb-init -- /etc/service/run",
            ]
            postfix = run(args)
            containers.append(postfix)

            def smtp():
                s = socket.create_connection(("127.0.0.1", port(dovecot, 587)), timeout=3)

                def response(stream, code):
                    while True:
                        line = stream.readline()
                        if not line[:3] == code:
                            raise AssertionError(line)
                        if line[3:4] == b" ":
                            return

                try:
                    s.sendall(b"PROXY TCP4 127.0.0.1 127.0.0.1 45678 587\r\n")
                    stream = s.makefile("rb")
                    response(stream, b"220")
                    s.sendall(b"EHLO guard.invalid\r\n")
                    response(stream, b"250")
                    s.sendall(b"STARTTLS\r\n")
                    response(stream, b"220")
                    stream.close()
                    s = context.wrap_socket(s, server_hostname="guard.invalid")
                    stream = s.makefile("rb")
                    s.sendall(b"EHLO guard.invalid\r\n")
                    response(stream, b"250")
                    credential = base64.b64encode(b"\0guard\0disposable-guard-password")
                    s.sendall(b"AUTH PLAIN " + credential + b"\r\n")
                    response(stream, b"235")
                    s.sendall(b"NOOP\r\n")
                    response(stream, b"250")
                    s.sendall(b"QUIT\r\n")
                    response(stream, b"221")
                    stream.close()
                finally:
                    s.close()

            retry(smtp)
            print(
                (
                    "Postfix: read-only root, PROXY protocol, "
                    "EHLO, STARTTLS, fixture AUTH and NOOP "
                    "passed; no mail submitted"
                ),
                flush=True,
            )
            for name, cid in [("dovecot", dovecot), ("postfix", postfix)]:
                status = run(["podman", "exec", cid, "cat", "/proc/1/status"])
                mask = "00000000000404fb" if name == "dovecot" else "00000000000004fb"
                for line in [
                    "CapEff:\t" + mask,
                    "CapBnd:\t" + mask,
                    "NoNewPrivs:\t1",
                    "Seccomp:\t2",
                ]:
                    if not line in status:
                        raise AssertionError(name + ": " + status)
                run(["podman", "exec", cid, name, "reload"])
            retry(imap)
            retry(smtp)
            print("Both daemons reloaded successfully; protocol checks passed again", flush=True)
        except Exception:
            for cid in containers:
                result = run_command(
                    ["podman", "logs", "--tail=25", cid],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                print((result.stdout + result.stderr)[-3000:])
            raise
        finally:
            for cid in reversed(containers):
                run(["podman", "rm", "-f", cid])
            for volume in volumes:
                run(["podman", "volume", "rm", volume])


if __name__ == "__main__":
    main()
