"""Render an inert, one-off build request using the existing cluster builder.

Writes JSON to stdout only; never contacts Kubernetes, Harbor or OpenBao.
"""

import argparse
import base64
import copy
import gzip
import hashlib
import io
import json
import re
import tarfile
from pathlib import Path

import yaml

FILES = (
    "Dockerfile",
    "requirements.lock",
    "server.py",
    "opus_audio.py",
    "web_search.py",
    "memory_search.py",
    "conversation_memory.py",
    "mcp_transport.py",
    "device_tools.py",
    "reminder_speech.py",
    "home_assistant.py",
    "homeassistant_tools.json",
    "prompts.py",
    ".dockerignore",
)


def render(image_tag=None):
    """Package only explicit source files and pin the build tag to their digest."""
    root = Path(__file__).resolve().parent
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w") as target:
        for name in FILES:
            data = (root / name).read_bytes()
            if name == "homeassistant_tools.json":
                # Keep generated schema bundles stable across editor EOF normalization.
                data = json.dumps(json.loads(data), ensure_ascii=False, indent=2).encode()
            entry = tarfile.TarInfo(name)
            entry.size = len(data)
            entry.mode = 0o644
            target.addfile(entry, io.BytesIO(data))
    data = gzip.compress(archive.getvalue(), mtime=0)
    source_hash = hashlib.sha256(data).hexdigest()
    name = "aiy-voice-build-" + source_hash[:16]
    if image_tag is not None and not re.fullmatch(r"[a-zA-Z0-9_][a-zA-Z0-9_.-]{0,127}", image_tag):
        raise ValueError("Invalid image tag")
    image = "harbor.andreybondarenko.com/library/aiy-voice:" + (
        image_tag or "src-" + source_hash[:16]
    )
    template_path = root.parent / "image-builder/cron-job-podman-builder.yaml"
    template = yaml.safe_load(template_path.read_text(encoding="utf-8"))
    spec = copy.deepcopy(template["spec"]["jobTemplate"]["spec"])
    spec["backoffLimit"] = 0
    spec["activeDeadlineSeconds"] = 3600
    pod = spec["template"]["spec"]
    spec["template"]["metadata"]["labels"]["app.kubernetes.io/component"] = "aiy-one-off"
    pod["volumes"].append({"name": "source", "configMap": {"name": name}})
    pod["initContainers"][0] = {
        "name": "unpack-source",
        "image": "harbor.andreybondarenko.com/dockerhub/library/busybox:1.38.0-musl",
        "command": [
            "sh",
            "-ec",
            "mkdir -p /workspace/context; tar -xzf /source/context.tgz -C /workspace/context",
        ],
        "volumeMounts": [
            {"name": "workspace", "mountPath": "/workspace"},
            {"name": "source", "mountPath": "/source", "readOnly": True},
        ],
        "resources": {"requests": {"cpu": "10m", "memory": "32Mi"}, "limits": {"memory": "128Mi"}},
        "securityContext": {
            "allowPrivilegeEscalation": False,
            "capabilities": {"drop": ["ALL"]},
            "readOnlyRootFilesystem": True,
            "runAsUser": 0,
            "seccompProfile": {"type": "RuntimeDefault"},
        },
    }
    for init in pod["initContainers"]:
        if init["name"] == "copy-cosign":
            init["resources"]["limits"]["memory"] = "256Mi"
    build = pod["containers"][0]
    build["workingDir"] = "/workspace/context"
    build["env"].append({"name": "AIY_IMAGE", "value": image})
    build["env"].append({"name": "AIY_SOURCE_SHA256", "value": source_hash})
    build["args"] = ["""set -Eeuo pipefail
export PATH="/tools:$PATH"
mkdir -p "$DOCKER_CONFIG"
printf '%s' "$HARBOR_PASSWORD" | podman login "$REGISTRY" --username "$HARBOR_USERNAME" --password-stdin
unset HARBOR_PASSWORD
podman build --platform linux/amd64 --label "io.aiy.source.sha256=$AIY_SOURCE_SHA256" -t "$AIY_IMAGE" .
podman push --digestfile /workspace/image.digest "$AIY_IMAGE"
digest=$(cat /workspace/image.digest)
[[ "$digest" =~ ^sha256:[0-9a-f]{64}$ ]]
cosign sign --yes --key "$COSIGN_KEY" "$AIY_IMAGE@$digest"
cosign verify --key "$COSIGN_PUBLIC_KEY" "$AIY_IMAGE@$digest"
printf 'Verified image: %s@%s\\n' "$AIY_IMAGE" "$digest"
"""]
    return {
        "apiVersion": "v1",
        "kind": "List",
        "items": [
            {
                "apiVersion": "v1",
                "kind": "ConfigMap",
                "metadata": {"name": name, "namespace": "image-builder"},
                "immutable": True,
                "binaryData": {"context.tgz": base64.b64encode(data).decode()},
            },
            {
                "apiVersion": "batch/v1",
                "kind": "Job",
                "metadata": {
                    "name": name,
                    "namespace": "image-builder",
                    "annotations": {"aiy-source-sha256": source_hash},
                },
                "spec": spec,
            },
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--image-tag", help="Retain an explicitly approved destination tag on a retry"
    )
    arguments = parser.parse_args()
    print(json.dumps(render(arguments.image_tag), indent=2))
