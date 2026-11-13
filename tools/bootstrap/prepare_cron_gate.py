#!/usr/bin/env python3
"""Render report gates or explicitly regenerate their local Git sources."""

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
COMMANDS = {
    "logs-check": ["python3", "/scripts/logs-check.py"],
    "external-access-daily-report": [
        "python3",
        "/opt/external-access-daily-report/external-access-daily-report.py",
    ],
    "wordpress-daily-report": ["python3", "/scripts/wordpress-daily-report.py"],
}


def candidate(name="logs-check"):
    """Wrap existing work in-place; never gate the cluster health reporter."""
    path, deadline, checks = REPORTS[name]
    original = yaml.safe_load((ROOT / path).read_text())
    job = copy.deepcopy(original)
    pod = job["spec"]["jobTemplate"]["spec"]["template"]["spec"]
    container = pod["containers"][0]
    desired = [
        "python3",
        "/opt/cron-dependencies/gate.py",
        "--config",
        "/opt/cron-dependencies/config.json",
        "--job",
        name,
    ]
    if container.get("command") not in (COMMANDS[name], desired) or container.get(
        "args"
    ):
        raise ValueError("Review changed report command before wrapping")
    container["command"] = desired
    container["volumeMounts"] = [
        m for m in container.get("volumeMounts", []) if m["name"] != "cron-dependencies"
    ]
    pod["volumes"] = [
        v for v in pod.get("volumes", []) if v["name"] != "cron-dependencies"
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
    """Render, verify or explicitly write local sources; never call the cluster."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", choices=[*REPORTS, "all"], default="logs-check")
    parser.add_argument("--write-source", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    names = list(REPORTS) if args.job == "all" else [args.job]
    if args.write_source and args.check:
        parser.error("Choose write-source or check")
    if args.write_source or args.check:
        for name in names:
            cm, job = candidate(name)
            path = ROOT / REPORTS[name][0]
            cm_path = path.parent / ("config-map-" + cm["metadata"]["name"] + ".yaml")
            if args.write_source:
                path.write_text(yaml.safe_dump(job, sort_keys=False))
                cm_path.write_text(yaml.safe_dump(cm, sort_keys=False))
            elif (
                yaml.safe_load(path.read_text()) != job
                or not cm_path.exists()
                or yaml.safe_load(cm_path.read_text()) != cm
            ):
                raise ValueError("Report gate source differs: " + name)
        print(
            "Report gate sources checked"
            if args.check
            else "Report gate sources updated"
        )
        return
    print(
        yaml.safe_dump_all(
            [doc for name in names for doc in candidate(name)], sort_keys=False
        )
    )


if __name__ == "__main__":
    main()
