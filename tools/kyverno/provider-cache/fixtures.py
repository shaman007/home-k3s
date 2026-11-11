#!/usr/bin/env python3
"""Prepare scanner equivalence fixtures from read-only API snapshots and the reviewed catalog."""

import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[3]
out = Path(sys.argv[1]).resolve()
out.mkdir(parents=True, exist_ok=True)
for resource, filename, extra in [
    ("validatingpolicies.policies.kyverno.io", "policies", []),
    ("policyexceptions.policies.kyverno.io", "exceptions", ["-n", "kyverno"]),
]:
    data = json.loads(subprocess.check_output(["kubectl", "get", resource, *extra, "-o", "json"]))[
        "items"
    ]
    for document in data:
        document.pop("status", None)
    (out / f"kyverno-cache-{filename}.json").write_text(json.dumps(data))
spec = importlib.util.spec_from_file_location(
    "audit", root / "tools/kyverno/test-audit-policies.py"
)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
resources = []
for entry in json.loads((root / "kyverno/exception-catalog.json").read_text())["entries"]:
    for document in (audit.snapshot(entry), audit.derived_pod(entry)):
        resources.append(document)
        changed = copy.deepcopy(document)
        audit.pod_spec(changed)["containers"][0].setdefault("securityContext", {})["privileged"] = (
            True
        )
        resources.append(changed)
(out / "kyverno-cache-resources.json").write_text(json.dumps(resources))
print(f"Prepared {len(resources)} resource cases in {out}")
