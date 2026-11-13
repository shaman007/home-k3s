"""Maintain inactive native Mastodon sources. Never call Helm or Kubernetes."""

import argparse
import copy
import hashlib
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = ROOT / "mastodon/native"
SCRIPT = ROOT / "tools/bootstrap/mastodon_startup.rb"
SCRIPT_MOUNT = {"name": "startup-gate", "mountPath": "/startup-gate", "readOnly": True}
ENV_NAMES = {"DB_USER", "DB_PASS", "REDIS_PASSWORD"}
GATE_NAMES = {"wait-for-data-services", "migrate-schema", "wait-for-schema"}


def sources():
    """Load owned native manifests; no chart render or live objects as dependencies."""
    return {p.name: yaml.safe_load(p.read_text()) for p in DIRECTORY.glob("*.yaml")}


def init_container(web, mode, allow_pending="false"):
    """Reuse the exact web image so all roles check the same migration file set."""
    migration = mode == "migrate"
    security = copy.deepcopy(web["securityContext"])
    if not migration:
        security["readOnlyRootFilesystem"] = True
    container = {
        "name": {
            "dependencies": "wait-for-data-services",
            "migrate": "migrate-schema",
            "schema": "wait-for-schema",
        }[mode],
        "image": web["image"],
        "imagePullPolicy": web["imagePullPolicy"],
        "workingDir": "/opt/mastodon",
        "command": [
            "bundle",
            "exec",
            "ruby",
            "/startup-gate/mastodon_startup.rb",
            mode,
        ],
        "securityContext": security,
        "resources": {
            "requests": {
                "cpu": "100m" if migration else "10m",
                "memory": "512Mi" if migration else "64Mi",
            },
            "limits": {"memory": "1536Mi" if migration else "256Mi"},
        },
        "envFrom": copy.deepcopy(web["envFrom"]),
        "env": [
            copy.deepcopy(e) for e in web["env"] if migration or e["name"] in ENV_NAMES
        ],
        "volumeMounts": [copy.deepcopy(SCRIPT_MOUNT)],
    }
    if migration:
        container["env"].append(
            {"name": "MASTODON_ALLOW_PENDING_MIGRATIONS", "value": allow_pending}
        )
        # The ordinary exporter cannot start until init finishes; migrations do not emit metrics.
        for entry in container["env"]:
            if entry["name"] == "MASTODON_PROMETHEUS_EXPORTER_ENABLED":
                entry["value"] = "false"
        container["env"].append(
            {"name": "MASTODON_MIGRATION_OWNER", "value": "web-init"}
        )
    return container


def candidates():
    """One web init owns migrations; all three processes wait for complete schema."""
    documents = sources()
    web_pod = documents["deployment-mastodon-web.yaml"]["spec"]["template"]["spec"]
    web = next(c for c in web_pod["containers"] if c["name"] == "mastodon-web")
    existing_owner = next(
        (c for c in web_pod.get("initContainers", []) if c["name"] == "migrate-schema"),
        {},
    )
    policy = next(
        (
            e
            for e in existing_owner.get("env", [])
            if e["name"] == "MASTODON_ALLOW_PENDING_MIGRATIONS"
        ),
        {"value": "false"},
    )
    allow_pending = policy.get("value")
    if allow_pending not in {"true", "false"}:
        raise ValueError(
            "Migration write policy must be an explicit reviewed string literal"
        )
    script = SCRIPT.read_text()
    environment = documents["config-map-mastodon-env.yaml"]["data"]
    checksum = hashlib.sha256(
        (script + json.dumps(environment, sort_keys=True) + web["image"]).encode()
    ).hexdigest()
    documents["config-map-startup-gate.yaml"] = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {"name": "mastodon-startup-gate", "namespace": "mastodon"},
        "data": {"mastodon_startup.rb": script},
    }
    for document in documents.values():
        if document["kind"] != "Deployment":
            continue
        template = document["spec"]["template"]
        pod = template["spec"]
        template["metadata"].setdefault("annotations", {})[
            "checksum/mastodon-startup"
        ] = checksum
        pod["volumes"] = [
            v for v in (pod.get("volumes") or []) if v["name"] != "startup-gate"
        ] + [{"name": "startup-gate", "configMap": {"name": "mastodon-startup-gate"}}]
        initial = [
            c for c in (pod.get("initContainers") or []) if c["name"] not in GATE_NAMES
        ]
        initial.append(init_container(web, "dependencies"))
        if document["metadata"]["name"] == "mastodon-web":
            initial.append(init_container(web, "migrate", allow_pending))
        initial.append(init_container(web, "schema"))
        pod["initContainers"] = initial
    return documents


def render(output, documents):
    """Emit a private validation scope using the same Application names as CI."""
    output = output.resolve()
    if output.is_relative_to(ROOT):
        raise ValueError("Validation output must be outside the GitOps tree")
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    (output / "mastodon.yaml").write_text(
        yaml.safe_dump_all(documents.values(), sort_keys=False)
    )
    namespace_documents = []
    for path in sorted((ROOT / "namespaces").glob("*.yaml")):
        namespace_documents.extend(yaml.safe_load_all(path.read_text()))
    (output / "namespaces.yaml").write_text(
        yaml.safe_dump_all(namespace_documents, sort_keys=False)
    )
    (output / "inventory.json").write_text(json.dumps(["mastodon", "namespaces"]))


def main():
    """Preparation only: active Argo source is deliberately unchanged."""
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true")
    group.add_argument("--write-source", action="store_true")
    group.add_argument("--output", type=Path)
    args = parser.parse_args()
    documents = candidates()
    if args.output:
        render(args.output, documents)
        return
    for filename, document in documents.items():
        path = DIRECTORY / filename
        if args.check:
            if not path.exists() or yaml.safe_load(path.read_text()) != document:
                raise SystemExit("Stale native Mastodon source: " + filename)
        else:
            path.write_text(yaml.safe_dump(document, sort_keys=False, width=110))
    print(
        "Native Mastodon source checked"
        if args.check
        else "Inactive native source updated; no cluster calls"
    )


if __name__ == "__main__":
    main()
