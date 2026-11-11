#!/usr/bin/env python3
"""Prepare scanner equivalence fixtures from read-only API snapshots and the reviewed catalog."""

import argparse
import copy
import importlib.util
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]


def resource_cases(root):
    """Keep reviewed workloads, derived Pods and their deliberately privileged variants."""
    spec = importlib.util.spec_from_file_location(
        "audit", root / "tools/kyverno/test_audit_policies.py"
    )
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    resources = []
    for entry in json.loads((root / "kyverno/exception-catalog.json").read_text())["entries"]:
        for document in (audit.snapshot(entry), audit.derived_pod(entry)):
            resources.append(document)
            changed = copy.deepcopy(document)
            audit.pod_spec(changed)["containers"][0].setdefault("securityContext", {})[
                "privileged"
            ] = True
            resources.append(changed)
    return resources


def main():
    """Collect complete bounded read-only snapshots before replacing fixture files."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    reports = {}
    for resource, filename, extra in [
        ("validatingpolicies.policies.kyverno.io", "policies", []),
        ("policyexceptions.policies.kyverno.io", "exceptions", ["-n", "kyverno"]),
    ]:
        data = json.loads(
            subprocess.check_output(
                ["kubectl", "get", resource, *extra, "-o", "json", "--request-timeout=15s"],
                shell=False,
                timeout=30,
            )
        )["items"]
        for document in data:
            document.pop("status", None)
        reports[filename] = data
    reports["resources"] = resource_cases(ROOT)
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    for name, documents in reports.items():
        (out / f"kyverno-cache-{name}.json").write_text(json.dumps(documents))
    print(f"Prepared {len(reports['resources'])} resource cases in {out}")


if __name__ == "__main__":
    main()
