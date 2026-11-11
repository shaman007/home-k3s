"""Prevent reintroduction of the retired private ingress issuance path."""

import json
from pathlib import Path
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]


class LegacyIngressRetirementTest(unittest.TestCase):
    """Keep retired issuance sources disabled while preserving private certificate routes."""
    def test_legacy_sources_are_removed(self):
        """Verify legacy sources are removed."""
        resources = json.loads(
            (
                ROOT / "docs/migrations/letsencrypt-internal/legacy-ingress-retirement.json"
            ).read_text()
        )["resources"]
        self.assertEqual(17, sum(r["kind"] == "Ingress" for r in resources))
        self.assertEqual(18, sum(r["kind"] == "Certificate" for r in resources))
        for r in resources:
            with self.subTest(resource=r["name"]):
                self.assertFalse((ROOT / r["source"]).exists())

    def test_private_routes_have_public_certificates_and_stay_private(self):
        """Verify private routes have public certificates and stay private."""
        certs = {}
        routes = []
        for p in ROOT.rglob("*.yaml"):
            if any(x in p.parts for x in ("docs", "DEPRECATED", "templates", ".git")):
                continue
            for d in yaml.safe_load_all(p.read_text()):
                if not isinstance(d, dict):
                    continue
                if d.get("kind") == "Certificate":
                    self.assertNotEqual("vault-acme", d["spec"]["issuerRef"]["name"])
                    certs[(d["metadata"]["namespace"], d["spec"]["secretName"])] = d
                if d.get("kind") == "Ingress":
                    for rule in d["spec"].get("rules", []):
                        self.assertFalse(rule["host"].endswith(".w386.k8s.my.lan"))
                        if rule["host"].endswith(".int.andreybondarenko.com"):
                            routes.append(d)
        self.assertEqual(17, len(routes))
        for route in routes:
            self.assertEqual("traefik-private", route["spec"]["ingressClassName"])
            for tls in route["spec"]["tls"]:
                cert = certs[(route["metadata"]["namespace"], tls["secretName"])]
                self.assertEqual("letsencrypt-internal-prod", cert["spec"]["issuerRef"]["name"])
                self.assertEqual(set(tls["hosts"]), set(cert["spec"]["dnsNames"]))

    def test_retired_bootstrap_cannot_reenable_issuance(self):
        """Verify retired bootstrap cannot reenable issuance."""
        script = (ROOT / "vault/configure-pki-acme.sh").read_text()
        self.assertNotIn("vault write", script)
        self.assertIn("exit 1", script)
        job = yaml.safe_load((ROOT / "openbao/cron-job-vault-pki-renewer.yaml").read_text())
        self.assertTrue(job["spec"]["suspend"])
        self.assertEqual(
            [], yaml.safe_load((ROOT / "openbao/role-vault-pki-renewer.yaml").read_text())["rules"]
        )


if __name__ == "__main__":
    unittest.main()
