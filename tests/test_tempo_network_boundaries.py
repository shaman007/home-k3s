"""Keep tracing transport permissions scoped while preserving existing traffic."""

from pathlib import Path
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]


class TempoNetworkBoundariesTest(unittest.TestCase):
    """Guard the unauthenticated tracing backend and non-isolated exporters."""

    def test_ingress_requires_specific_pods_and_transport(self):
        """A namespace alone must not grant access to Tempo receivers."""
        doc = yaml.safe_load((ROOT / "tempo/network-policy-tempo.yaml").read_text())
        for rule in doc["spec"]["ingress"]:
            for peer in rule["from"]:
                with self.subTest(peer=peer):
                    self.assertTrue(peer.get("podSelector"))
                    self.assertNotIn("ipBlock", peer)
                    for port in rule["ports"]:
                        self.assertIn(
                            (port["protocol"], port["port"]),
                            {("TCP", 3200), ("TCP", 4317), ("TCP", 4318),
                             ("TCP", 9411), ("UDP", 6831)},
                        )
                        if port["port"] != 3200:
                            self.assertTrue(peer.get("namespaceSelector"))

    def test_export_egress_targets_only_tempo(self):
        """Trace-specific allows must not open arbitrary monitoring services."""
        paths = list(ROOT.glob("*/network-policy-*-allow-egress-tempo.yaml"))
        self.assertTrue(paths)
        for path in paths:
            doc = yaml.safe_load(path.read_text())
            with self.subTest(path=path):
                self.assertTrue(doc["spec"]["podSelector"])
                for rule in doc["spec"]["egress"]:
                    self.assertEqual(rule["to"], [{
                        "namespaceSelector": {"matchLabels": {
                            "kubernetes.io/metadata.name": "monitoring"}},
                        "podSelector": {"matchLabels": {"app": "tempo"}},
                    }])
                    self.assertEqual(len(rule["ports"]), 1)

    def test_coredns_egress_is_not_accidentally_isolated(self):
        """An Egress-only tracing allow would break previously unrestricted DNS."""
        for path in (ROOT / "kube-system/coredns-custom").glob("*.yaml"):
            for doc in yaml.safe_load_all(path.read_text()):
                if doc and doc.get("kind") == "NetworkPolicy":
                    self.assertNotIn("Egress", doc["spec"].get("policyTypes", []))

    def test_tempo_service_remains_internal(self):
        """Export protocols must not acquire public listeners or node ports."""
        doc = yaml.safe_load((ROOT / "tempo/service-tempo.yaml").read_text())
        self.assertEqual(doc["spec"].get("type", "ClusterIP"), "ClusterIP")
        self.assertNotIn("externalIPs", doc["spec"])
        for port in doc["spec"]["ports"]:
            self.assertNotIn("nodePort", port)


if __name__ == "__main__":
    unittest.main()
