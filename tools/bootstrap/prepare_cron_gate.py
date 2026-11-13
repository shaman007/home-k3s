#!/usr/bin/env python3
"""Render an inactive logs-check candidate without editing the active CronJob."""

import argparse
import copy
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def candidate():
    """Wrap existing work in-place; never gate the cluster health reporter."""
    original = yaml.safe_load((ROOT / "metrics/cron-job-logs-check.yaml").read_text())
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
            "configMap": {"name": "logs-check-dependencies"},
        }
    )
    # Hard Pod/Job ceiling also covers image pulls, a stuck probe and application work.
    job["spec"]["jobTemplate"]["spec"]["activeDeadlineSeconds"] = 14400
    config = {
        "mode": "skip",
        "budget_seconds": 300,
        "interval_seconds": 5,
        "probe_seconds": 5,
        "checks": [
            {
                "name": "loki",
                "url": "http://loki-gateway.loki.svc.cluster.local/loki/api/v1/labels",
            },
            {
                "name": "ollama",
                "url": "http://ollama.ollama.svc.cluster.local:11434/api/tags",
            },
        ],
    }
    config_map = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {"name": "logs-check-dependencies", "namespace": "monitoring"},
        "data": {
            "gate.py": (ROOT / "tools/bootstrap/cron_dependency_gate.py").read_text(),
            "config.json": json.dumps(config, indent=2),
        },
    }
    return [config_map, job]


def main():
    """Print the proposal only; active Argo sources are never written."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    print(yaml.safe_dump_all(candidate(), sort_keys=False))


if __name__ == "__main__":
    main()
