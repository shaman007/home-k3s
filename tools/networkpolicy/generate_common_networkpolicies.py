#!/usr/bin/env python3
"""Generate common Kubernetes NetworkPolicy bundles from compact specs."""

from __future__ import annotations

import argparse
import copy
from pathlib import Path
from typing import Any

import yaml


DNS_SELECTOR = {
    "namespaceSelector": {
        "matchLabels": {
            "kubernetes.io/metadata.name": "kube-system",
        },
    },
    "podSelector": {
        "matchLabels": {
            "k8s-app": "kube-dns",
        },
    },
}

DNS_PORTS = [
    {"protocol": "UDP", "port": 53},
    {"protocol": "TCP", "port": 53},
]

WEB_PORTS = [
    {"protocol": "TCP", "port": 80},
    {"protocol": "TCP", "port": 443},
]


class NoAliasDumper(yaml.SafeDumper):
    def ignore_aliases(self, data: Any) -> bool:
        return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate common NetworkPolicy YAML from a compact catalog."
    )
    parser.add_argument(
        "catalog",
        type=Path,
        help=(
            "Catalog YAML describing namespace, selector, output, and policies, "
            "or a directory of catalog YAML files."
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the generated bundle differs from the committed output.",
    )
    return parser.parse_args()


def catalog_paths(path: Path) -> list[Path]:
    if path.is_dir():
        return sorted(
            child
            for pattern in ("*.yaml", "*.yml")
            for child in path.glob(pattern)
            if child.is_file()
        )
    return [path]


def namespace_peer(namespace: str) -> dict[str, Any]:
    return {
        "namespaceSelector": {
            "matchLabels": {
                "kubernetes.io/metadata.name": namespace,
            },
        },
    }


def ip_block_peer(cidr: str) -> dict[str, Any]:
    return {"ipBlock": {"cidr": cidr}}


def base_policy(spec: dict[str, Any], name: str, policy_types: list[str]) -> dict[str, Any]:
    return {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "NetworkPolicy",
        "metadata": {
            "name": f"{spec['namePrefix']}-{name}",
            "namespace": spec["namespace"],
        },
        "spec": {
            "podSelector": (
                {"matchLabels": spec["podSelector"]} if spec.get("podSelector") else {}
            ),
            "policyTypes": policy_types,
        },
    }


def normalize_ports(policy_spec: dict[str, Any]) -> list[dict[str, Any]] | None:
    ports = policy_spec.get("ports")
    if ports is None:
        port = policy_spec.get("port")
        if port is None:
            return None
        ports = [{"protocol": policy_spec.get("protocol", "TCP"), "port": port}]
    return ports


def build_policy(spec: dict[str, Any], policy_spec: dict[str, Any]) -> dict[str, Any]:
    policy_type = policy_spec["type"]

    if policy_type == "default-deny":
        return base_policy(spec, "default-deny", ["Ingress", "Egress"])

    if policy_type == "dns-egress":
        policy = base_policy(spec, "allow-egress-dns", ["Egress"])
        policy["spec"]["egress"] = [{"to": [DNS_SELECTOR], "ports": DNS_PORTS}]
        return policy

    if policy_type == "web-egress":
        name = policy_spec.get("name", "allow-egress-web")
        cidrs = policy_spec.get("cidrs", ["0.0.0.0/0", "::/0"])
        policy = base_policy(spec, name, ["Egress"])
        policy["spec"]["egress"] = [
            {"to": [ip_block_peer(cidr)], "ports": copy.deepcopy(WEB_PORTS)}
            for cidr in cidrs
        ]
        return policy

    if policy_type == "namespace-egress":
        name = policy_spec.get("name", "allow-egress-intra-namespace")
        namespace = policy_spec.get("namespace", spec["namespace"])
        policy = base_policy(spec, name, ["Egress"])
        rule: dict[str, Any] = {"to": [namespace_peer(namespace)]}
        ports = normalize_ports(policy_spec)
        if ports:
            rule["ports"] = ports
        policy["spec"]["egress"] = [rule]
        return policy

    if policy_type == "namespace-egresses":
        name = policy_spec["name"]
        policy = base_policy(spec, name, ["Egress"])
        rules = []
        for namespace in policy_spec["namespaces"]:
            rule: dict[str, Any] = {"to": [namespace_peer(namespace)]}
            ports = normalize_ports(policy_spec)
            if ports:
                rule["ports"] = ports
            rules.append(rule)
        policy["spec"]["egress"] = rules
        return policy

    if policy_type == "namespace-ingress":
        name = policy_spec.get("name", "allow-ingress-intra-namespace")
        namespace = policy_spec.get("namespace", spec["namespace"])
        policy = base_policy(spec, name, ["Ingress"])
        rule: dict[str, Any] = {"from": [namespace_peer(namespace)]}
        ports = normalize_ports(policy_spec)
        if ports:
            rule["ports"] = ports
        policy["spec"]["ingress"] = [rule]
        return policy

    if policy_type == "namespace-ingresses":
        name = policy_spec["name"]
        policy = base_policy(spec, name, ["Ingress"])
        rules = []
        for namespace in policy_spec["namespaces"]:
            rule: dict[str, Any] = {"from": [namespace_peer(namespace)]}
            ports = normalize_ports(policy_spec)
            if ports:
                rule["ports"] = ports
            rules.append(rule)
        policy["spec"]["ingress"] = rules
        return policy

    raise ValueError(f"Unsupported common policy type: {policy_type}")


def render_bundle(spec: dict[str, Any]) -> str:
    documents = [build_policy(spec, policy_spec) for policy_spec in spec["policies"]]
    rendered = yaml.dump_all(
        documents,
        Dumper=NoAliasDumper,
        explicit_start=True,
        sort_keys=False,
        default_flow_style=False,
    )
    header = (
        "# Generated by tools/networkpolicy/generate_common_networkpolicies.py.\n"
        "# Edit the catalog in tools/networkpolicy/common-policies/ instead.\n"
    )
    return header + rendered


def process_catalog(path: Path, check: bool) -> int:
    spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    output_path = Path(spec["output"])
    rendered = render_bundle(spec)

    if check:
        current = output_path.read_text(encoding="utf-8")
        if current != rendered:
            print(f"{output_path} is not up to date; regenerate from {path}.")
            return 1
        return 0

    output_path.write_text(rendered, encoding="utf-8")
    print(f"Wrote {output_path}")
    return 0


def main() -> int:
    args = parse_args()
    exit_code = 0
    for path in catalog_paths(args.catalog):
        exit_code = max(exit_code, process_catalog(path, args.check))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
