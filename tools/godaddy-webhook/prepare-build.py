#!/usr/bin/env python3
"""Write a reviewable, unsubmitted one-off Podman build Job with its exact source."""

import base64
import copy
import gzip
import hashlib
import io
from pathlib import Path
import tarfile
import yaml

root = Path(__file__).resolve().parent
buffer = io.BytesIO()
with tarfile.open(fileobj=buffer, mode="w") as archive:
    for name in ["Dockerfile", "go.mod", "go.sum", "main.go"]:
        payload = (root / name).read_bytes()
        entry = tarfile.TarInfo(name)
        entry.size = len(payload)
        entry.mode = 0o644
        archive.addfile(entry, io.BytesIO(payload))
source = gzip.compress(buffer.getvalue(), mtime=0)
source_hash = hashlib.sha256(source).hexdigest()
name = "godaddy-webhook-build-" + source_hash[:12]
image = "harbor.andreybondarenko.com/library/godaddy-webhook:" + source_hash[:12]
config = {
    "apiVersion": "v1",
    "kind": "ConfigMap",
    "metadata": {"name": name, "namespace": "image-builder"},
    "binaryData": {"source.tar.gz": base64.b64encode(source).decode()},
}
container = {
    "name": "build",
    "image": "quay.io/podman/stable:v5.8.9",
    "workingDir": "/workspace",
    "command": ["/bin/bash", "-ec"],
    "args": [
        (
            "set -Eeuo pipefail\n tar -xzf "
            "/source/source.tar.gz -C /workspace\n "
            "printf '%s' \"$HARBOR_PASSWORD\" | podman "
            "login harbor.andreybondarenko.com "
            '--username "$HARBOR_USERNAME" '
            "--password-stdin\n unset HARBOR_PASSWORD\n "
            'podman build --pull=always -t "$IMAGE" '
            ".\n podman push "
            '--digestfile=/tmp/image.digest "$IMAGE"\n '
            "cat /tmp/image.digest\n"
        )
    ],
    "securityContext": {"privileged": True},
    "env": [
        {
            "name": "HARBOR_USERNAME",
            "valueFrom": {"secretKeyRef": {"name": "podman-builder-harbor", "key": "username"}},
        },
        {
            "name": "HARBOR_PASSWORD",
            "valueFrom": {"secretKeyRef": {"name": "podman-builder-harbor", "key": "password"}},
        },
        {"name": "IMAGE", "value": image},
        {"name": "STORAGE_DRIVER", "value": "overlay"},
    ],
    "resources": {"requests": {"cpu": "500m", "memory": "1Gi"}, "limits": {"memory": "4Gi"}},
    "volumeMounts": [
        {"name": "source", "mountPath": "/source", "readOnly": True},
        {"name": "workspace", "mountPath": "/workspace"},
        {"name": "storage", "mountPath": "/var/lib/containers"},
    ],
}
job = {
    "apiVersion": "batch/v1",
    "kind": "Job",
    "metadata": {"name": name, "namespace": "image-builder"},
    "spec": {
        "backoffLimit": 0,
        "activeDeadlineSeconds": 1800,
        "ttlSecondsAfterFinished": 86400,
        "template": {
            "metadata": {
                "labels": {
                    "app.kubernetes.io/name": "podman-builder",
                    "app.kubernetes.io/instance": "podman-builder",
                }
            },
            "spec": {
                "automountServiceAccountToken": False,
                "restartPolicy": "Never",
                "nodeSelector": {"kubernetes.io/arch": "amd64"},
                "containers": [container],
                "volumes": [
                    {"name": "source", "configMap": {"name": name}},
                    {"name": "workspace", "emptyDir": {"sizeLimit": "2Gi"}},
                    {"name": "storage", "emptyDir": {"sizeLimit": "10Gi"}},
                ],
            },
        },
    },
}
# Reuse the reviewed signing runtime and secret references from the scheduled builder.
base = yaml.safe_load((root.parents[1] / "image-builder/cron-job-podman-builder.yaml").read_text())
base_pod = base["spec"]["jobTemplate"]["spec"]["template"]["spec"]
pod = job["spec"]["template"]["spec"]
pod["initContainers"] = copy.deepcopy(
    [c for c in base_pod["initContainers"] if c["name"] in {"copy-busybox", "copy-cosign"}]
)
pod["volumes"] += copy.deepcopy(
    [v for v in base_pod["volumes"] if v["name"].startswith("signing-")]
)
container["volumeMounts"] += copy.deepcopy(
    [v for v in base_pod["containers"][0]["volumeMounts"] if v["name"].startswith("signing-")]
)
container["env"] += copy.deepcopy(
    [
        v
        for v in base_pod["containers"][0]["env"]
        if v["name"]
        in {
            "COSIGN_KEY",
            "COSIGN_PUBLIC_KEY",
            "COSIGN_PASSWORD",
            "DOCKER_CONFIG",
            "REGISTRY_AUTH_FILE",
        }
    ]
)
container["args"][0] = container["args"][0].replace(
    "set -Eeuo pipefail",
    'set -Eeuo pipefail\n export PATH="/tools:$PATH"\n mkdir -p "$DOCKER_CONFIG"',
)
container["args"][0] = container["args"][0].replace(
    " cat /tmp/image.digest",
    ''' digest=$(cat /tmp/image.digest)
 [[ "$digest" =~ ^sha256:[0-9a-f]{64}$ ]] || exit 1
 cosign sign --yes --key "$COSIGN_KEY" "${IMAGE%:*}@$digest"
 cosign verify --key "$COSIGN_PUBLIC_KEY" "${IMAGE%:*}@$digest"
 printf '%s\\n' "$digest"''',
)
output = Path("/tmp") / (name + ".yaml")
output.write_text(yaml.safe_dump_all([config, job], sort_keys=False, explicit_start=True))
print("Build manifest:", output)
print("Source archive SHA256:", source_hash)
print("Target image:", image)
print("No Job was submitted")
