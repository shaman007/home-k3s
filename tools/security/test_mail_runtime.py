#!/usr/bin/env python3
"""Real SMTP/AUTH/IMAP and antivirus fault matrix in disposable local containers.

Uses production images/config, fixture credentials/TLS, empty volumes and a tiny
public EICAR test signature database. Never mounts production data or Secrets.
"""

import base64
import imaplib
import json
import re
import shutil
import socket
import ssl
import tempfile
import time
import uuid
from email.message import EmailMessage
from pathlib import Path

import test_mail_capability_guards as guards
import yaml
from probe_commands import run_command

ROOT = Path(__file__).resolve().parents[2]


def native(args, **options):
    """Bounded trusted CLI execution, capturing fixture-only output."""
    return run_command(args, timeout=120, capture_output=True, text=True, **options)


def image(path, container=None):
    """Select the exact declared application image."""
    doc = yaml.safe_load((ROOT / path).read_text())
    items = doc["spec"]["template"]["spec"]["containers"]
    return next(
        c["image"] for c in items if container is None or c["name"] == container
    )


def launch(dovecot, ref, args):
    """All extra services share the disposable loopback-only fixture namespace."""
    return guards.run(
        [
            "podman",
            "run",
            "-d",
            "--network=container:" + dovecot,
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            *args,
            ref,
        ]
    )


def tcp_ready(port):
    """Wait only for the local forwarded fixture SMTP listener."""
    with socket.create_connection(("127.0.0.1", port), timeout=2):
        return True


def prepare_rspamd(d):
    """Use Git policy with local-only backends and synthetic signing material."""
    doc = yaml.safe_load((ROOT / "mail/deployment-rspamd.yaml").read_text())
    pod = doc["spec"]["template"]["spec"]
    data = yaml.safe_load((ROOT / "mail/config-map-rspamd-cf.yaml").read_text())["data"]
    args = [
        "--user=11333:11333",
        "--tmpfs",
        "/var/lib/rspamd:rw,mode=0777",
        "--tmpfs",
        "/var/log:rw,mode=0777",
        "--tmpfs",
        "/run/rspamd:rw,mode=0777",
    ]
    maps = {
        v["name"]: v
        for v in pod["volumes"]
        if v.get("configMap", {}).get("name") == "rspamd-cf"
    }
    for mount in pod["containers"][0]["volumeMounts"]:
        if mount["name"] not in maps:
            continue
        item = maps[mount["name"]]["configMap"]["items"][0]
        content = data[item["key"]].replace(
            "valkey.mail.svc.cluster.local:6379", "127.0.0.1:6379"
        )
        content = content.replace(
            "clamav.clamav.svc.cluster.local:3200", "127.0.0.1:3200"
        )
        content = content.replace('"10.43.0.53"', '"127.0.0.1"').replace(
            "andreybondarenko.com", "guard.invalid"
        )
        path = d / ("rspamd-" + item["key"])
        path.write_text(content)
        path.chmod(0o644)
        guards.bind(args, path, mount["mountPath"])
    controller = d / "controller"
    controller.write_text('bind_socket = "*:11334";\nsecure_ip = "127.0.0.1";\n')
    controller.chmod(0o644)
    guards.bind(args, controller, "/etc/rspamd/local.d/worker-controller.inc")
    keydir = d / "dkim"
    keydir.mkdir()
    keydir.chmod(0o755)
    key = keydir / "guard.invalid.key"
    shutil.copyfile(d / "tls.key", key)
    key.chmod(0o444)
    guards.bind(args, keydir, "/var/lib/rspamd/dkim")
    return args


def imap_contains(dovecot, ca, message_id):
    """Search only the synthetic fixture message, using real IMAP authentication."""
    client = imaplib.IMAP4_SSL(
        "127.0.0.1",
        guards.port(dovecot, 993),
        ssl_context=ssl.create_default_context(cafile=str(ca)),
        timeout=5,
    )
    try:
        assert client.login("guard", "disposable-guard-password")[0] == "OK"
        assert client.select("INBOX", readonly=True)[0] == "OK"
        status, ids = client.search(None, "HEADER", "Message-ID", message_id)
        return status == "OK" and bool(ids[0])
    finally:
        client.logout()


def transaction(d, dovecot, case, expected, virus=False):
    """Send only to guard.invalid via swaks; never expose AUTH payload or password."""
    token = uuid.uuid4().hex
    mid = f"<{case}-{token}@guard.invalid>"
    message = EmailMessage()
    message["From"] = "guard@guard.invalid"
    message["To"] = "guard@guard.invalid"
    message["Subject"] = "Isolated mail verification " + case
    message["Message-ID"] = mid
    message.set_content("Synthetic isolated mail test. Unique token: " + token + "\n")
    if not virus:
        message.add_attachment(
            ("Synthetic attachment " + token).encode(),
            maintype="application",
            subtype="octet-stream",
            filename="fixture.txt",
        )
    if virus:
        # Harmless standard EICAR string, decoded only into a disposable fixture message.
        payload = base64.b64decode(
            "WDVPIVAlQEFQWzRcUFpYNTQoUF4pN0NDKTd9JEVJQ0FSLVNUQU5EQVJELUFO"
            "VElWSVJVUy1URVNULUZJTEUhJEgrSCo="
        )
        message.add_attachment(
            payload,
            maintype="application",
            subtype="octet-stream",
            filename="eicar-test.txt",
        )
    path = d / (case + ".eml")
    path.write_bytes(message.as_bytes())
    result = native(
        [
            "swaks",
            "--server",
            "127.0.0.1",
            "--port",
            str(guards.port(dovecot, 587)),
            "--proxy",
            "TCP4 127.0.0.1 127.0.0.1 45678 587",
            "--tls",
            "--tls-verify",
            "--tls-ca-path",
            str(d / "tls.crt"),
            "--tls-verify-target",
            "127.0.0.1",
            "--auth",
            "PLAIN",
            "--auth-user",
            "guard",
            "--auth-password",
            "disposable-guard-password",
            "--auth-hide-password",
            "--hide-send",
            "--helo",
            "guard.invalid",
            "--from",
            "guard@guard.invalid",
            "--to",
            "guard@guard.invalid",
            "--data",
            "@" + str(path),
            "--timeout",
            "45",
        ],
        check=False,
    )
    output = result.stdout + result.stderr
    failures = re.findall(r"^<[^\n]*?\*\s+(\d{3})\s+([^\n]*)", output, re.MULTILINE)
    accepted = bool(re.search(r"250 2\.0\.0 .*queued as", output))
    if expected == "accepted":
        assert result.returncode == 0 and accepted, (
            case,
            result.returncode,
            [c for c, _ in failures],
        )
        guards.retry(
            lambda: (
                imap_contains(dovecot, d / "tls.crt", mid)
                or (_ for _ in ()).throw(OSError("not delivered"))
            )
        )
    elif expected == "temporary":
        assert not accepted and failures and failures[-1][0].startswith("4"), (
            case,
            result.returncode,
            [c for c, _ in failures],
        )
        assert not imap_contains(dovecot, d / "tls.crt", mid)
    else:
        assert not accepted and failures and failures[-1][0].startswith("5"), (
            case,
            result.returncode,
            [c for c, _ in failures],
        )
        assert "virus" in failures[-1][1].lower(), (
            "rejection was not the antivirus action"
        )
        assert not imap_contains(dovecot, d / "tls.crt", mid)
    print(
        json.dumps(
            {
                "case": case,
                "expected": expected,
                "smtp_accepted": accepted,
                "failure_codes": [c for c, _ in failures],
                "verified": True,
            }
        ),
        flush=True,
    )


def start_unbound(d, dovecot):
    """Provide local fixture DNS using the production resolver configuration."""
    cfg = yaml.safe_load((ROOT / "mail/config-map-unbound.yaml").read_text())["data"][
        "unbound.conf"
    ]
    # Local fixture domain answers; retain the resolver behavior for other checks.
    cfg = cfg.replace(
        "server:\n",
        "server:\n"
        '  local-zone: "guard.invalid." static\n'
        '  local-data: "guard.invalid. 60 IN A 127.0.0.1"\n'
        "  local-data: 'guard.invalid. 60 IN TXT \"v=spf1 ip4:127.0.0.1 -all\"'\n"
        "  local-data: '_dmarc.guard.invalid. 60 IN TXT \"v=DMARC1; p=none\"'\n",
        1,
    )
    conf = d / "unbound.conf"
    conf.write_text(cfg)
    conf.chmod(0o644)
    args = [
        "--cap-add=NET_BIND_SERVICE",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,mode=1777",
        "--entrypoint",
        "/opt/unbound/sbin/unbound",
    ]
    guards.bind(args, conf, "/opt/unbound/etc/unbound/unbound.conf")
    # Use an explicit daemon command rather than image supervision.
    unbound = guards.run(
        [
            "podman",
            "run",
            "-d",
            "--network=container:" + dovecot,
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            *args,
            image("mail/deployment-unbound.yaml"),
            "-d",
            "-c",
            "/opt/unbound/etc/unbound/unbound.conf",
        ]
    )
    return unbound


def start_clamav(d, dovecot):
    """Run the real scanner with only a harmless fixture signature database."""
    db = d / "avdb"
    db.mkdir()
    db.chmod(0o755)
    (db / "fixture.hdb").write_text(
        "44d88612fea8a8f36de82e1278abb02f:68:Eicar-Test-Signature\n"
    )
    clamconf = d / "clamd.conf"
    clamconf.write_text(
        yaml.safe_load((ROOT / "clamav/config-map-clamav.yaml").read_text())["data"][
            "clamd.conf"
        ]
    )
    clamconf.chmod(0o644)
    args = [
        "--user=1000:1000",
        "--read-only",
        "--tmpfs",
        "/run/clamav:rw,mode=0777",
        "--tmpfs",
        "/tmp:rw,mode=1777",
        "--tmpfs",
        "/var/log/clamav:rw,mode=0777",
        "--entrypoint",
        "clamd",
    ]
    guards.bind(args, db, "/var/lib/clamav")
    guards.bind(args, clamconf, "/etc/clamav/clamd.conf")
    clamav = guards.run(
        [
            "podman",
            "run",
            "-d",
            "--network=container:" + dovecot,
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            *args,
            image("clamav/deployment-clamav.yaml", "clamd"),
            "--foreground",
        ]
    )
    return clamav


def report_failure(containers, rspamd, postfix):
    """Print bounded logs from fixture containers only on a failed assertion."""
    for cid in containers:
        result = native(["podman", "logs", "--tail=12", cid], check=False)
        print(result.stdout[-1800:] + result.stderr[-1800:])
    if rspamd:
        result = native(
            ["podman", "exec", rspamd, "tail", "-20", "/var/log/mail.log"],
            check=False,
        )
        print(result.stdout[-6000:])
    if postfix:
        result = native(
            ["podman", "exec", postfix, "tail", "-30", "/var/log/fixture.log"],
            check=False,
        )
        print(result.stdout[-6000:])


def cleanup_volumes(volumes):
    """Remove only owned volumes still present after container removal."""
    for volume in volumes:
        result = native(["podman", "volume", "exists", volume], check=False)
        if result.returncode == 0:
            guards.run(["podman", "volume", "rm", volume])
        elif result.returncode != 1:
            raise RuntimeError("Unable to verify fixture volume cleanup")


def main():
    """Track and clean only resources created by this single isolated run."""
    containers = []
    volumes = []
    original_run = guards.run
    run_id = uuid.uuid4().hex

    def tagged(args):
        if args[:2] == ["podman", "run"]:
            args = (
                args[:2]
                + ["--label", "io.codex.mail-verification=" + run_id]
                + args[2:]
            )
        elif args[:3] == ["podman", "volume", "create"]:
            args = args + ["--label", "io.codex.mail-verification=" + run_id]
        return original_run(args)

    guards.run = tagged
    with tempfile.TemporaryDirectory(prefix="mail-runtime-") as directory:
        d = Path(directory)
        try:
            guards.create_certificate(d)
            dovecot = guards.start_dovecot(d)
            containers.append(dovecot)
            # Empty, disposable Valkey. Nothing talks to production backends.
            valkey = launch(
                dovecot,
                "harbor.andreybondarenko.com/dockerhub/valkey/valkey:9",
                ["--user=999:999", "--tmpfs", "/data:rw,mode=0777"],
            )
            containers.append(valkey)
            unbound = start_unbound(d, dovecot)
            containers.append(unbound)
            clamav = start_clamav(d, dovecot)
            containers.append(clamav)
            rspamd = launch(
                dovecot, image("mail/deployment-rspamd.yaml"), prepare_rspamd(d)
            )
            containers.append(rspamd)
            postfix = guards.start_postfix(
                d,
                dovecot,
                volumes,
                milter="127.0.0.1:11332",
                fixture_domain="guard.invalid",
            )
            containers.append(postfix)
            guards.retry(lambda: tcp_ready(guards.port(dovecot, 587)))
            time.sleep(3)
            transaction(d, dovecot, "healthy", "accepted")
            transaction(d, dovecot, "virus", "rejected", virus=True)
            guards.run(["podman", "stop", "--time", "3", clamav])
            transaction(d, dovecot, "scanner-down", "temporary")
            guards.run(["podman", "start", clamav])
            time.sleep(3)
            transaction(d, dovecot, "scanner-recovered", "accepted")
            guards.run(["podman", "stop", "--time", "3", rspamd])
            transaction(d, dovecot, "milter-down", "temporary")
            guards.run(["podman", "start", rspamd])
            time.sleep(3)
            transaction(d, dovecot, "milter-recovered", "accepted")
        except Exception:
            report_failure(containers, locals().get("rspamd"), locals().get("postfix"))
            raise
        finally:
            for cid in reversed(containers):
                guards.run(["podman", "rm", "-f", "-v", cid])
            cleanup_volumes(volumes)
            guards.run = original_run


if __name__ == "__main__":
    main()
