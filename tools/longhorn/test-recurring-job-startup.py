#!/usr/bin/env python3
"""Run the pinned job image against isolated mock APIs; select no real volumes.

Requires rootless Podman and OpenSSL. Authentication and TLS material are
synthetic, temporary, and never used with Kubernetes or production services.
"""

import http.server
import json
from pathlib import Path
import ssl
import subprocess
import tempfile
import threading
import urllib.parse

IMAGE = "docker.io/longhornio/longhorn-manager:v1.13.0"


class MockAPI(http.server.BaseHTTPRequestHandler):
    """Serve synthetic Kubernetes API responses for isolated startup-policy probes."""
    task = "snapshot"
    calls = []
    manager_port = None

    def log_message(self, *args):
        pass

    def do_GET(self):
        self.respond()

    def do_PUT(self):
        self.respond()

    def respond(self):
        path = urllib.parse.urlparse(self.path).path
        self.calls.append((self.command, path))
        body = {
            "apiVersion": "longhorn.io/v1beta2",
            "kind": "RecurringJob",
            "metadata": {"name": "compatibility-probe", "namespace": "longhorn-system"},
            "spec": {
                "task": self.task,
                "retain": 1,
                "concurrency": 1,
                "groups": [],
                "retentionPolicy": "count-based",
            },
            "status": {"executionCount": 0},
        }
        if self.command == "PUT" and path.endswith("/status"):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        elif path == "/v1":
            body = {"type": "collection", "data": []}
        elif "/recurringjobs/" in path:
            pass
        elif path.endswith("/settings/allow-recurring-job-while-volume-detached"):
            body = {
                "apiVersion": "longhorn.io/v1beta2",
                "kind": "Setting",
                "metadata": {"name": "allow-recurring-job-while-volume-detached"},
                "value": "true",
            }
        elif path.endswith("/volumes"):
            body = {"apiVersion": "longhorn.io/v1beta2", "kind": "VolumeList", "items": []}
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("X-API-Schemas", f"http://127.0.0.1:{self.manager_port}/v1")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())


def main():
    with tempfile.TemporaryDirectory(prefix="longhorn-mock-") as temporary:
        root = Path(temporary)
        root.chmod(0o755)
        account = root / "sa"
        account.mkdir()
        (account / "token").write_text("synthetic-local-test-only")
        (account / "namespace").write_text("longhorn-system")
        subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-keyout",
                str(root / "key.pem"),
                "-out",
                str(account / "ca.crt"),
                "-days",
                "1",
                "-subj",
                "/CN=localhost",
                "-addext",
                "subjectAltName=IP:127.0.0.1",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
        kube = http.server.ThreadingHTTPServer(("127.0.0.1", 0), MockAPI)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(str(account / "ca.crt"), str(root / "key.pem"))
        kube.socket = context.wrap_socket(kube.socket, server_side=True)
        manager = http.server.ThreadingHTTPServer(("127.0.0.1", 0), MockAPI)
        MockAPI.manager_port = manager.server_port
        servers = [kube, manager]
        for server in servers:
            threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            for task in ["snapshot", "backup", "filesystem-trim"]:
                MockAPI.task, MockAPI.calls = task, []
                result = subprocess.run(
                    [
                        "podman",
                        "run",
                        "--rm",
                        "--user",
                        "1000:1000",
                        "--cap-drop=ALL",
                        "--security-opt=no-new-privileges",
                        "--network=host",
                        "--http-proxy=false",
                        "-v",
                        f"{account}:/var/run/secrets/kubernetes.io/serviceaccount:ro,Z",
                        "-e",
                        "POD_NAMESPACE=longhorn-system",
                        "-e",
                        "KUBERNETES_SERVICE_HOST=127.0.0.1",
                        "-e",
                        f"KUBERNETES_SERVICE_PORT={kube.server_port}",
                        IMAGE,
                        "sh",
                        "-ec",
                        'id; grep -E "CapEff|NoNewPrivs|Seccomp:" /proc/self/status; '
                        'exec longhorn-manager "$@"',
                        "sh",
                        "recurring-job",
                        "compatibility-probe",
                        "--manager-url",
                        f"http://127.0.0.1:{manager.server_port}/v1",
                    ],
                    text=True,
                    capture_output=True,
                    timeout=90,
                    check=False,
                )
                if not result.returncode == 0:
                    raise AssertionError(result.stderr)
                if not "uid=1000" in result.stdout:
                    raise AssertionError(result.stdout)
                if not "CapEff:\t0000000000000000" in result.stdout:
                    raise AssertionError(result.stdout)
                if not "NoNewPrivs:\t1" in result.stdout:
                    raise AssertionError(result.stdout)
                if not "Seccomp:\t2" in result.stdout:
                    raise AssertionError(result.stdout)
                if not any(
                    (method == "PUT" and path.endswith("/status") for method, path in MockAPI.calls)
                ):
                    raise AssertionError
                if not any((path.endswith("/volumes") for method, path in MockAPI.calls)):
                    raise AssertionError
                print(
                    (
                        f"{task}"
                        f": UID 1000 / drop ALL / NNP / seccomp; "
                        f"API startup passed; zero volumes "
                        f"selected"
                    ),
                    flush=True,
                )
        finally:
            for server in servers:
                server.shutdown()
                server.server_close()


if __name__ == "__main__":
    main()
