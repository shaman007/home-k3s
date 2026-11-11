#!/usr/bin/env python3
"""Regression: audit actual Helm output after native prepull admission, not before."""

import argparse
import copy
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import yaml

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "audit", ROOT / "tools/kyverno/test-audit-policies.py"
)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rendered", type=Path, required=True)
    parser.add_argument("--kyverno", default="kyverno")
    args = parser.parse_args()
    if not ("1.19.2" in subprocess.check_output([args.kyverno, "version"], text=True)):
        raise AssertionError
    documents = [
        d
        for path in args.rendered.glob("*.yaml")
        for d in yaml.safe_load_all(path.read_text())
        if isinstance(d, dict)
    ]
    raw = copy.deepcopy(
        next(
            d
            for d in documents
            if d.get("kind") == "DaemonSet" and d["metadata"]["name"] == "longhorn-manager"
        )
    )
    raw["metadata"].setdefault("namespace", "longhorn-system")
    policies = [d for d in documents if d.get("kind") == "ValidatingPolicy"]
    if not ({d["metadata"]["name"] for d in policies} == audit.EXPECTED_POLICIES):
        raise AssertionError
    admitted = audit.admitted_longhorn_manager(raw, args.kyverno)
    original_spec = copy.deepcopy(admitted["spec"])
    helper = next(
        c
        for c in original_spec["template"]["spec"]["containers"]
        if c["name"] == "pre-pull-share-manager-image"
    )
    original_helper = next(
        c for c in raw["spec"]["template"]["spec"]["containers"] if c["name"] == helper["name"]
    )
    if "securityContext" in original_helper:
        helper["securityContext"] = copy.deepcopy(original_helper["securityContext"])
    else:
        helper.pop("securityContext", None)
    if not (original_spec == raw["spec"]):
        raise AssertionError("Admission changed more than the prepull context")
    if not (admitted != raw):
        raise AssertionError("This regression needs raw chart output, before native admission")
    skip = {p: "skip" for p in audit.EXPECTED_POLICIES}
    raw_expected = {p: "skip" if p == "disallow-privileged-containers" else "fail" for p in skip}
    mismatch = copy.deepcopy(raw)
    next(
        c
        for c in audit.pod_spec(mismatch)["containers"]
        if c["name"] == "pre-pull-share-manager-image"
    )["image"] = "registry.invalid/unreviewed:1"
    if not (audit.admitted_longhorn_manager(mismatch, args.kyverno) == mismatch):
        raise AssertionError
    unsafe = copy.deepcopy(admitted)
    next(
        c
        for c in audit.pod_spec(unsafe)["containers"]
        if c["name"] == "pre-pull-share-manager-image"
    )["securityContext"]["capabilities"]["add"] = ["SYS_ADMIN"]
    cases = [
        (raw, raw_expected),
        (admitted, skip),
        (mismatch, raw_expected),
        (unsafe, {**skip, "require-drop-all-capabilities": "fail"}),
    ]
    with tempfile.TemporaryDirectory(prefix="manager-admission-regression-") as directory:
        directory = Path(directory)
        (directory / "policies.yaml").write_text(yaml.safe_dump_all(policies))
        (directory / "exceptions.yaml").write_text(
            (ROOT / "kyverno/policy-exceptions-verified.yaml").read_text()
        )
        for index, (resource, expected) in enumerate(cases):
            folder = directory / str(index)
            folder.mkdir()
            (folder / "resource.yaml").write_text(yaml.safe_dump(resource))
            (folder / "kyverno-test.yaml").write_text(
                yaml.safe_dump(
                    {
                        "apiVersion": "cli.kyverno.io/v1alpha1",
                        "kind": "Test",
                        "metadata": {"name": "manager-" + str(index)},
                        "policies": ["../policies.yaml"],
                        "exceptions": ["../exceptions.yaml"],
                        "resources": ["resource.yaml"],
                        "results": [
                            {
                                "policy": p,
                                "kind": resource["kind"],
                                "resources": [resource["metadata"]["name"]],
                                "result": r,
                            }
                            for p, r in expected.items()
                        ],
                    }
                )
            )
        subprocess.run(
            [args.kyverno, "test", str(directory), "--fail-only", "--remove-color"], check=True
        )
    print(
        "20 real CEL expectations passed: raw chart, admitted chart, unmatched image and unsafe helper"
    )


if __name__ == "__main__":
    main()
