#!/usr/bin/env python3
"""Exercise the native component policy's CEL/JSONPatch through Kyverno 1.19.2."""

import argparse
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import yaml

ROOT = Path(__file__).resolve().parents[2]
s = importlib.util.spec_from_file_location(
    "backfill", ROOT / "tools/longhorn/backfill-component-security.py"
)
b = importlib.util.module_from_spec(s)
s.loader.exec_module(b)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--kyverno", default="kyverno")
    args = parser.parse_args()
    if not "1.19.2" in subprocess.check_output([args.kyverno, "version"], text=True):
        raise AssertionError
    policy, _ = yaml.safe_load_all((ROOT / "longhorn/policy-component-security.yaml").read_text())
    policy["apiVersion"] = "policies.kyverno.io/v1"
    policy["kind"] = "MutatingPolicy"
    policy["spec"].pop("reinvocationPolicy")
    entries = json.loads((ROOT / "longhorn/component-security-catalog.json").read_text())["entries"]
    cases = []
    for entry in entries:
        for initial in ["missing", "existing"]:
            doc = copy.deepcopy(entry["fixture"])
            c = doc["spec"]["template"]["spec"]["containers"][entry["index"]]
            if initial == "missing":
                c.pop("securityContext", None)
            else:
                c["securityContext"] = {
                    "readOnlyRootFilesystem": True,
                    "capabilities": {"add": ["SYS_ADMIN"]},
                }
            cases.append((entry, doc, True))
        for mutation in [
            "namespace",
            "name",
            "labels",
            "account",
            "image",
            "args",
            "command",
            "extra-container",
            "init-container",
        ]:
            doc = copy.deepcopy(entry["fixture"])
            pod = doc["spec"]["template"]["spec"]
            c = pod["containers"][entry["index"]]
            if mutation == "namespace":
                doc["metadata"]["namespace"] = "unreviewed"
            if mutation == "name":
                doc["metadata"]["name"] = "unreviewed"
            if mutation == "labels":
                doc["spec"]["template"]["metadata"]["labels"] = {"app": "unreviewed"}
            if mutation == "account":
                pod["serviceAccountName"] = "unreviewed"
            if mutation == "image":
                c["image"] = "registry.invalid/changed:1"
            if mutation == "args":
                c["args"] = ["--unreviewed"]
            if mutation == "command":
                c["command"] = ["unreviewed"]
            if mutation == "extra-container":
                pod["containers"].append(
                    {"name": "unreviewed", "image": "registry.invalid/changed:1"}
                )
            if mutation == "init-container":
                pod["initContainers"] = [
                    {"name": "unreviewed", "image": "registry.invalid/changed:1"}
                ]
            cases.append((entry, doc, False))
        if entry["kind"] == "DaemonSet":
            doc = copy.deepcopy(entry["fixture"])
            doc["spec"]["template"]["spec"]["containers"][0]["image"] = "registry.invalid/changed:1"
            cases.append((entry, doc, False))
            doc = copy.deepcopy(entry["fixture"])
            pod = doc["spec"]["template"]["spec"]
            pod["containers"][0], pod["containers"][1] = pod["containers"][1], pod["containers"][0]
            cases.append((entry, doc, False))
    with tempfile.TemporaryDirectory(prefix="longhorn-component-tests-") as temp:
        temp = Path(temp)
        p = temp / "policy.yaml"
        p.write_text(yaml.safe_dump(policy))

        def evaluate(doc):
            r = temp / "resource.yaml"
            o = temp / "out.yaml"
            r.write_text(yaml.safe_dump(doc))
            if o.exists():
                o.unlink()
            result = subprocess.run(
                [args.kyverno, "apply", str(p), "--resource", str(r), "--output", str(o)],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if not (result.returncode == 0 and "error: 0" in result.stdout):
                raise AssertionError(result.stdout + result.stderr)
            docs = [d for d in yaml.safe_load_all(o.read_text()) if d] if o.exists() else []
            if not len(docs) <= 1:
                raise AssertionError
            return docs[0] if docs else doc

        for entry, doc, changed in cases:
            output = evaluate(doc)
            if changed:
                if not output["spec"] == b.expected_spec(doc, entry):
                    raise AssertionError(
                        (
                            entry["name"],
                            "unexpected spec changes",
                        )
                    )
                if not evaluate(output) == output:
                    raise AssertionError((entry["name"], "not idempotent"))
            else:
                if not output == doc:
                    raise AssertionError((entry["name"], "mutated out-of-scope resource"))
    print(
        f"{len(cases)} component mutation/scope checks and {len(entries) * 2} idempotence checks passed"
    )


if __name__ == "__main__":
    main()
