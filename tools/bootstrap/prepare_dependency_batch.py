#!/usr/bin/env python3
"""Build inactive independent startup proposals; never edit active sources or call APIs."""

import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
BOOT = ROOT / "tools/bootstrap"
INTERNAL_S3 = "http://s3.seaweedfs.svc.cluster.local:8333"
THANOS_TEMPLATE = """{{- $store := .source | fromYaml -}}
{{- if or (ne (get $store "type") "S3") (not (kindIs "map" (get $store "config"))) -}}
{{- mustFromJson "S3-config-required" -}}
{{- end -}}
{{- $config := $store.config -}}
{{- $_ := set $config "endpoint" "s3.seaweedfs.svc.cluster.local:8333" -}}
{{- $_ := set $config "insecure" true -}}
{{- $store | toYaml -}}
"""


def read(path):
    """Read a single non-secret source document."""
    return yaml.safe_load((ROOT / path).read_text())


def config_map(name, namespace, files):
    """Mount code only, never credential values."""
    digest = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()[:12]
    return {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "immutable": True,
        "metadata": {"name": name + "-" + digest, "namespace": namespace},
        "data": files,
    }


def script(name):
    """Load a reviewed source script for an inactive ConfigMap."""
    return (BOOT / name).read_text()


def mail():
    """Render the active canonical mail package; never resurrect retired Redis waits."""
    spec = importlib.util.spec_from_file_location(
        "mail_gates", BOOT / "prepare_mail_gates.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.documents()


def nextcloud_cron():
    """Keep the PHP image/PVC and replace blind sleep with native read-only checks."""
    job = read("nextcloud/cron-job-nextcloud.yaml")
    pod = job["spec"]["jobTemplate"]["spec"]["template"]["spec"]
    work = pod["containers"][0]
    desired = ["/bin/sh", "/cron-gate/nextcloud_job_gate.sh"]
    if work["command"] not in (
        ["/bin/sh", "-c", "sleep 120; exec php /nextcloud/cron.php"],
        desired,
    ):
        raise ValueError("Review changed Nextcloud cron command")
    work["command"] = desired
    work["volumeMounts"] = [
        m for m in work.get("volumeMounts", []) if m["name"] != "cron-gate"
    ]
    pod["volumes"] = [v for v in pod.get("volumes", []) if v["name"] != "cron-gate"]
    cm = config_map(
        "nextcloud-cron-dependencies",
        "nextcloud",
        {
            name: script(name)
            for name in (
                "nextcloud_job_gate.sh",
                "probe_data.php",
                "nextcloud_job_ready.php",
            )
        },
    )
    work.setdefault("volumeMounts", []).append(
        {
            "name": "cron-gate",
            "mountPath": "/cron-gate",
            "readOnly": True,
        }
    )
    pod.setdefault("volumes", []).append(
        {"name": "cron-gate", "configMap": {"name": cm["metadata"]["name"]}}
    )
    return {
        "nextcloud/cron-job-nextcloud.yaml": job,
        "nextcloud/config-map-cron-dependencies.yaml": cm,
    }


def mail_training():
    """Skip before the trainer starts Dovecot or reads/deletes any queued spam."""
    job = read("mail/cron-job-rspamd-spam-trainer.yaml")
    pod = job["spec"]["jobTemplate"]["spec"]["template"]["spec"]
    work = pod["containers"][0]
    original = ["/bin/sh", "/config/train-spam.sh"]
    desired = ["/bin/sh", "/mail-training/mail_training_gate.sh", *original]
    if work["command"] not in (original, desired):
        raise ValueError("Review changed spam trainer command")
    cm = config_map(
        "mail-training-dependencies",
        "mail",
        {
            "mail_training_gate.sh": script("mail_training_gate.sh"),
        },
    )
    work["command"] = desired
    work["volumeMounts"] = [
        m for m in work.get("volumeMounts", []) if m["name"] != "mail-training"
    ]
    pod["volumes"] = [v for v in pod.get("volumes", []) if v["name"] != "mail-training"]
    work.setdefault("volumeMounts", []).append(
        {
            "name": "mail-training",
            "mountPath": "/mail-training",
            "readOnly": True,
        }
    )
    pod.setdefault("volumes", []).append(
        {"name": "mail-training", "configMap": {"name": cm["metadata"]["name"]}}
    )
    job["spec"]["jobTemplate"]["spec"]["activeDeadlineSeconds"] = 3600
    return {
        "mail/cron-job-rspamd-spam-trainer.yaml": job,
        "mail/config-map-training-dependencies.yaml": cm,
    }


def karakeep():
    """Gate only s6 workers; the browser Deployment starts independently."""
    deployment = read("karakeep/deployment-karakeep.yaml")
    env = read("karakeep/config-map-karakeep-env.yaml")["data"]
    if (
        env.get("BROWSER_WEB_URL") not in (
            "http://127.0.0.1:9222",
            "http://chrome.karakeep.svc.cluster.local:9222",
        )
        or env.get("MEILI_ADDR") != "http://meilisearch.karakeep.svc.cluster.local:7700"
    ):
        raise ValueError("Review changed Karakeep worker-provider addresses")
    pod = deployment["spec"]["template"]["spec"]
    web = next(c for c in pod["containers"] if c["name"] == "web")
    if not web["image"].endswith("/karakeep:0.34.1"):
        raise ValueError("Reinspect the new image's s6 worker runner before adoption")
    if "command" in web or "args" in web:
        raise ValueError("Review the existing entrypoint override")
    runner = (
        "#!/command/with-contenv sh\ncd /app/apps/workers\n"
        "exec node /worker-startup/karakeep_worker_gate.cjs\n"
    )
    cm = config_map(
        "karakeep-worker-startup",
        "karakeep",
        {
            "karakeep_worker_gate.cjs": script("karakeep_worker_gate.cjs"),
            "run": runner,
        },
    )
    web["volumeMounts"] = [m for m in web.get("volumeMounts", []) if m["name"] != "worker-startup"]
    pod["volumes"] = [v for v in pod.get("volumes", []) if v["name"] != "worker-startup"]
    web.setdefault("volumeMounts", []).extend(
        [
            {
                "name": "worker-startup",
                "mountPath": "/worker-startup",
                "readOnly": True,
            },
            {
                "name": "worker-startup",
                "mountPath": "/etc/s6-overlay/s6-rc.d/svc-workers/run",
                "subPath": "run",
                "readOnly": True,
            },
        ]
    )
    pod.setdefault("volumes", []).append(
        {
            "name": "worker-startup",
            "configMap": {"name": cm["metadata"]["name"], "defaultMode": 0o555},
        }
    )
    deployment["spec"]["template"]["metadata"].setdefault("annotations", {})[
        "checksum/karakeep-worker-startup"
    ] = hashlib.sha256(json.dumps(cm["data"], sort_keys=True).encode()).hexdigest()
    return {
        "karakeep/deployment-karakeep.yaml": deployment,
        "karakeep/config-map-worker-startup.yaml": cm,
    }


def egress_policy(name, namespace, selector):
    """Permit the direct S3 path only to the selected SeaweedFS Pods."""
    return {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "NetworkPolicy",
        "metadata": {"name": name, "namespace": namespace},
        "spec": {
            "podSelector": selector,
            "policyTypes": ["Egress"],
            "egress": [
                {
                    "to": [
                        {
                            "namespaceSelector": {
                                "matchLabels": {
                                    "kubernetes.io/metadata.name": "seaweedfs"
                                }
                            },
                            "podSelector": {"matchLabels": {"app": "seaweedfs-s3"}},
                        }
                    ],
                    "ports": [{"protocol": "TCP", "port": 8333}],
                }
            ],
        },
    }


def observability():
    """Preserve storage settings and credentials while bypassing public ingress."""
    loki = read("argocd/application-loki.yaml")
    sources = loki["spec"].get("sources", [loki["spec"].get("source")])
    source = next(s for s in sources if s and s.get("chart") == "loki")
    values = yaml.safe_load(source["helm"]["values"])
    values["loki"]["storage"]["s3"].update(endpoint=INTERNAL_S3, insecure=True)
    source["helm"]["values"] = yaml.safe_dump(values, sort_keys=False)
    thanos = read("thanos/external-secret-thanos-objstore-secret.yaml")
    # Keep the provider key/property exactly as they were; render the endpoint
    # override inside ESO without ever exporting or rewriting OpenBao values.
    if (
        len(thanos["spec"]["data"]) != 1
        or thanos["spec"]["data"][0]["secretKey"] != "objstore.yml"
    ):
        raise ValueError("Review changed Thanos source Secret schema")
    thanos["spec"]["data"][0]["secretKey"] = "source"
    thanos["spec"]["target"]["template"] = {
        "engineVersion": "v2",
        "mergePolicy": "Replace",
        "data": {"objstore.yml": THANOS_TEMPLATE},
    }
    # Monitoring policies use an explicit Argo include list, unlike Loki/SeaweedFS.
    policy_app = read("argocd/application-monitoring-network-policy.yaml")
    include = policy_app["spec"]["source"]["directory"]["include"]
    policy_file = "network-policy-monitoring-allow-egress-thanos-s3-internal.yaml"
    if not (include.startswith("{") and include.endswith("}")):
        raise ValueError("Review monitoring policy source include format")
    entries = include[1:-1].split(",")
    if policy_file not in entries:
        entries.append(policy_file)
    policy_app["spec"]["source"]["directory"]["include"] = "{" + ",".join(entries) + "}"
    selector = {
        "matchExpressions": [
            {
                "key": "app",
                "operator": "In",
                "values": [
                    "prometheus-server",
                    "thanos-store-gateway",
                    "thanos-compactor",
                ],
            }
        ]
    }
    loki_selector = {
        "matchLabels": {
            "app.kubernetes.io/component": "single-binary",
            "app.kubernetes.io/name": "loki",
            "app.kubernetes.io/instance": "loki",
        }
    }
    ingress = {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "NetworkPolicy",
        "metadata": {
            "name": "seaweedfs-allow-ingress-observability-s3",
            "namespace": "seaweedfs",
        },
        "spec": {
            "podSelector": {"matchLabels": {"app": "seaweedfs-s3"}},
            "policyTypes": ["Ingress"],
            "ingress": [
                {
                    "from": [
                        {
                            "namespaceSelector": {
                                "matchLabels": {
                                    "kubernetes.io/metadata.name": "monitoring"
                                }
                            },
                            "podSelector": selector,
                        },
                        {
                            "namespaceSelector": {
                                "matchLabels": {"kubernetes.io/metadata.name": "loki"}
                            },
                            "podSelector": loki_selector,
                        },
                    ],
                    "ports": [{"protocol": "TCP", "port": 8333}],
                }
            ],
        },
    }
    return {
        "argocd/application-loki.yaml": loki,
        "argocd/application-monitoring-network-policy.yaml": policy_app,
        "thanos/external-secret-thanos-objstore-secret.yaml": thanos,
        "metrics/network-policy-monitoring-allow-egress-thanos-s3-internal.yaml": egress_policy(
            "monitoring-allow-egress-thanos-s3-internal", "monitoring", selector
        ),
        "loki/network-policy-loki-allow-egress-s3-internal.yaml": egress_policy(
            "loki-allow-egress-s3-internal",
            "loki",
            loki_selector,
        ),
        "seaweedfs/network-policy-seaweedfs-allow-ingress-observability-s3.yaml": ingress,
    }


PACKAGES = {
    "mail": mail,
    "mail-training": mail_training,
    "nextcloud-cron": nextcloud_cron,
    "karakeep": karakeep,
    "observability": observability,
}


def observability_network():
    """Stage one contains only scoped permissions and their Argo source adoption."""
    proposal = observability()
    paths = (
        "argocd/application-monitoring-network-policy.yaml",
        "metrics/network-policy-monitoring-allow-egress-thanos-s3-internal.yaml",
        "loki/network-policy-loki-allow-egress-s3-internal.yaml",
        "seaweedfs/network-policy-seaweedfs-allow-ingress-observability-s3.yaml",
    )
    return {path: proposal[path] for path in paths}


def prepare(output, packages, *, network_only=False):
    """Write a new review directory outside the repository, never overwrite one."""
    output = output.resolve()
    if output.is_relative_to(ROOT):
        raise ValueError("Candidates must remain outside active repository sources")
    if network_only and packages != ["observability"]:
        raise ValueError("Network-only stage is specific to observability")
    proposals = {
        name: observability_network() if network_only else PACKAGES[name]()
        for name in packages
    }
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    inventory = {}
    for name, documents in proposals.items():
        inventory[name] = []
        for relative, document in documents.items():
            target = output / name / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            docs = document if isinstance(document, list) else [document]
            with target.open("x", encoding="utf-8") as handle:
                yaml.safe_dump_all(copy.deepcopy(docs), handle, sort_keys=False)
            source = ROOT / relative
            inventory[name].append(
                {
                    "path": relative,
                    "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest()
                    if source.is_file()
                    else None,
                }
            )
    (output / "index.json").write_text(json.dumps(inventory, indent=2) + "\n")
    return inventory


def main():
    """Render selected independent packages only; deployment remains separate."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--package", choices=[*PACKAGES, "all"], default="all")
    parser.add_argument("--network-only", action="store_true",
                        help="Render only observability stage-one policies and Argo adoption")
    args = parser.parse_args()
    if args.network_only and args.package != "observability":
        parser.error("--network-only requires --package observability")
    packages = list(PACKAGES) if args.package == "all" else [args.package]
    inventory = prepare(args.output, packages, network_only=args.network_only)
    print(
        json.dumps(
            {"output": str(args.output), "packages": list(inventory), "inactive": True}
        )
    )


if __name__ == "__main__":
    main()
