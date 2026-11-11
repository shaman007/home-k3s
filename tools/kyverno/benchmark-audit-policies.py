#!/usr/bin/env python3
"""Compare prepared legacy/sharded audit fixtures and benchmark identical assertions.

Inputs must be sanitized CLI fixtures, never full rendered application bundles.
Run outside CI; the normal validation workflow always executes the full suite.
"""

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

import yaml


def read_tests(root):
    """Load fixture assertions and reject ambiguous or missing resource matches."""
    tests = []
    for file in sorted(root.rglob("kyverno-test.yaml")):
        test = yaml.safe_load(file.read_text())
        resources = [
            doc
            for name in test["resources"]
            for doc in yaml.safe_load_all((file.parent / name).read_text())
            if doc
        ]
        assertions = []
        for result in test["results"]:
            for name in result["resources"]:
                matches = [
                    doc
                    for doc in resources
                    if doc["kind"] == result["kind"]
                    and doc["metadata"]["name"] == name
                    and (
                        "namespace" not in result
                        or doc["metadata"].get("namespace") == result["namespace"]
                    )
                ]
                if len(matches) != 1:
                    raise ValueError(f"Ambiguous/missing resource in {file}: {name}")
                doc = matches[0]
                key = json.dumps([doc, result["policy"], result["result"]], sort_keys=True)
                assertions.append((key, doc, {**result, "resources": [name]}))
        tests.append((file, test, assertions))
    if not tests or not any(t[2] for t in tests):
        raise ValueError(f"No assertions in {root}")
    return tests


def coverage(tests):
    """Count the exact resource, policy, and expected-result assertion combinations."""
    return Counter(key for _, _, assertions in tests for key, _, _ in assertions)


def policy_scopes(tests):
    """Match the engine's policyRef filter, retaining all cross-workload exceptions."""
    documents, scopes = {}, {}

    def load(file):
        file = file.resolve()
        if file not in documents:
            documents[file] = [d for d in yaml.safe_load_all(file.read_text()) if d]
        return documents[file]

    for file, test, _ in tests:
        exceptions = [e for name in test["exceptions"] for e in load(file.parent / name)]
        for name in test["policies"]:
            for policy in load(file.parent / name):
                relevant = [
                    e
                    for e in exceptions
                    if any(
                        r["name"] == policy["metadata"]["name"] and r["kind"] == policy["kind"]
                        for r in e["spec"]["policyRefs"]
                    )
                ]
                scope = json.dumps([policy, relevant], sort_keys=True)
                key = policy["metadata"]["name"]
                if key in scopes and scopes[key] != scope:
                    raise ValueError(f"Inconsistent policy or exception scope for {key}")
                scopes[key] = scope
    return scopes


def subset(tests, keys, output):
    """Write selected assertions while preserving their original policies and exceptions."""
    output.mkdir()
    for index, (file, test, assertions) in enumerate(tests):
        selected = [(doc, ref) for key, doc, ref in assertions if key in keys]
        if not selected:
            continue
        folder = output / f"case-{index:04d}"
        folder.mkdir()
        test = dict(test)
        # Keep the original policies/exceptions for each variant. Only resource
        # selection changes, never policy contents or exception matching scope.
        for section in ["policies", "exceptions"]:
            paths = []
            for i, name in enumerate(test[section]):
                target = f"{section}-{i}.yaml"
                (folder / target).write_text((file.parent / name).read_text())
                paths.append(target)
            test[section] = paths
        documents = {json.dumps(doc, sort_keys=True): doc for doc, _ in selected}
        (folder / "resources.yaml").write_text(
            yaml.safe_dump_all(documents.values(), sort_keys=False)
        )
        test["resources"] = ["resources.yaml"]
        test["results"] = [ref for _, ref in selected]
        (folder / "kyverno-test.yaml").write_text(yaml.safe_dump(test, sort_keys=False))


def main():
    """Compare prepared legacy/sharded audit fixtures and benchmark identical assertions."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--optimized", type=Path, required=True)
    parser.add_argument(
        "--output", type=Path, required=True, help="New private benchmark directory"
    )
    parser.add_argument("--kyverno", default="kyverno")
    parser.add_argument(
        "--sample-every",
        type=int,
        default=20,
        help="Take every Nth sorted assertion; 1 benchmarks the full suites",
    )
    parser.add_argument(
        "--gomaxprocs", type=int, default=2, help="Identical CPU budget for both variants"
    )
    args = parser.parse_args()
    if args.sample_every < 1 or args.gomaxprocs < 1:
        parser.error("Sampling interval and CPU budget must be positive")
    version = subprocess.check_output([args.kyverno, "version"], text=True)
    if "1.19.2" not in version:
        parser.error("Benchmark requires the pinned Kyverno CLI 1.19.2")
    tests = {
        name: read_tests(path)
        for name, path in [("baseline", args.baseline), ("optimized", args.optimized)]
    }
    original = coverage(tests["baseline"])
    if original != coverage(tests["optimized"]):
        raise ValueError("Fixture coverage differs; refusing a misleading benchmark")
    scopes = policy_scopes(tests["baseline"])
    if scopes != policy_scopes(tests["optimized"]):
        raise ValueError("Policy contents or applicable exception scope differs")
    keys = set(sorted(original)[:: args.sample_every])
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    report = {
        "version": version.strip(),
        "full_assertions": sum(original.values()),
        "coverage_sha256": hashlib.sha256(
            json.dumps(sorted(original.items())).encode()
        ).hexdigest(),
        "scope_sha256": hashlib.sha256(json.dumps(scopes, sort_keys=True).encode()).hexdigest(),
        "sample_every": args.sample_every,
        "GOMAXPROCS": args.gomaxprocs,
        "runs": {},
    }
    for name in tests:
        path = args.output / name
        subset(tests[name], keys, path)
    sampled = coverage(read_tests(args.output / "baseline"))
    if not sampled == coverage(read_tests(args.output / "optimized")):
        raise AssertionError
    report["sample_assertions"] = sum(sampled.values())
    for name in tests:
        start = time.monotonic()
        with (args.output / f"{name}.log").open("w") as log:
            result = subprocess.run(
                [
                    args.kyverno,
                    "test",
                    str(args.output / name),
                    "--fail-only",
                    "--remove-color",
                    "--require-tests",
                ],
                stdout=log,
                stderr=subprocess.STDOUT,
                env={**os.environ, "GOMAXPROCS": str(args.gomaxprocs)},
                check=False,
            )
        report["runs"][name] = {
            "seconds": time.monotonic() - start,
            "returncode": result.returncode,
        }
        (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        print(f"{name}: {report['runs'][name]}", flush=True)
        if result.returncode:
            raise SystemExit(result.returncode)
    report["speedup"] = (
        report["runs"]["baseline"]["seconds"] / report["runs"]["optimized"]["seconds"]
    )
    (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
