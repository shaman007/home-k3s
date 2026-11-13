#!/usr/bin/env python3
"""Render inactive report candidates without editing active CronJobs."""

import argparse
import copy
import hashlib
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
LOKI = {
    "name": "loki",
    "url": "http://loki-gateway.loki.svc.cluster.local/loki/api/v1/labels",
}
REPORTS = {
    "logs-check": (
        "metrics/cron-job-logs-check.yaml",
        14400,
        [
            LOKI,
            {
                "name": "ollama",
                "url": "http://ollama.ollama.svc.cluster.local:11434/api/tags",
            },
        ],
    ),
    "external-access-daily-report": (
        "metrics/cron-job-external-access-daily-report.yaml",
        3600,
        [LOKI],
    ),
    "wordpress-daily-report": (
        "wordpress/cron-job-wordpress-daily-report.yaml",
        3600,
        [LOKI],
    ),
}


def candidate(name="logs-check"):
    """Wrap existing work in-place; never gate the cluster health reporter."""
    path, deadline, checks = REPORTS[name]
    original = yaml.safe_load((ROOT / path).read_text())
    job = copy.deepcopy(original)
    pod = job["spec"]["jobTemplate"]["spec"]["template"]["spec"]
    container = pod["containers"][0]
    original_argv = container["command"] + container.pop("args", [])
    container["command"] = [
        "python3",
        "/opt/cron-dependencies/gate.py",
        "--config",
        "/opt/cron-dependencies/config.json",
        "--",
        *original_argv,
    ]
    container.setdefault("volumeMounts", []).append(
        {
            "name": "cron-dependencies",
            "mountPath": "/opt/cron-dependencies",
            "readOnly": True,
        }
    )
    pod.setdefault("volumes", []).append(
        {
            "name": "cron-dependencies",
            "configMap": {"name": name + "-dependencies"},
        }
    )
    # Hard Pod/Job ceiling also covers image pulls, a stuck probe and application work.
    job["spec"]["jobTemplate"]["spec"]["activeDeadlineSeconds"] = deadline
    config = {
        "mode": "skip",
        "budget_seconds": 300,
        "interval_seconds": 5,
        "probe_seconds": 5,
        "checks": copy.deepcopy(checks),
    }
    config_map = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "immutable": True,
        "metadata": {
            "name": name + "-dependencies",
            "namespace": job["metadata"]["namespace"],
        },
        "data": {
            "gate.py": (ROOT / "tools/bootstrap/cron_dependency_gate.py").read_text(),
            "config.json": json.dumps(config, indent=2),
        },
    }
    digest = hashlib.sha256(
        json.dumps(config_map["data"], sort_keys=True).encode()
    ).hexdigest()[:12]
    config_map["metadata"]["name"] += "-" + digest
    pod["volumes"][-1]["configMap"]["name"] = config_map["metadata"]["name"]
    return [config_map, job]


def main():
    """Print the proposal only; active Argo sources are never written."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", choices=[*REPORTS, "all"], default="logs-check")
    args = parser.parse_args()
    names = list(REPORTS) if args.job == "all" else [args.job]
    print(
        yaml.safe_dump_all(
            [doc for name in names for doc in candidate(name)], sort_keys=False
        )
    )


if __name__ == "__main__":
    main()
