from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "mail" / "postfixadmin.yaml"


class PostfixAdminSecurityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.resources = {
            (document["kind"], document["metadata"]["name"]): document
            for document in yaml.safe_load_all(MANIFEST.read_text(encoding="utf-8"))
        }

    def test_official_image_is_pinned_by_digest(self):
        deployment = self.resources[("Deployment", "postfixadmin")]
        image = deployment["spec"]["template"]["spec"]["containers"][0]["image"]

        self.assertRegex(
            image,
            r"^harbor\.andreybondarenko\.com/dockerhub/postfixadmin@sha256:[0-9a-f]{64}$",
        )

    def test_ingress_is_internal_and_lan_restricted(self):
        ingress = self.resources[("Ingress", "postfixadmin")]
        certificate = self.resources[("Certificate", "postfixadmin-vault-acme-tls")]
        middleware = self.resources[("Middleware", "postfixadmin-local-network-only")]

        self.assertEqual(
            "postfixadmin.w386.k8s.my.lan",
            ingress["spec"]["rules"][0]["host"],
        )
        self.assertEqual("vault-acme", certificate["spec"]["issuerRef"]["name"])
        self.assertEqual(
            ["192.168.1.0/24"],
            middleware["spec"]["ipAllowList"]["sourceRange"],
        )

    def test_mail_services_are_not_configured_to_use_postfixadmin_database(self):
        deployment = self.resources[("Deployment", "postfixadmin")]
        environment = {
            item["name"]
            for item in deployment["spec"]["template"]["spec"]["containers"][0]["env"]
        }

        self.assertNotIn("POSTFIXADMIN_SMTP_SERVER", environment)


if __name__ == "__main__":
    unittest.main()
