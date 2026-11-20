"""Protect the report's secret scope and Valkey's effective network boundary."""

from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]


def load(relative):
    """Read one Kubernetes manifest."""
    return yaml.safe_load((ROOT / relative).read_text(encoding="utf-8"))


def matches(selector, labels):
    """Evaluate the label selectors used by the Dawarich policies."""
    if any(labels.get(key) != value for key, value in selector.get("matchLabels", {}).items()):
        return False
    for expr in selector.get("matchExpressions", []):
        if expr["operator"] != "In":
            raise AssertionError("Extend selector evaluation for this operator")
        if labels.get(expr["key"]) not in expr["values"]:
            return False
    return True


def valkey_allows(namespace, labels, port, direction="Ingress"):
    """Evaluate the union of all matching policies, including broader allows."""
    selected = []
    for path in (ROOT / "dawarich").glob("network-policy-*.yaml"):
        spec = yaml.safe_load(path.read_text())["spec"]
        if direction in spec["policyTypes"] and matches(
            spec["podSelector"], {"app": "valkey-dawarich"}):
            selected.append(spec)
    if not selected:
        return True
    for spec in selected:
        for rule in spec.get(direction.lower(), []):
            if "ports" in rule and not any(
                item["port"] == port and item.get("protocol", "TCP") == "TCP"
                for item in rule["ports"]
            ):
                continue
            peer_key = "from" if direction == "Ingress" else "to"
            if peer_key not in rule:
                return True
            for peer in rule[peer_key]:
                if "ipBlock" in peer:
                    raise AssertionError("Extend peer evaluation for IP blocks")
                ns_matches = matches(peer["namespaceSelector"], {
                    "kubernetes.io/metadata.name": namespace
                }) if "namespaceSelector" in peer else namespace == "dawarich"
                if ns_matches and matches(peer.get("podSelector", {}), labels):
                    return True
    return False


class AuditAccessBoundariesTest(unittest.TestCase):
    """Keep required clients working while rejecting unrelated access."""

    def test_report_secret_access_is_named_and_namespaced(self):
        """Inventory access must not grant access to every application's credentials."""
        cluster_role = load("metrics/cluster-role-platform-health-report.yaml")
        for rule in cluster_role["rules"]:
            self.assertFalse({"secrets", "*"} & set(rule["resources"]))
        role = load("mail/role-platform-health-report-mail-tls.yaml")
        binding = load("mail/role-binding-platform-health-report-mail-tls.yaml")
        self.assertEqual("mail", role["metadata"]["namespace"])
        self.assertEqual("mail", binding["metadata"]["namespace"])
        self.assertEqual(role["metadata"]["name"], binding["roleRef"]["name"])
        self.assertEqual([{"kind": "ServiceAccount", "name": "platform-health-report",
                           "namespace": "monitoring"}], binding["subjects"])
        self.assertEqual([{"apiGroups": [""], "resources": ["secrets"],
                           "resourceNames": ["mail-tls"], "verbs": ["get"]}], role["rules"])

    def test_valkey_accepts_application_and_metrics_clients(self):
        """Preserve application requests and the Prometheus scrape."""
        self.assertTrue(valkey_allows("dawarich", {"app": "dawarich"}, 6379))
        self.assertTrue(valkey_allows("monitoring", {"app": "prometheus-server"}, 9121))

    def test_valkey_rejects_unrelated_and_outbound_connections(self):
        """Namespace membership and client labels alone must not bypass the boundary."""
        for namespace, labels, port in [
            ("unrelated", {"app": "dawarich"}, 6379),
            ("dawarich", {"app": "photon"}, 6379),
            ("monitoring", {"app": "prometheus-server"}, 6379),
            ("monitoring", {"app": "other"}, 9121),
            ("unrelated", {"app": "prometheus-server"}, 9121),
        ]:
            with self.subTest(namespace=namespace, labels=labels, port=port):
                self.assertFalse(valkey_allows(namespace, labels, port))
        self.assertFalse(valkey_allows("unrelated", {}, 443, "Egress"))


if __name__ == "__main__":
    unittest.main()
