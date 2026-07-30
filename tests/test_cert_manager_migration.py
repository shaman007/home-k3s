from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]


def load_yaml(path: str) -> dict:
    return yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))


class CertManagerMigrationTest(unittest.TestCase):
    def test_year_uses_the_production_certificate(self):
        production_certificate = load_yaml("year/certificate-year-tls.yaml")
        ingress = load_yaml("year/ingress-year.yaml")
        application = load_yaml("argocd/application-year.yaml")

        self.assertFalse(
            (ROOT / "year/certificate-year-tls-staging.yaml").exists()
        )
        self.assertEqual(production_certificate["metadata"]["namespace"], "year")
        self.assertEqual(production_certificate["spec"], {
            "secretName": "year-tls",
            "dnsNames": ["year.andreybondarenko.com"],
            "issuerRef": {
                "group": "cert-manager.io",
                "kind": "ClusterIssuer",
                "name": "letsencrypt-prod",
            },
        })
        self.assertNotIn(
            "traefik.ingress.kubernetes.io/router.tls.certresolver",
            ingress["metadata"]["annotations"],
        )
        self.assertEqual(ingress["spec"]["tls"], [{
            "hosts": ["year.andreybondarenko.com"],
            "secretName": "year-tls",
        }])
        self.assertTrue(
            application["spec"]["syncPolicy"]["automated"]["prune"]
        )


if __name__ == "__main__":
    unittest.main()
