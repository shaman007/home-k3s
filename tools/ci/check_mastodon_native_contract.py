"""Compare inactive native objects with the current chart render, without exposing env values."""

import argparse
import copy
from pathlib import Path

import yaml

KINDS = {"Deployment", "Service", "ServiceAccount", "ConfigMap"}
GATES = {"wait-for-data-services", "migrate-schema", "wait-for-schema"}


def load(path):
    """Ignore hook objects and never retain rendered Secret payloads in the contract."""
    return {
        (d["kind"], d["metadata"]["name"]): d
        for d in yaml.safe_load_all(path.read_text())
        if isinstance(d, dict)
        and d.get("kind") in KINDS
        and not d["metadata"].get("annotations", {}).get("helm.sh/hook")
    }


def normalize_deployment(document):
    """Remove only deliberate startup/maintenance changes, not application behavior."""
    spec = copy.deepcopy(document["spec"])
    spec.pop("strategy", None)  # Candidate is explicitly Recreate, checked separately.
    template = spec["template"]
    annotations = template["metadata"].get("annotations", {})
    annotations.pop("checksum/mastodon-startup", None)
    if not annotations:
        template["metadata"].pop("annotations", None)
    pod = template["spec"]
    pod.pop("automountServiceAccountToken", None)
    pod["volumes"] = [
        v for v in (pod.get("volumes") or []) if v["name"] != "startup-gate"
    ]
    pod["initContainers"] = [
        c for c in (pod.get("initContainers") or []) if c["name"] not in GATES
    ]
    for container in pod["containers"]:
        container["image"] = container["image"].split("@", 1)[0]
    return spec


def check(baseline, candidate):
    """Report only resource identities; never include expected/observed Secret refs or env data."""
    errors = []
    expected = set(baseline)
    actual = set(candidate) - {("ConfigMap", "mastodon-startup-gate")}
    if expected != actual:
        errors.append("Native resource inventory differs from chart contract")
    for identity in expected & actual:
        old, new = baseline[identity], candidate[identity]
        kind, name = identity
        if kind == "Deployment":
            if new["spec"].get("strategy") != {"type": "Recreate"}:
                errors.append(name + ": maintenance strategy must be Recreate")
            if any(
                "@sha256:" not in c["image"]
                for c in new["spec"]["template"]["spec"]["containers"]
            ):
                errors.append(name + ": app images must retain a reviewed digest")
            if normalize_deployment(old) != normalize_deployment(new):
                errors.append(name + ": original workload contract changed")
        elif kind == "ConfigMap" and old.get("data") != new.get("data"):
            errors.append(name + ": application environment changed")
        elif kind == "Service" and old.get("spec") != new.get("spec"):
            errors.append(name + ": service/selector contract changed")
        elif (
            kind == "ServiceAccount"
            and new.get("automountServiceAccountToken") is not False
        ):
            errors.append(name + ": unused API token must remain disabled")
    return errors


def main():
    """Validate native preparation against the still-active chart until cutover."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    args = parser.parse_args()
    errors = check(load(args.baseline), load(args.candidate))
    if errors:
        raise SystemExit("\n".join(errors))
    print("Native Mastodon retains chart application/service/environment contract")


if __name__ == "__main__":
    main()
