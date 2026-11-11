#!/usr/bin/env python3
"""Render a staged Harbor signing rollout using a real trusted public key."""
import argparse
from pathlib import Path
import subprocess
import yaml

ROOT = Path(__file__).resolve().parents[2]


def prepare(public_key):
    subprocess.run(["openssl", "pkey", "-pubin", "-noout"], input=public_key,
                   text=True, check=True, capture_output=True)
    cron = yaml.safe_load((ROOT / "image-builder/cron-job-podman-builder.yaml").read_text())
    pod = cron["spec"]["jobTemplate"]["spec"]["template"]["spec"]
    # Keep dependency updates from the manifest when rebuilding signing helpers.
    helper_images = {x["name"]: x["image"] for x in pod["initContainers"]
                     if x["name"] in {"copy-busybox", "copy-cosign"}}
    # Re-rendering an already integrated template must not duplicate env/mounts.
    pod["initContainers"] = [x for x in pod["initContainers"] if x["name"] not in {"copy-busybox", "copy-cosign"}]
    pod["volumes"] = [x for x in pod["volumes"] if x["name"] not in {"signing-tools", "signing-key", "signing-public"}]
    build = pod["containers"][0]
    names = {"SIGN", "COSIGN_KEY", "COSIGN_PUBLIC_KEY", "COSIGN_PASSWORD", "DOCKER_CONFIG", "REGISTRY_AUTH_FILE"}
    build["env"] = [x for x in build["env"] if x["name"] not in names]
    build["volumeMounts"] = [x for x in build["volumeMounts"] if x["name"] not in {"signing-tools", "signing-key", "signing-public"}]
    tools_mount = {"name": "signing-tools", "mountPath": "/tools"}
    pod["initContainers"] += [
        {"name": "copy-busybox", "image": helper_images.get("copy-busybox", "harbor.andreybondarenko.com/dockerhub/library/busybox:1.38.0-musl"),
         "command": ["/bin/cp", "/bin/busybox", "/tools/busybox"],
         "volumeMounts": [tools_mount]},
        {"name": "copy-cosign", "image": helper_images.get("copy-cosign", "harbor.andreybondarenko.com/github/sigstore/cosign/cosign:v3.0.6"),
         "command": ["/tools/busybox", "cp", "/ko-app/cosign", "/tools/cosign"],
         "volumeMounts": [tools_mount]},
    ]
    for init in pod["initContainers"][-2:]:
        init["securityContext"] = {"allowPrivilegeEscalation": False,
            "capabilities": {"drop": ["ALL"]}, "readOnlyRootFilesystem": True,
            "runAsUser": 0, "runAsGroup": 0, "seccompProfile": {"type": "RuntimeDefault"}}
        init["resources"] = {"requests": {"cpu": "10m", "memory": "32Mi"},
                             "limits": {"memory": "128Mi"}}
    build = pod["containers"][0]
    if 'export PATH="/tools:$PATH"' not in build["args"][0]:
        build["args"][0] = build["args"][0].replace('set -Eeuo pipefail',
            'set -Eeuo pipefail\nexport PATH="/tools:$PATH"\nmkdir -p "$DOCKER_CONFIG"')
    build["env"] += [
        {"name": "SIGN", "value": "1"},
        {"name": "COSIGN_KEY", "value": "/var/run/signing/cosign.key"},
        {"name": "COSIGN_PUBLIC_KEY", "value": "/var/run/signing-public/cosign.pub"},
        {"name": "COSIGN_PASSWORD", "valueFrom": {"secretKeyRef": {
            "name": "podman-builder-signing", "key": "password"}}},
        {"name": "DOCKER_CONFIG", "value": "/workspace/registry-auth"},
        {"name": "REGISTRY_AUTH_FILE", "value": "/workspace/registry-auth/config.json"},
    ]
    build["volumeMounts"] += [dict(tools_mount, readOnly=True),
        {"name": "signing-key", "mountPath": "/var/run/signing", "readOnly": True},
        {"name": "signing-public", "mountPath": "/var/run/signing-public", "readOnly": True}]
    pod["volumes"] += [{"name": "signing-tools", "emptyDir": {"sizeLimit": "256Mi"}},
        {"name": "signing-key", "secret": {"secretName": "podman-builder-signing",
            "defaultMode": 256, "items": [{"key": "cosign.key", "path": "cosign.key"}]}},
        {"name": "signing-public", "configMap": {"name": "podman-builder-signing-public"}}]
    external = {"apiVersion": "external-secrets.io/v1", "kind": "ExternalSecret",
        "metadata": {"name": "podman-builder-signing", "namespace": "image-builder"},
        "spec": {"refreshInterval": "15m", "secretStoreRef": {"name": "vault-secret-store", "kind": "SecretStore"},
            "target": {"name": "podman-builder-signing", "creationPolicy": "Owner"},
            "data": [{"secretKey": k, "remoteRef": {"key": "image-signing", "property": p}}
                     for k, p in [("cosign.key", "private_key"), ("password", "password")]]}}
    config = {"apiVersion": "v1", "kind": "ConfigMap",
        "metadata": {"name": "podman-builder-signing-public", "namespace": "image-builder"},
        "data": {"cosign.pub": public_key}}
    base = list(yaml.safe_load_all((ROOT / "kyverno/policy-verify-own-ghcr.yaml").read_text()))[1]
    base["metadata"]["name"] = "verify-own-harbor-images"
    spec = base["spec"]
    spec["matchImageReferences"] = [{"glob": "harbor.andreybondarenko.com/library/*"}]
    spec["attestors"] = [{"name": "homelab", "cosign": {"key": {"data": public_key},
        "ctlog": {"url": "https://rekor.sigstore.dev"}}}]
    spec["validations"] = [{"expression": "(images.containers + images.initContainers + images.ephemeralContainers).map(image, verifyImageSignatures(image, [attestors.homelab])).all(result, result > 0)",
                            "message": "Image must be signed by the homelab signing key"}]
    return {"cron-job-podman-builder.yaml": cron, "external-secret-signing.yaml": external,
            "config-map-signing-public.yaml": config, "policy-verify-own-harbor.yaml": base}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-key", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    documents = prepare(args.public_key.read_text())
    args.output.mkdir(parents=True, exist_ok=False)
    for name, document in documents.items():
        (args.output / name).write_text(yaml.safe_dump(document, sort_keys=False))
    print("Prepared unsigned rollout manifests in", args.output)
    print("No key was created and no cluster or registry was changed")


if __name__ == "__main__":
    main()
