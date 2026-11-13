"""Render or explicitly update Dawarich startup source; never contact Kubernetes."""

import argparse
import copy
import hashlib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
ENV_NAMES = {
    "DATABASE_HOST",
    "DATABASE_PORT",
    "DATABASE_USERNAME",
    "DATABASE_PASSWORD",
    "DATABASE_NAME",
    "REDIS_URL",
    "RAILS_ENV",
}
WORKER_WRAPPER = (
    "bundle exec ruby /startup-gate/wait_dependencies.rb web\n"
    "exec sidekiq-entrypoint.sh\n"
)


def candidate(deployment=None):
    """Preserve the workload except for explicit local dependency gates and probes."""
    deployment = (
        copy.deepcopy(deployment)
        if deployment is not None
        else yaml.safe_load((ROOT / "dawarich/deployment-dawarich.yaml").read_text())
    )
    pod = deployment["spec"]["template"]["spec"]
    web = next(c for c in pod["containers"] if c["name"] == "dawarich")
    worker = next(c for c in pod["containers"] if c["name"] == "dawarich-sidekiq")
    original_worker = worker["command"] == ["sidekiq-entrypoint.sh"] and not worker.get(
        "args"
    )
    gated_worker = worker["command"] == ["/bin/sh", "-ec"] and worker.get("args") == [
        WORKER_WRAPPER
    ]
    if not (original_worker or gated_worker):
        raise ValueError("Review changed Sidekiq entrypoint before rendering")
    pod["volumes"] = [v for v in pod["volumes"] if v["name"] != "startup-gate"]
    pod["initContainers"] = [
        c for c in pod["initContainers"] if c["name"] != "wait-for-data-services"
    ]
    worker["volumeMounts"] = [
        v for v in worker["volumeMounts"] if v["name"] != "startup-gate"
    ]
    script = (ROOT / "tools/bootstrap/wait_dependencies.rb").read_text()
    deployment["spec"]["template"]["metadata"].setdefault("annotations", {})[
        "checksum/dawarich-startup-gate"
    ] = hashlib.sha256(script.encode()).hexdigest()
    environment = [copy.deepcopy(e) for e in web["env"] if e["name"] in ENV_NAMES]
    if {e["name"] for e in environment} != ENV_NAMES:
        raise ValueError("Required dependency environment changed")
    for entry in environment:
        if entry["name"] == "DATABASE_PASSWORD" and "secretKeyRef" not in entry.get(
            "valueFrom", {}
        ):
            raise ValueError("Database password must remain a Secret reference")
    mount = {"name": "startup-gate", "mountPath": "/startup-gate", "readOnly": True}
    pod["volumes"].append(
        {"name": "startup-gate", "configMap": {"name": "dawarich-startup-gate"}}
    )
    pod["initContainers"].append(
        {
            "name": "wait-for-data-services",
            "image": web["image"],
            "imagePullPolicy": web.get("imagePullPolicy", "IfNotPresent"),
            "command": [
                "bundle",
                "exec",
                "ruby",
                "/startup-gate/wait_dependencies.rb",
                "dependencies",
            ],
            "env": environment,
            "securityContext": copy.deepcopy(web["securityContext"]),
            "resources": {
                "requests": {"cpu": "10m", "memory": "64Mi"},
                "limits": {"memory": "192Mi"},
            },
            "volumeMounts": [copy.deepcopy(mount)],
        }
    )
    worker["volumeMounts"].append(copy.deepcopy(mount))
    worker["command"] = ["/bin/sh", "-ec"]
    worker["args"] = [WORKER_WRAPPER]
    web["readinessProbe"] = {
        "httpGet": {
            "path": "/api/v1/ready",
            "port": 3000,
            "httpHeaders": [{"name": "Host", "value": "localhost"}],
        },
        "periodSeconds": 10,
        "timeoutSeconds": 3,
        "failureThreshold": 3,
    }
    config = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {"name": "dawarich-startup-gate", "namespace": "dawarich"},
        "data": {"wait_dependencies.rb": script},
    }
    return [config, deployment]


def main():
    """Keep output inactive unless the user explicitly selects source generation."""
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--output", type=Path)
    mode.add_argument("--write-source", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    config, deployment = candidate()
    if args.write_source or args.check:
        targets = [
            (ROOT / "dawarich/config-map-startup-gate.yaml", config),
            (ROOT / "dawarich/deployment-dawarich.yaml", deployment),
        ]
        for path, document in targets:
            if args.check:
                if not path.exists() or yaml.safe_load(path.read_text()) != document:
                    raise SystemExit(f"Startup source is stale: {path}")
            else:
                path.write_text(yaml.safe_dump(document, sort_keys=False, width=110))
        print(
            "Dawarich startup source checked"
            if args.check
            else "Local source updated; no cluster calls made"
        )
        return
    output = args.output.resolve()
    if output.is_relative_to(ROOT):
        parser.error("Output must be outside the repository's GitOps tree")
    with output.open("x") as stream:
        yaml.safe_dump_all([config, deployment], stream, sort_keys=False)
    print(f"Inactive candidate: {output}; no Kubernetes calls made")


if __name__ == "__main__":
    main()
