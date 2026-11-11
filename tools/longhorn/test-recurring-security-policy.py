#!/usr/bin/env python3
"""Evaluate the native policy's CEL/JSONPatch using the pinned Kyverno engine.

The CLI cannot load native MutatingAdmissionPolicy directly; only the wrapper
is converted to MutatingPolicy. Native binding and API type checks are separate.
"""

import argparse
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import yaml

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "backfill", ROOT / "tools/longhorn/backfill-recurring-security.py"
)
backfill = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backfill)


def fixture(name):
    """Build a synthetic manager-owned recurring CronJob with the pinned image and command."""
    return {
        "apiVersion": "batch/v1",
        "kind": "CronJob",
        "metadata": {
            "name": name,
            "namespace": "longhorn-system",
            "labels": {
                "longhorn.io/managed-by": "longhorn-manager",
                "recurring-job.longhorn.io": name,
            },
            "ownerReferences": [
                {
                    "apiVersion": "longhorn.io/v1beta2",
                    "kind": "RecurringJob",
                    "name": name,
                    "uid": "00000000-0000-0000-0000-000000000001",
                }
            ],
        },
        "spec": {
            "schedule": "0 0 * * *",
            "concurrencyPolicy": "Forbid",
            "jobTemplate": {
                "spec": {
                    "template": {
                        "spec": {
                            "serviceAccountName": "longhorn-service-account",
                            "restartPolicy": "Never",
                            "containers": [
                                {
                                    "name": name,
                                    "image": backfill.IMAGE,
                                    "command": [
                                        "longhorn-manager",
                                        "-d",
                                        "recurring-job",
                                        name,
                                        "--manager-url",
                                        "http://longhorn-backend:9500/v1",
                                    ],
                                    "resources": {"requests": {"memory": "64Mi"}},
                                    "securityContext": {"readOnlyRootFilesystem": True},
                                }
                            ],
                        }
                    }
                }
            },
        },
    }


def main():
    """Evaluate the native policy's CEL/JSONPatch using the pinned Kyverno engine."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kyverno", default="kyverno")
    args = parser.parse_args()
    if not "1.19.2" in subprocess.check_output([args.kyverno, "version"], text=True):
        raise AssertionError
    policy, binding = yaml.safe_load_all(
        (ROOT / "longhorn/policy-recurring-job-security.yaml").read_text()
    )
    names = policy["spec"]["matchConstraints"]["resourceRules"][0]["resourceNames"]
    policy["apiVersion"] = "policies.kyverno.io/v1"
    policy["kind"] = "MutatingPolicy"
    policy["spec"].pop("reinvocationPolicy")
    cases = []
    for name in names:
        doc = fixture(name)
        cases.append((doc, True))
        absent = fixture(name)
        absent["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"][0].pop(
            "securityContext"
        )
        cases.append((absent, True))
    for mutation in [
        "namespace",
        "name",
        "labels",
        "account",
        "image",
        "command",
        "extra-container",
        "init-container",
    ]:
        doc = fixture(names[0])
        ps = doc["spec"]["jobTemplate"]["spec"]["template"]["spec"]
        c = ps["containers"][0]
        if mutation == "namespace":
            doc["metadata"]["namespace"] = "unreviewed"
        if mutation == "name":
            doc = fixture("unreviewed")
        if mutation == "labels":
            doc["metadata"]["labels"] = {}
        if mutation == "account":
            ps["serviceAccountName"] = "unreviewed"
        if mutation == "image":
            c["image"] = "registry.invalid/changed:1"
        if mutation == "command":
            c["command"] = ["longhorn-manager", "daemon"]
        if mutation == "extra-container":
            ps["containers"].append({"name": "other", "image": backfill.IMAGE})
        if mutation == "init-container":
            ps["initContainers"] = [{"name": "other", "image": backfill.IMAGE}]
        cases.append((doc, False))
    with tempfile.TemporaryDirectory(prefix="longhorn-policy-cases-") as temp:
        temp = Path(temp)
        p = temp / "policy.yaml"
        p.write_text(yaml.safe_dump(policy))
        for i, (doc, changed) in enumerate(cases):
            r = temp / "resource.yaml"
            o = temp / "out.yaml"
            r.write_text(yaml.safe_dump(doc))
            result = subprocess.run(
                [args.kyverno, "apply", str(p), "--resource", str(r), "--output", str(o)],
                text=True,
                capture_output=True,
                timeout=30,
                check=False,
            )
            if not result.returncode == 0:
                raise AssertionError(result.stdout + result.stderr)
            if not "error: 0" in result.stdout:
                raise AssertionError(result.stdout)
            emitted = [d for d in yaml.safe_load_all(o.read_text()) if d] if o.exists() else []
            if changed:
                if not len(emitted) == 1:
                    raise AssertionError((i, result.stdout))
                if not emitted[0]["spec"] == backfill.expected_spec(doc):
                    raise AssertionError((i, emitted))
                # Idempotence matters because updates can be reinvoked.
                r.write_text(yaml.safe_dump(emitted[0]))
                o.unlink()
                subprocess.run(
                    [args.kyverno, "apply", str(p), "--resource", str(r), "--output", str(o)],
                    check=True,
                    capture_output=True,
                    timeout=30,
                )
                if (
                    not next((d for d in yaml.safe_load_all(o.read_text()) if d))["spec"]
                    == emitted[0]["spec"]
                ):
                    raise AssertionError
            else:
                if not (not emitted or emitted[0] == doc):
                    raise AssertionError((i, emitted))
            if o.exists():
                o.unlink()
    print(f"{len(cases)} CEL scope/mutation cases and {len(names) * 2} idempotence checks passed")


if __name__ == "__main__":
    main()
