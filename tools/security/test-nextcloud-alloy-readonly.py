#!/usr/bin/env python3
"""Offline Alloy file-tail/push/checkpoint probe using fixture logs and mock Loki.

No production data, credentials, endpoints or published ports are used.
Requires rootless Podman and the host libsnappy library.
"""

from pathlib import Path
import ctypes
import ctypes.util
import subprocess
import tempfile
import time
import uuid
import yaml

ROOT = Path(__file__).resolve().parents[2]
MOCK = """from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
class Handler(BaseHTTPRequestHandler):
    body=b''
    def log_message(self,*args): pass
    def do_POST(self):
        if self.path!='/loki/api/v1/push': self.send_error(404); return
        type(self).body=self.rfile.read(int(self.headers['Content-Length']))
        self.send_response(204); self.end_headers()
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(type(self).body)
ThreadingHTTPServer(('127.0.0.1',3100),Handler).serve_forever()
"""


def run(args, timeout=60):
    r = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    if not r.returncode == 0:
        raise AssertionError(r.stdout[-2500:] + r.stderr[-2500:])
    return r.stdout.strip()


def decode(data):
    lib = ctypes.CDLL(ctypes.util.find_library("snappy"))
    lib.snappy_uncompressed_length.argtypes = [
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_size_t),
    ]
    lib.snappy_uncompress.argtypes = [
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_size_t),
    ]
    source = ctypes.create_string_buffer(data)
    size = ctypes.c_size_t()
    if not lib.snappy_uncompressed_length(source, len(data), ctypes.byref(size)) == 0:
        raise AssertionError
    if not 0 < size.value < 1048576:
        raise AssertionError
    output = ctypes.create_string_buffer(size.value)
    if not lib.snappy_uncompress(source, len(data), output, ctypes.byref(size)) == 0:
        raise AssertionError
    return output.raw[: size.value]


def main():
    pod = yaml.safe_load((ROOT / "nextcloud/stateful-set-nextcloud-web.yaml").read_text())["spec"][
        "template"
    ]["spec"]
    c = next(c for c in pod["containers"] if c["name"] == "alloy")
    if not pod["securityContext"]["runAsUser"] == pod["securityContext"]["runAsGroup"] == 33:
        raise AssertionError
    if not c["securityContext"]["readOnlyRootFilesystem"] is True:
        raise AssertionError
    if not c["securityContext"]["allowPrivilegeEscalation"] is False:
        raise AssertionError
    if not c["securityContext"]["capabilities"] == {"drop": ["ALL"]}:
        raise AssertionError
    if (
        not next((v for v in c["volumeMounts"] if v["mountPath"] == "/nextcloud"))["readOnly"]
        is True
    ):
        raise AssertionError
    if not "--storage.path=/data-alloy" in c["args"]:
        raise AssertionError
    config = yaml.safe_load(
        (ROOT / "nextcloud/config-map-alloy-nextcloud-config.yaml").read_text()
    )["data"]["config.alloy"]
    upstream = "http://loki.loki.svc.cluster.local:3100/loki/api/v1/push"
    if not config.count(upstream) == 1:
        raise AssertionError
    config = config.replace(upstream, "http://127.0.0.1:3100/loki/api/v1/push")
    volumes = []
    containers = []
    try:
        for suffix in ["state", "run"]:
            volumes.append(
                run(
                    [
                        "podman",
                        "volume",
                        "create",
                        "alloy-ro-guard-" + uuid.uuid4().hex + "-" + suffix,
                    ]
                )
            )
        run(
            [
                "podman",
                "run",
                "--rm",
                "--network=none",
                "--cap-drop=ALL",
                "--cap-add=CHOWN",
                "--group-add=33",
                "-v",
                volumes[0] + ":/data-alloy",
                "-v",
                volumes[1] + ":/run/alloy",
                "--entrypoint",
                "sh",
                "harbor.andreybondarenko.com/dockerhub/busybox:1.38",
                "-ec",
                "chown 0:33 /data-alloy /run/alloy; chmod 2777 /data-alloy /run/alloy",
            ]
        )
        with tempfile.TemporaryDirectory(prefix="alloy-readonly-") as directory:
            d = Path(directory)
            cfg = d / "config"
            cfg.mkdir(mode=0o755)
            (cfg / "config.alloy").write_text(config)
            logs = d / "nextcloud"
            logs.mkdir(mode=0o777)
            logs.chmod(0o777)
            (logs / "data").mkdir(mode=0o755)
            marker = "alloyreadonlyhealth" + uuid.uuid4().hex
            log = logs / "data" / "guard.log"
            log.write_text(marker + " initial fixture\n")
            mock = d / "mock.py"
            mock.write_text(MOCK)
            mock.chmod(0o644)
            server = run(
                [
                    "podman",
                    "run",
                    "-d",
                    "--network=none",
                    "--read-only",
                    "--read-only-tmpfs=false",
                    "--user=33:33",
                    "--cap-drop=ALL",
                    "--security-opt=no-new-privileges",
                    "-v",
                    str(mock) + ":/guard/mock.py:ro,Z",
                    "harbor.andreybondarenko.com/dockerhub/python:3.13-slim",
                    "python3",
                    "-B",
                    "/guard/mock.py",
                ]
            )
            containers.append(server)
            alloy = run(
                [
                    "podman",
                    "run",
                    "-d",
                    "--network=container:" + server,
                    "--read-only",
                    "--read-only-tmpfs=false",
                    "--user=33:33",
                    "--cap-drop=ALL",
                    "--security-opt=no-new-privileges",
                    "-v",
                    str(cfg) + ":/etc/alloy:ro,Z",
                    "-v",
                    str(logs) + ":/nextcloud:ro,Z",
                    "-v",
                    volumes[0] + ":/data-alloy",
                    "-v",
                    volumes[1] + ":/run/alloy",
                    c["image"],
                    *c["args"],
                ]
            )
            containers.append(alloy)

            def received(expected):
                for _ in range(35):
                    r = subprocess.run(
                        [
                            "podman",
                            "exec",
                            server,
                            "python3",
                            "-B",
                            "-c",
                            "import urllib.request,sys;sys.stdout.buffer.write(urllib.request.urlopen('http://127.0.0.1:3100/last').read())",
                        ],
                        capture_output=True,
                        check=False,
                    )
                    if r.returncode == 0 and r.stdout and expected.encode() in decode(r.stdout):
                        return
                    time.sleep(1)
                raise RuntimeError("Fixture log was not delivered to mock Loki")

            received(marker)
            second = marker + "tail"
            with log.open("a") as out:
                out.write(second + " appended fixture\n")
            received(second)
            run(
                [
                    "podman",
                    "exec",
                    server,
                    "python3",
                    "-B",
                    "-c",
                    "import urllib.request; assert all(urllib.request.urlopen('http://127.0.0.1:12345/'+p).status==200 for p in ['-/ready','-/healthy'])",
                ]
            )
            mountinfo = run(["podman", "exec", alloy, "cat", "/proc/1/mountinfo"])
            for mount in ["/", "/nextcloud"]:
                if not any(
                    (
                        p[4] == mount and "ro" in p[5].split(",")
                        for p in (s.split() for s in mountinfo.splitlines())
                    )
                ):
                    raise AssertionError
            status = run(["podman", "exec", alloy, "cat", "/proc/1/status"])
            for expected in [
                "CapEff:\t0000000000000000",
                "CapBnd:\t0000000000000000",
                "NoNewPrivs:\t1",
                "Seccomp:\t2",
            ]:
                if not expected in status:
                    raise AssertionError(status)
            # Fixture directory is otherwise writable; the read-only mount blocks writes.
            run(
                [
                    "podman",
                    "exec",
                    alloy,
                    "/bin/sh",
                    "-ec",
                    "if touch /nextcloud/must-not-be-created 2>/dev/null; then exit 1; fi",
                ]
            )
            run(["podman", "stop", "--time", "10", alloy])
            positions = run(
                [
                    "podman",
                    "run",
                    "--rm",
                    "--network=none",
                    "--user=33:33",
                    "--cap-drop=ALL",
                    "-v",
                    volumes[0] + ":/state:ro",
                    "--entrypoint",
                    "sh",
                    "harbor.andreybondarenko.com/dockerhub/busybox:1.38",
                    "-ec",
                    "find /state -type f -name '*positions*' -exec cat '{}' ';'",
                ]
            )
            if not "/nextcloud/data/guard.log" in positions:
                raise AssertionError("Fixture checkpoint was not saved under /data-alloy")
            print(
                "Nextcloud Alloy: initial/appended logs reached mock Loki; Snappy payloads verified"
            )
            print(
                "Read-only root and Nextcloud mount, blocked writes, writable checkpoints, zero caps/NNP/seccomp passed"
            )
    except Exception:
        for cid in containers:
            r = subprocess.run(
                ["podman", "logs", "--tail=15", cid], capture_output=True, text=True, check=False
            )
            print((r.stdout + r.stderr)[-2000:])
        raise
    finally:
        for cid in reversed(containers):
            run(["podman", "rm", "-f", cid])
        for volume in volumes:
            run(["podman", "volume", "rm", volume])


if __name__ == "__main__":
    main()
