from base64 import b64decode
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]


def load_yaml(path: str) -> dict:
    return yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))


class VaultAcmeTest(unittest.TestCase):
    def test_cluster_issuer_uses_restricted_vault_role_directory(self):
        issuer = load_yaml("cert-manager/cluster-issuer-vault-acme.yaml")
        acme = issuer["spec"]["acme"]

        self.assertEqual(issuer["metadata"]["name"], "vault-acme")
        self.assertEqual(
            acme["server"],
            "https://vault.w386.k8s.my.lan/v1/pki-int/roles/"
            "w386-k8s-my-lan-acme/acme/directory",
        )
        self.assertIn(
            b"-----BEGIN CERTIFICATE-----",
            b64decode(acme["caBundle"]),
        )
        self.assertEqual(
            acme["privateKeySecretRef"]["name"],
            "vault-acme-account-key",
        )
        self.assertEqual(
            acme["solvers"][0]["http01"]["ingress"]["ingressClassName"],
            "traefik",
        )

    def test_canary_does_not_replace_a_consumed_secret(self):
        certificate = load_yaml(
            "cert-manager/certificate-vault-acme-canary.yaml"
        )

        self.assertEqual(certificate["metadata"]["namespace"], "cert-manager")
        self.assertEqual(
            certificate["spec"],
            {
                "secretName": "vault-acme-canary-tls",
                "duration": "720h",
                "renewBefore": "168h",
                "dnsNames": ["vault.w386.k8s.my.lan"],
                "issuerRef": {
                    "group": "cert-manager.io",
                    "kind": "ClusterIssuer",
                    "name": "vault-acme",
                },
            },
        )

    def test_network_policies_limit_acme_control_and_validation_paths(self):
        egress = load_yaml(
            "vault/network-policy-vault-allow-egress-acme-http01.yaml"
        )

        self.assertEqual(
            egress["spec"]["egress"][1]["to"],
            [{"ipBlock": {"cidr": "192.168.1.210/32"}}],
        )

    def test_vault_configuration_is_role_and_issuer_restricted(self):
        script = (ROOT / "vault/configure-pki-acme.sh").read_text(
            encoding="utf-8"
        )

        for setting in (
            "default_directory_policy=forbid",
            'allowed_roles="${role_name}"',
            'allowed_issuers="${issuer_id}"',
            "allow_wildcard_certificates=false",
            "allow_ip_sans=false",
            "allow_localhost=false",
            "tidy_acme=true",
        ):
            self.assertIn(setting, script)


if __name__ == "__main__":
    unittest.main()
