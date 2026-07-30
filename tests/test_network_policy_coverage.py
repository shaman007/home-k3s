from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
ARGOCD = ROOT / "argocd"


class NetworkPolicyCoverageTest(unittest.TestCase):
    def test_cert_manager_chart_network_policies_are_enabled(self):
        application = yaml.safe_load(
            (ARGOCD / "application-cert-manager.yaml").read_text(encoding="utf-8")
        )
        values = yaml.safe_load(application["spec"]["sources"][0]["helm"]["values"])

        self.assertTrue(values["networkPolicy"]["enabled"])
        self.assertTrue(values["webhook"]["networkPolicy"]["enabled"])
        self.assertTrue(values["cainjector"]["networkPolicy"]["enabled"])


if __name__ == "__main__":
    unittest.main()
