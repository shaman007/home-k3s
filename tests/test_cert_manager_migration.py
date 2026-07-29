from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]


def load_yaml(path: str) -> dict:
    return yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))


class CertManagerMigrationTest(unittest.TestCase):
    def test_year_staging_canary_does_not_cut_over_the_ingress(self):
        certificate = load_yaml("year/certificate-year-tls-staging.yaml")
        ingress = load_yaml("year/ingress-year.yaml")

        self.assertEqual(certificate["metadata"]["namespace"], "year")
        self.assertEqual(certificate["spec"], {
            "secretName": "year-tls-staging",
            "dnsNames": ["year.andreybondarenko.com"],
            "issuerRef": {
                "group": "cert-manager.io",
                "kind": "ClusterIssuer",
                "name": "letsencrypt-staging",
            },
        })
        self.assertEqual(
            ingress["metadata"]["annotations"][
                "traefik.ingress.kubernetes.io/router.tls.certresolver"
            ],
            "letsencrypt",
        )
        self.assertNotIn("tls", ingress["spec"])


if __name__ == "__main__":
    unittest.main()
