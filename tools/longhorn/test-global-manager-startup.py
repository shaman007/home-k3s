#!/usr/bin/env python3
"""Verify non-root global-manager startup against local synthetic Kubernetes APIs.

Requires Podman and the pinned image. Uses no production credentials or storage.
The watch stream models an empty initial state; Lease responses are synthetic.
It tests startup/leadership, not real PV/Pod reconciliation or production RBAC.
"""

import datetime
import http.server
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import urllib.parse
import urllib.request

IMAGE = "docker.io/longhornio/longhorn-manager:v1.13.0"
RESOURCE_KINDS = {
    "backingimagedatasources": "BackingImageDataSource",
    "backingimagemanagers": "BackingImageManager",
    "backingimages": "BackingImage",
    "backupbackingimages": "BackupBackingImage",
    "backups": "Backup",
    "backuptargets": "BackupTarget",
    "backupvolumes": "BackupVolume",
    "configmaps": "ConfigMap",
    "cronjobs": "CronJob",
    "csidrivers": "CSIDriver",
    "daemonsets": "DaemonSet",
    "deployments": "Deployment",
    "endpoints": "Endpoints",
    "enginefrontends": "EngineFrontend",
    "engineimages": "EngineImage",
    "engines": "Engine",
    "instancemanagers": "InstanceManager",
    "instancemanagerupgradecontrols": "InstanceManagerUpgradeControl",
    "instancemanagerupgrades": "InstanceManagerUpgrade",
    "leases": "Lease",
    "nodes": "Node",
    "orphans": "Orphan",
    "persistentvolumeclaims": "PersistentVolumeClaim",
    "persistentvolumes": "PersistentVolume",
    "poddisruptionbudgets": "PodDisruptionBudget",
    "pods": "Pod",
    "priorityclasses": "PriorityClass",
    "recurringjobs": "RecurringJob",
    "replicas": "Replica",
    "secrets": "Secret",
    "services": "Service",
    "settings": "Setting",
    "shardgroups": "ShardGroup",
    "shards": "Shard",
    "sharemanagers": "ShareManager",
    "snapshotgroups": "SnapshotGroup",
    "snapshots": "Snapshot",
    "storageclasses": "StorageClass",
    "supportbundles": "SupportBundle",
    "systembackups": "SystemBackup",
    "systemrestores": "SystemRestore",
    "volumeattachments": "VolumeAttachment",
    "volumes": "Volume",
}


class MockAPI(http.server.BaseHTTPRequestHandler):
    lease = None

    def log_message(self, *args):
        pass

    def do_GET(self):
        self.respond()

    def do_POST(self):
        self.respond()

    def do_PUT(self):
        self.respond()

    def mock_lease(self):
        now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        return {
            "apiVersion": "coordination.k8s.io/v1",
            "kind": "Lease",
            "metadata": {
                "name": "longhorn-global-manager",
                "namespace": "longhorn-system",
                "resourceVersion": "1",
            },
            "spec": {
                "holderIdentity": "global-manager-probe",
                "leaseDurationSeconds": 20,
                "acquireTime": now,
                "renewTime": now,
                "leaseTransitions": 0,
            },
        }

    def respond(self):
        path = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(path.query)
        if "watch" in query:
            # client-go WatchList needs the initial-events-end bookmark before
            # its informer caches are considered synchronized.
            parts = path.path.split("/")
            version = "/".join(parts[2:4]) if parts[1] == "apis" else parts[2]
            event = {
                "type": "BOOKMARK",
                "object": {
                    "apiVersion": version,
                    "kind": RESOURCE_KINDS[parts[-1]],
                    "metadata": {
                        "resourceVersion": "1",
                        "annotations": {"k8s.io/initial-events-end": "true"},
                    },
                },
            }
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write((json.dumps(event) + "\n").encode())
            self.wfile.flush()
            time.sleep(35)
            return
        if "/leases/" in path.path and self.command == "GET":
            if MockAPI.lease is None:
                self.send_error(404)
                return
            body = MockAPI.lease
        elif self.command in ("POST", "PUT") and "/leases" in path.path:
            # Typed client-go sends protobuf. Consume it without needing a
            # protobuf dependency; this mock returns a fixed synthetic Lease.
            self.rfile.read(int(self.headers["Content-Length"]))
            body = self.mock_lease()
            MockAPI.lease = body
        elif self.command == "GET":
            body = {"metadata": {"resourceVersion": "1"}, "items": []}
        else:
            self.send_error(405)
            return
        self.send_response(201 if self.command == "POST" else 200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())


def main():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), MockAPI)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with tempfile.TemporaryDirectory(prefix="global-manager-probe-") as temporary:
            root = Path(temporary)
            root.chmod(0o755)
            (root / "kubeconfig").write_text(
                "apiVersion: v1\nkind: Config\nclusters:\n- name: mock\n"
                f'  cluster: {{server: "http://127.0.0.1:{server.server_port}"}}\n'
                "contexts:\n- name: mock\n  context: {cluster: mock, user: mock}\n"
                "current-context: mock\nusers:\n- name: mock\n  user: {}\n"
            )
            container = subprocess.check_output(
                [
                    "podman",
                    "run",
                    "--rm",
                    "-d",
                    "--user",
                    "1000:1000",
                    "--cap-drop=ALL",
                    "--security-opt=no-new-privileges",
                    "--network=host",
                    "--http-proxy=false",
                    "-v",
                    f"{root}:/test:ro,Z",
                    "-e",
                    "POD_NAME=global-manager-probe",
                    "-e",
                    "POD_NAMESPACE=longhorn-system",
                    IMAGE,
                    "longhorn-manager",
                    "-d",
                    "global",
                    "--kube-config=/test/kubeconfig",
                ],
                text=True,
            ).strip()
            try:
                for _ in range(80):
                    logs = subprocess.check_output(
                        ["podman", "logs", container], text=True, stderr=subprocess.STDOUT
                    )
                    if "Global controllers started; serving as leader" in logs:
                        with urllib.request.urlopen(
                            "http://127.0.0.1:9505/v1/healthz", timeout=2
                        ) as response:
                            if not response.status == 200:
                                raise AssertionError
                        state = subprocess.check_output(
                            [
                                "podman",
                                "exec",
                                container,
                                "sh",
                                "-c",
                                'grep -E "Uid:|Gid:|CapEff|NoNewPrivs|Seccomp:" /proc/1/status',
                            ],
                            text=True,
                        )
                        for expected in [
                            "Uid:\t1000",
                            "Gid:\t1000",
                            "CapEff:\t0000000000000000",
                            "NoNewPrivs:\t1",
                            "Seccomp:\t2",
                        ]:
                            if not expected in state:
                                raise AssertionError(state)
                        print(
                            "UID 1000: informer sync, mock lease acquisition, global controller startup and health HTTP200 passed"
                        )
                        break
                    if not "fatal" not in logs.lower():
                        raise AssertionError(logs[-3000:])
                    time.sleep(0.25)
                else:
                    raise AssertionError(logs[-5000:])
            finally:
                subprocess.run(
                    ["podman", "stop", "--time", "3", container],
                    check=True,
                    stdout=subprocess.DEVNULL,
                )
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
