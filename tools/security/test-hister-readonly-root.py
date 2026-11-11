#!/usr/bin/env python3
"""Offline Hister index/search/reindex/restart probe; disposable data/config only."""

from pathlib import Path
import uuid
import subprocess
import tempfile
import time
import yaml

ROOT = Path(__file__).resolve().parents[2]


def run(args, timeout=90):
    """Run the probe command and fail when its expected execution does not succeed."""
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    if not result.returncode == 0:
        raise AssertionError(result.stdout[-2000:] + result.stderr[-2000:])
    return result.stdout.strip()


def main():
    """Offline Hister index/search/reindex/restart probe; disposable data/config only."""
    server = yaml.safe_load((ROOT / "hister/deployment-hister.yaml").read_text())["spec"][
        "template"
    ]["spec"]["containers"][0]
    sc = server["securityContext"]
    if not (sc["readOnlyRootFilesystem"] and sc["runAsNonRoot"]):
        raise AssertionError
    if not sc["runAsUser"] == sc["runAsGroup"] == 65532:
        raise AssertionError
    if not sc["allowPrivilegeEscalation"] is False:
        raise AssertionError
    if not sc["capabilities"] == {"drop": ["ALL"]}:
        raise AssertionError
    volume = run(["podman", "volume", "create", "hister-ro-guard-" + uuid.uuid4().hex])
    cid = None
    try:
        # New disposable volume only: match the existing permission init's UID.
        run(
            [
                "podman",
                "run",
                "--rm",
                "--network=none",
                "--cap-drop=ALL",
                "--cap-add=CHOWN",
                "-v",
                volume + ":/data",
                "--entrypoint",
                "sh",
                "harbor.andreybondarenko.com/dockerhub/busybox:1.38",
                "-ec",
                (
                    'printf "histerguarduniqueword offline '
                    'fixture\\n" > /data/fixture.txt; chmod '
                    "644 /data/fixture.txt; chown 65532:65532 "
                    "/data"
                ),
            ]
        )
        with tempfile.TemporaryDirectory(prefix="hister-readonly-") as directory:
            cfg = Path(directory) / "config.yml"
            pdf = Path(directory) / "fixture.pdf"
            content = b"BT /F1 14 Tf 72 720 Td (histerguardpdfunique) Tj ET"
            objects = [
                b"<< /Type /Catalog /Pages 2 0 R >>",
                b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
                (
                    b"<< /Type /Page /Parent 2 0 R /MediaBox "
                    b"[0 0 612 792] /Resources << /Font << /F1 "
                    b"5 0 R >> >> /Contents 4 0 R >>"
                ),
                b"<< /Length "
                + str(len(content)).encode()
                + b" >>\nstream\n"
                + content
                + b"\nendstream",
                b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
            ]
            data = b"%PDF-1.4\n"
            offsets = [0]
            for i, obj in enumerate(objects, 1):
                offsets.append(len(data))
                data += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
            xref = len(data)
            data += b"xref\n0 6\n0000000000 65535 f \n" + b"".join(
                f"{v:010} 00000 n \n".encode() for v in offsets[1:]
            )
            data += f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
            pdf.write_bytes(data)
            pdf.chmod(0o644)
            cfg.write_text(
                yaml.safe_dump(
                    {
                        "app": {"access_token": "disposable-guard-token"},
                        "server": {"address": "0.0.0.0:8080", "base_url": "http://127.0.0.1:8080/"},
                    }
                )
            )
            cfg.chmod(0o644)
            base = [
                "--read-only",
                "--read-only-tmpfs=false",
                "--user=65532:65532",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges",
                "-v",
                volume + ":/data",
            ]
            args = ["podman", "run", "-d", "--network=none"] + base
            args += [
                "-v",
                str(cfg) + ":/data/config.yml:ro,z",
                "-v",
                str(pdf) + ":/data/fixture.pdf:ro,z",
            ]
            for e in server["env"]:
                value = (
                    "http://127.0.0.1:8080/"
                    if e["name"] == "HISTER__SERVER__BASE_URL"
                    else e["value"]
                )
                args += ["-e", e["name"] + "=" + value]
            cid = run(args + [server["image"]])

            def cli(*command):
                return run(
                    [
                        "podman",
                        "exec",
                        cid,
                        "/hister/hister",
                        "--server-url",
                        "http://127.0.0.1:8080",
                        *command,
                    ]
                )

            def ready():
                for _ in range(30):
                    try:
                        cli("search", "--format=json", "histerguarduniqueword")
                        return
                    except AssertionError:
                        time.sleep(1)
                raise RuntimeError("Hister did not become ready")

            ready()
            cli("import", "file", "/data/fixture.txt")
            cli("import", "file", "/data/fixture.pdf")

            def search(query="histerguarduniqueword", expected="fixture.txt"):
                for _ in range(20):
                    result = cli("search", "--format=json", query)
                    if expected in result:
                        return
                    time.sleep(1)
                raise RuntimeError("Indexed fixture not found")

            search()
            search("histerguardpdfunique", "fixture.pdf")
            command = [
                "/hister/hister",
                "reindex",
                "--server-url",
                "http://127.0.0.1:8080",
                "--client-timeout",
                "0",
            ]
            run(
                [
                    "podman",
                    "run",
                    "--rm",
                    "--network=container:" + cid,
                    *base,
                    "-v",
                    str(cfg) + ":/data/config.yaml:ro,z",
                    "-e",
                    "HISTER_CONFIG=/data/config.yaml",
                    "-e",
                    "HISTER_DATA_DIR=/data",
                    "--entrypoint",
                    command[0],
                    server["image"],
                    *command[1:],
                ],
                timeout=120,
            )
            search()
            search("histerguardpdfunique", "fixture.pdf")
            run(["podman", "restart", cid])
            ready()
            search()
            search("histerguardpdfunique", "fixture.pdf")
            # Read /proc with the existing BusyBox image in the server's PID/net namespaces.
            status = run(
                [
                    "podman",
                    "run",
                    "--rm",
                    "--network=container:" + cid,
                    "--pid=container:" + cid,
                    "--user=65532:65532",
                    "--cap-drop=ALL",
                    "--entrypoint",
                    "cat",
                    "harbor.andreybondarenko.com/dockerhub/busybox:1.38",
                    "/proc/1/status",
                ]
            )
            for expected in [
                "CapEff:\t0000000000000000",
                "CapBnd:\t0000000000000000",
                "NoNewPrivs:\t1",
                "Seccomp:\t2",
            ]:
                if not expected in status:
                    raise AssertionError(status)
            print(
                (
                    "Hister: read-only root startup, text/PDF "
                    "import/search, isolated reindex client and "
                    "persistent restart passed"
                )
            )
            print(
                (
                    "UID/GID 65532, zero capabilities, "
                    "no-new-privileges and seccomp verified; "
                    "no production data or credentials used"
                )
            )
    except Exception:
        if cid:
            result = subprocess.run(
                ["podman", "logs", "--tail=20", cid], capture_output=True, text=True, check=False
            )
            # Fixture-only server; never print real configuration or credentials.
            print(
                (result.stdout + result.stderr).replace(
                    "disposable-guard-token", "[fixture token]"
                )[-2500:]
            )
        raise
    finally:
        if cid:
            run(["podman", "rm", "-f", cid])
        run(["podman", "volume", "rm", volume])


if __name__ == "__main__":
    main()
