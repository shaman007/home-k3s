from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
ARGOCD = ROOT / "argocd"
ADAPTER_POLICIES = ROOT / "metrics" / "prometheus-adapter" / "network-policy.yaml"


class NetworkPolicyCoverageTest(unittest.TestCase):
    def test_cert_manager_chart_network_policies_are_enabled(self):
        application = yaml.safe_load(
            (ARGOCD / "application-cert-manager.yaml").read_text(encoding="utf-8")
        )
        values = yaml.safe_load(application["spec"]["sources"][0]["helm"]["values"])

        self.assertTrue(values["networkPolicy"]["enabled"])
        self.assertTrue(values["webhook"]["networkPolicy"]["enabled"])
        self.assertTrue(values["cainjector"]["networkPolicy"]["enabled"])

    def test_prometheus_adapter_application_includes_policy_source(self):
        application = yaml.safe_load(
            (ARGOCD / "application-my-adapter.yaml").read_text(encoding="utf-8")
        )
        git_sources = [
            source
            for source in application["spec"]["sources"]
            if source.get("repoURL") == "https://github.com/shaman007/home-k3s.git"
        ]

        self.assertEqual("metrics/prometheus-adapter", git_sources[0]["path"])
        self.assertEqual("main", git_sources[0]["targetRevision"])

    def test_prometheus_adapter_policy_allows_only_required_flows(self):
        policies = {
            document["metadata"]["name"]: document
            for document in yaml.safe_load_all(ADAPTER_POLICIES.read_text(encoding="utf-8"))
        }
        default_deny = policies["prometheus-adapter-default-deny"]["spec"]
        required = policies["prometheus-adapter-allow-required-traffic"]["spec"]
        api = policies["prometheus-adapter-allow-kube-apiserver"]["spec"]

        self.assertEqual({"Ingress", "Egress"}, set(default_deny["policyTypes"]))
        self.assertEqual([{"protocol": "TCP", "port": 6443}], required["ingress"][0]["ports"])
        self.assertIn("kube-apiserver", api["egress"][0]["toEntities"])
        self.assertEqual(
            {53, 9090},
            {port["port"] for rule in required["egress"] for port in rule["ports"]},
        )


if __name__ == "__main__":
    unittest.main()
