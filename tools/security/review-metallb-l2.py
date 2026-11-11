#!/usr/bin/env python3
"""Read-only review of the pinned MetalLB chart's staged L2 migration.

Never prints rendered Secrets and never mutates Kubernetes resources.
"""

import argparse
import copy
import json
from pathlib import Path
import subprocess
import tempfile

import yaml

ROOT = Path(__file__).resolve().parents[2]


def run(*args):
    return subprocess.check_output(args, text=True)


def key(doc):
    return doc["kind"], doc["metadata"]["name"]


def render(chart, values):
    with tempfile.TemporaryDirectory(prefix="metallb-l2-review-") as directory:
        path = Path(directory) / "values.yaml"
        path.write_text(yaml.safe_dump(values))
        docs = yaml.safe_load_all(
            run(
                "helm",
                "template",
                "metallb",
                str(chart),
                "--namespace",
                "metallb-system",
                "--include-crds",
                "--values",
                str(path),
            )
        )
        # Ignore generated certificate/memberlist material, even when comparing.
        return {key(doc): doc for doc in docs if doc and doc["kind"] != "Secret"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chart", type=Path, required=True, help="Unpacked MetalLB 0.16.1 chart")
    parser.add_argument(
        "--live", action="store_true", help="Also inspect live configuration, read-only"
    )
    args = parser.parse_args()
    chart = yaml.safe_load((args.chart / "Chart.yaml").read_text())
    if not (chart["name"] == "metallb" and chart["version"] == "0.16.1"):
        raise AssertionError("Unreviewed chart")
    app = yaml.safe_load((ROOT / "argocd/application-metallb.yaml").read_text())
    if not app["spec"]["source"]["targetRevision"] == chart["version"]:
        raise AssertionError
    if not app["spec"]["syncPolicy"]["automated"]["prune"] is False:
        raise AssertionError("Migration must not auto-prune")
    values = yaml.safe_load(app["spec"]["source"]["helm"]["values"])
    if not values["loadBalancerClass"] == "metallb-l2":
        raise AssertionError
    if not values["frrk8s"] == {"enabled": False, "external": False}:
        raise AssertionError
    if not values["speaker"]["frr"]["enabled"] is False:
        raise AssertionError
    previous = copy.deepcopy(values)
    previous["frrk8s"]["enabled"] = True
    before, after = render(args.chart, previous), render(args.chart, values)
    if not not after.keys() - before.keys():
        raise AssertionError("Unexpected new resources")
    removed = sorted(before.keys() - after.keys())
    inventory = json.loads(
        (ROOT / "tools/security/metallb-frr-retirement-inventory.json").read_text()
    )
    expected = {
        (entry["kind"], entry["name"]) for entry in inventory["retire"] + inventory["retain"]
    }
    # The subchart also generates one TLS Secret; it is intentionally not read.
    expected.discard(("Secret", "frr-k8s-webhook-server-cert"))
    if not set(removed) == expected:
        raise AssertionError("Retirement inventory differs from chart")
    changed = []
    for identity in before.keys() & after.keys():
        original, actual = copy.deepcopy(before[identity]), after[identity]
        if original == actual:
            continue
        changed.append(identity)
        if identity in [("DaemonSet", "metallb-speaker"), ("Deployment", "metallb-controller")]:
            for container in original["spec"]["template"]["spec"]["containers"]:
                container["env"] = [
                    env for env in container.get("env", []) if env["name"] != "METALLB_BGP_TYPE"
                ]
        elif identity == ("ClusterRole", "metallb:speaker"):
            original["rules"] = [
                rule for rule in original["rules"] if rule.get("apiGroups") != ["frrk8s.metallb.io"]
            ]
        else:
            raise AssertionError("Unexpected changed resource: " + str(identity))
        if not original == actual:
            raise AssertionError("Unexpected change within " + str(identity))
    if not len(changed) == 3:
        raise AssertionError("Expected only controller/speaker backend and speaker RBAC changes")
    speaker = after[("DaemonSet", "metallb-speaker")]["spec"]
    pod = speaker["template"]["spec"]
    if not pod["securityContext"] == {
        "runAsNonRoot": False,
        "runAsUser": 0,
        "runAsGroup": 0,
        "seccompProfile": {"type": "RuntimeDefault"},
    }:
        raise AssertionError("Retain the reviewed root identity")
    if not speaker["updateStrategy"] == {
        "type": "RollingUpdate",
        "rollingUpdate": {"maxUnavailable": 1},
    }:
        raise AssertionError
    if not (pod["hostNetwork"] is True and (not pod.get("hostPID")) and (not pod.get("hostIPC"))):
        raise AssertionError
    if not not pod.get("initContainers"):
        raise AssertionError("Unexpected speaker init container")
    if not len(pod["containers"]) == 1:
        raise AssertionError
    container = pod["containers"][0]
    if not container["securityContext"] == {
        "allowPrivilegeEscalation": False,
        "readOnlyRootFilesystem": True,
        "capabilities": {"drop": ["ALL"], "add": ["NET_RAW"]},
    }:
        raise AssertionError("Required raw L2 capability changed")
    if not all((port["containerPort"] > 1024 for port in container["ports"])):
        raise AssertionError
    if not all((set(volume) <= {"name", "secret", "configMap"} for volume in pod["volumes"])):
        raise AssertionError("fsGroup review excludes persistent/host volumes")
    exclude = next(volume for volume in pod["volumes"] if volume["name"] == "metallb-excludel2")
    if not exclude["configMap"]["defaultMode"] == 256:
        raise AssertionError("Unexpected config mode")
    print(
        "Restored speaker identity, NET_RAW, projected-only volumes and one-at-a-time rollout verified."
    )
    print(
        "Chart review passed: 3 narrowly changed resources; 17 FRR resources leave desired state, including 4 retained CRDs."
    )
    if args.live:

        def get(resource, namespace=None):
            command = ["kubectl", "get", resource, "--request-timeout=15s", "-o", "json"]
            command += ["-n", namespace] if namespace else ["-A"]
            return json.loads(run(*command))["items"]

        for resource in [
            "bgppeers.metallb.io",
            "bgpadvertisements.metallb.io",
            "frrconfigurations.frrk8s.metallb.io",
            "frrk8sconfigurations.frrk8s.metallb.io",
        ]:
            if not not get(resource):
                raise AssertionError("BGP/FRR configuration exists: " + resource)
        ads = get("l2advertisements.metallb.io", "metallb-system")
        pools = get("ipaddresspools.metallb.io", "metallb-system")
        if not (ads and pools):
            raise AssertionError("L2 configuration missing")
        services = [
            service for service in get("services") if service["spec"].get("type") == "LoadBalancer"
        ]
        if not services:
            raise AssertionError("No LoadBalancer services")
        for service in services:
            if not service["spec"].get("loadBalancerClass") == "metallb-l2":
                raise AssertionError("Unexpected LoadBalancer class")
            if not service.get("status", {}).get("loadBalancer", {}).get("ingress"):
                raise AssertionError("Unassigned LoadBalancer")
        print(
            f"Live prerequisites passed: no BGP/FRR configs; {len(pools)} pools, {len(ads)} L2 advertisements, {len(services)} assigned L2 services."
        )
        print(
            "This does not prove post-rollout ARP/NDP reachability. Verify from the LAN after backend or identity changes."
        )


if __name__ == "__main__":
    main()
