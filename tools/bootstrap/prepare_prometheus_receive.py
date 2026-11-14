#!/usr/bin/env python3
"""Export inactive staged Prometheus/Receive candidates; never access the cluster."""

import argparse
import copy
import hashlib
import json
import textwrap
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PROM = "metrics/kubernetes-prometheus/deployment-prometheus-deployment.yaml"
CONFIG = "metrics/kubernetes-prometheus/config-map-prometheus-server-conf.yaml"
QUERIER = "thanos/deployment-thanos-querier.yaml"
POLICY = "metrics/network-policy-monitoring-thanos-receive.yaml"
STAGES = ("infrastructure", "dual-write", "cutover")
OPTIONAL = {
    "spotify-metrics-token",
    "hister-metrics-token",
    "meilisearch-metrics-token",
}


def read(path):
    """Load a manifest without reading any live Secret payload."""
    return yaml.safe_load((ROOT / path).read_text())


def remote_write():
    """A bounded asynchronous queue, not a Prometheus startup prerequisite."""
    return {
        "name": "thanos-receive",
        "url": "http://thanos-receive.monitoring.svc.cluster.local:19291/api/v1/receive",
        "headers": {"THANOS-TENANT": "prometheus"},
        "remote_timeout": "30s",
        "queue_config": {
            "min_shards": 1,
            "max_shards": 4,
            "capacity": 10000,
            "max_samples_per_send": 2000,
            "retry_on_http_429": True,
        },
    }


def receive_statefulset():
    """Single ingestor owns a NEW PVC; never shares the Prometheus TSDB."""
    image = next(
        c["image"]
        for c in read(QUERIER)["spec"]["template"]["spec"]["containers"]
        if c["name"] == "thanos"
    )
    security = {
        "allowPrivilegeEscalation": False,
        "capabilities": {"drop": ["ALL"]},
        "readOnlyRootFilesystem": True,
        "runAsNonRoot": True,
        "runAsUser": 1001,
        "runAsGroup": 1001,
    }
    return {
        "apiVersion": "apps/v1",
        "kind": "StatefulSet",
        "metadata": {
            "name": "thanos-receive",
            "namespace": "monitoring",
            "labels": {
                "app": "thanos-receive",
                "app.kubernetes.io/name": "thanos-receive",
                "app.kubernetes.io/instance": "thanos-receive",
                "app.kubernetes.io/managed-by": "argoCD",
            },
        },
        "spec": {
            "replicas": 1,
            "serviceName": "thanos-receive-headless",
            "selector": {"matchLabels": {"app": "thanos-receive"}},
            "persistentVolumeClaimRetentionPolicy": {
                "whenDeleted": "Retain",
                "whenScaled": "Retain",
            },
            "template": {
                "metadata": {
                    "labels": {"app": "thanos-receive", "thanos-store-api": "true"}
                },
                "spec": {
                    "automountServiceAccountToken": False,
                    "priorityClassName": "homelab-standard",
                    "securityContext": {
                        "fsGroup": 1001,
                        "fsGroupChangePolicy": "OnRootMismatch",
                        "seccompProfile": {"type": "RuntimeDefault"},
                    },
                    "containers": [
                        {
                            "name": "thanos",
                            "image": image,
                            "imagePullPolicy": "IfNotPresent",
                            "securityContext": security,
                            "env": [
                                {
                                    "name": "POD_NAME",
                                    "valueFrom": {
                                        "fieldRef": {"fieldPath": "metadata.name"}
                                    },
                                }
                            ],
                            "args": [
                                "receive",
                                "--log.level=info",
                                "--tsdb.path=/data",
                                "--tsdb.retention=3d",
                                "--tsdb.min-block-duration=2h",
                                "--tsdb.max-block-duration=2h",
                                "--receive.replication-factor=1",
                                "--receive.default-tenant-id=prometheus",
                                "--receive.tenant-label-name=cluster",
                                '--label=replica="$(POD_NAME)"',
                                "--remote-write.address=0.0.0.0:19291",
                                "--http-address=0.0.0.0:10902",
                                "--grpc-address=0.0.0.0:10901",
                                "--objstore.config-file=/etc/thanos/objstore.yml",
                            ],
                            "ports": [
                                {"name": "remote-write", "containerPort": 19291},
                                {"name": "http", "containerPort": 10902},
                                {"name": "grpc", "containerPort": 10901},
                            ],
                            "startupProbe": {
                                "httpGet": {"port": "http", "path": "/-/ready"},
                                "periodSeconds": 10,
                                "timeoutSeconds": 2,
                                "failureThreshold": 120,
                            },
                            "readinessProbe": {
                                "httpGet": {"port": "http", "path": "/-/ready"},
                                "periodSeconds": 10,
                                "timeoutSeconds": 2,
                            },
                            "livenessProbe": {
                                "httpGet": {"port": "http", "path": "/-/healthy"},
                                "periodSeconds": 30,
                                "timeoutSeconds": 2,
                            },
                            "resources": {
                                "requests": {"cpu": "100m", "memory": "2Gi"},
                                "limits": {"memory": "6Gi"},
                            },
                            "volumeMounts": [
                                {"name": "data", "mountPath": "/data"},
                                {
                                    "name": "objstore",
                                    "mountPath": "/etc/thanos",
                                    "readOnly": True,
                                },
                            ],
                        }
                    ],
                    "volumes": [
                        {
                            "name": "objstore",
                            "secret": {
                                "secretName": "thanos-receive-objstore-internal"
                            },
                        }
                    ],
                },
            },
            "volumeClaimTemplates": [
                {
                    "metadata": {
                        "name": "data",
                        "labels": {"storage.k8s.io/name": "longhorn"},
                    },
                    "spec": {
                        "accessModes": ["ReadWriteOnce"],
                        "storageClassName": "longhorn",
                        "resources": {"requests": {"storage": "64Gi"}},
                    },
                }
            ],
        },
    }


def services():
    """Separate receiver endpoints; Prometheus Service remains readiness-aware."""
    result = []
    for name, headless in [
        ("thanos-receive", False),
        ("thanos-receive-headless", True),
    ]:
        spec = {
            "selector": {"app": "thanos-receive"},
            "ports": [
                {"name": n, "port": p, "targetPort": n}
                for n, p in [("remote-write", 19291), ("http", 10902), ("grpc", 10901)]
            ],
        }
        if headless:
            spec["clusterIP"] = "None"
        result.append(
            {
                "apiVersion": "v1",
                "kind": "Service",
                "metadata": {"name": name, "namespace": "monitoring"},
                "spec": spec,
            }
        )
    return result


def policies():
    """Only Prometheus may write, Querier may read, Receiver may access direct S3."""

    def peer(app):
        return {"podSelector": {"matchLabels": {"app": app}}}

    def port(number):
        return [{"protocol": "TCP", "port": number}]

    def policy(name, app, kind, rules):
        return {
            "apiVersion": "networking.k8s.io/v1",
            "kind": "NetworkPolicy",
            "metadata": {"name": name, "namespace": "monitoring"},
            "spec": {
                "podSelector": {"matchLabels": {"app": app}},
                "policyTypes": [kind],
                kind.lower(): rules,
            },
        }

    s3 = read("metrics/network-policy-monitoring-allow-egress-thanos-s3-internal.yaml")
    s3["metadata"]["name"] = "monitoring-receive-s3"
    s3["spec"]["podSelector"] = {"matchLabels": {"app": "thanos-receive"}}
    return [
        policy(
            "monitoring-receive-ingress",
            "thanos-receive",
            "Ingress",
            [
                {
                    "from": [peer("prometheus-server")],
                    "ports": port(19291) + port(10902),
                },
                {"from": [peer("thanos-querier")], "ports": port(10901)},
            ],
        ),
        policy(
            "monitoring-prometheus-receive",
            "prometheus-server",
            "Egress",
            [{"to": [peer("thanos-receive")], "ports": port(19291) + port(10902)}],
        ),
        s3,
    ]


def infrastructure():
    """Prepare Receiver without touching Prometheus workload or its configuration."""
    secret = read("thanos/external-secret-thanos-compactor-objstore-internal.yaml")
    secret["metadata"]["name"] = "thanos-receive-objstore-internal"
    secret["metadata"].pop("annotations", None)
    secret["spec"]["target"]["name"] = "thanos-receive-objstore-internal"
    result = {
        "thanos/stateful-set-thanos-receive.yaml": [receive_statefulset()],
        "thanos/service-thanos-receive.yaml": services(),
        "thanos/external-secret-thanos-receive-objstore-internal.yaml": [secret],
        POLICY: policies(),
    }
    for path in [
        "metrics/network-policy-monitoring-allow-egress-intra-namespace.yaml",
        "metrics/network-policy-monitoring-allow-ingress-from-monitoring.yaml",
    ]:
        obj = read(path)
        values = obj["spec"]["podSelector"]["matchExpressions"][0]["values"]
        if "thanos-receive" not in values:
            values.append("thanos-receive")
        result[path] = [obj]
    path = "metrics/network-policy-monitoring-allow-egress-thanos-querier.yaml"
    obj = read(path)
    rule = copy.deepcopy(obj["spec"]["egress"][-1])
    rule["to"][0]["podSelector"]["matchLabels"]["app"] = "thanos-receive"
    if rule not in obj["spec"]["egress"]:
        obj["spec"]["egress"].append(rule)
    result[path] = [obj]
    path = "metrics/network-policy-monitoring-allow-egress-thanos-s3-internal.yaml"
    obj = read(path)
    values = obj["spec"]["podSelector"]["matchExpressions"][0]["values"]
    if "thanos-receive" not in values:
        values.append("thanos-receive")
    result[path] = [obj]
    path = "seaweedfs/network-policy-seaweedfs-allow-ingress-observability-s3.yaml"
    obj = read(path)
    values = obj["spec"]["ingress"][0]["from"][0]["podSelector"]["matchExpressions"][0][
        "values"
    ]
    if "thanos-receive" not in values:
        values.append("thanos-receive")
    result[path] = [obj]
    path = "argocd/application-monitoring-network-policy.yaml"
    obj = read(path)
    directory = obj["spec"]["source"]["directory"]
    if Path(POLICY).name not in directory["include"]:
        directory["include"] = directory["include"].replace(
            "}", "," + Path(POLICY).name + "}"
        )
    result[path] = [obj]
    return result


def prepare_config(cm):
    """Add canonical remote write, its scrape job and extra alerts without weakening old rules."""
    config = yaml.safe_load(cm["data"]["prometheus.yaml"])
    if config["global"]["external_labels"] != {"cluster": "prometheus"}:
        raise ValueError("Review changed external labels before generating")
    if config.get("remote_write") not in (None, [], [remote_write()]):
        raise ValueError("Review existing remote_write before generating")
    config["remote_write"] = [remote_write()]
    job = {
        "job_name": "thanos-receive",
        "scrape_interval": "30s",
        "static_configs": [
            {"targets": ["thanos-receive.monitoring.svc.cluster.local:10902"]}
        ],
    }
    existing = [
        j for j in config["scrape_configs"] if j["job_name"] == "thanos-receive"
    ]
    if existing and existing != [job]:
        raise ValueError("Review existing Receive scrape job")
    if not existing:
        config["scrape_configs"].append(job)
    # Preserve every existing alert byte-for-byte; append additional sender alerts only.
    rules = cm["data"]["prometheus.rules"]
    additional_rules = textwrap.dedent("""
    - name: remote-write-recovery
      rules:
      - alert: PrometheusRemoteWriteLag
        expr: time() - prometheus_remote_storage_queue_highest_sent_timestamp_seconds{remote_name="thanos-receive"} > 300
        for: 10m
        labels: {severity: mail, owner: homelab, priority: warning}
        annotations:
          summary: Prometheus remote write is falling behind.
          runbook_url: https://github.com/shaman007/home-k3s/blob/main/docs/startup/prometheus-receive/README.md#limits-and-rollback
          description: Local scraping remains independent; investigate Receive and drain the WAL before its replay window is lost.
      - alert: PrometheusRemoteWriteDroppedSamples
        expr: increase(prometheus_remote_storage_samples_dropped_total{remote_name="thanos-receive"}[5m]) > 0
        labels: {severity: mail, owner: homelab, priority: critical}
        annotations:
          summary: Prometheus remote write dropped samples.
          runbook_url: https://github.com/shaman007/home-k3s/blob/main/docs/startup/prometheus-receive/README.md#limits-and-rollback
          description: Investigate ingestion failure and assess recovery from retained local blocks; do not reset TSDB.
""")
    existing_group = [
        g
        for g in yaml.safe_load(rules)["groups"]
        if g["name"] == "remote-write-recovery"
    ]
    if not existing_group:
        rules += additional_rules
    elif existing_group != yaml.safe_load(additional_rules):
        raise ValueError("Review changed remote write alerts")
    return config, rules


def cutover_deployment():
    """Detach only the sidecar and its mounts; retain mandatory TSDB/config/API auth."""
    deployment = read(PROM)
    pod = deployment["spec"]["template"]["spec"]
    pod["containers"] = [c for c in pod["containers"] if c["name"] != "thanos"]
    for c in pod["containers"]:
        c["volumeMounts"] = [
            v for v in c["volumeMounts"] if v["name"] != "prometheus-config-shared"
        ]
    pod["volumes"] = [
        v
        for v in pod["volumes"]
        if v["name"] not in {"objstoreyml", "prometheus-config-shared"}
    ]
    for volume in pod["volumes"]:
        if volume["name"] in OPTIONAL:
            volume["secret"]["optional"] = True
    return deployment


def candidate(stage):
    """Infrastructure, dual-write, then detach only after explicit data acceptance."""
    if stage not in STAGES:
        raise ValueError("Unknown migration stage")
    result = infrastructure()
    if stage == "infrastructure":
        return result
    cm = read(CONFIG)
    config, rules = prepare_config(cm)
    querier = read(QUERIER)
    args = querier["spec"]["template"]["spec"]["containers"][0]["args"]
    endpoint = "--endpoint=thanos-receive.monitoring.svc.cluster.local:10901"
    if endpoint not in args:
        args.append(endpoint)
    if stage == "cutover":
        result[PROM] = [cutover_deployment()]
        old_endpoint = "--endpoint=thanos-sidecar.monitoring.svc.cluster.local:10901"
        if old_endpoint in args:
            args.remove(old_endpoint)
        config["scrape_configs"] = [
            j for j in config["scrape_configs"] if j["job_name"] != "thanos-sidecar"
        ]
        rules = rules.replace(
            '"job", "thanos-sidecar"', '"job", "thanos-receive"'
        ).replace("job: thanos-sidecar", "job: thanos-receive")
    cm["data"]["prometheus.yaml"] = yaml.safe_dump(config, sort_keys=False, width=120)
    cm["data"]["prometheus.rules"] = rules
    result[CONFIG] = [cm]
    result[QUERIER] = [querier]
    return result


def validation_inventory(documents, output):
    """Use the standard resource validator without making extra promotion sources."""
    directory = output / "validation"
    directory.mkdir()
    groups = {
        "thanos": [
            obj
            for path, objects in documents.items()
            if path.startswith("thanos/")
            for obj in objects
        ],
        "kubernetes-prometheus": documents.get(PROM, [read(PROM)]),
        "namespaces": [
            obj
            for obj in yaml.safe_load_all(
                (ROOT / "namespaces/limit-ranges.yaml").read_text()
            )
            if obj and obj["metadata"].get("namespace") == "monitoring"
        ],
    }
    for name, objects in groups.items():
        (directory / (name + ".yaml")).write_text(
            yaml.safe_dump_all(objects, sort_keys=False)
        )
    (directory / "inventory.json").write_text(json.dumps(list(groups)) + "\n")


def export(stage, output):
    """Write only a new review tree outside Git; no implicit source promotion."""
    output = output.resolve()
    if output.exists() or output.is_relative_to(ROOT):
        raise ValueError("Use a new output directory outside Git")
    documents = candidate(stage)
    output.mkdir(parents=True)
    hashes = {}
    for path, objects in documents.items():
        source = ROOT / path
        if source.exists():
            hashes[path] = hashlib.sha256(source.read_bytes()).hexdigest()
        target = output / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(yaml.safe_dump_all(objects, sort_keys=False, width=120))
    (output / "index.json").write_text(
        json.dumps(
            {"stage": stage, "source_sha256": hashes, "paths": sorted(documents)},
            indent=2,
        )
        + "\n"
    )
    validation_inventory(documents, output)
    return len(documents)


def main():
    """Generate one explicitly selected inactive stage."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=STAGES, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps({"files": export(args.stage, args.output), "stage": args.stage}))


if __name__ == "__main__":
    main()
