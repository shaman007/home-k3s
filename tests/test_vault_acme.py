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

    def test_first_service_cutover_avoids_cronjob_dual_writers(self):
        candidates = {
            "argocd-deploy/certificate-argocd-vault-acme-tls.yaml": {
                "namespace": "argocd",
                "secret": "argocd-vault-acme-tls",
                "dns_name": "argocd.w386.k8s.my.lan",
                "ingress": "argocd-deploy/ingress-argocd-ingress.yaml",
                "legacy_secret": "argocd-tls",
            },
            "longhorn/ingress-certificate-longhorn-vault-acme-tls.yaml": {
                "namespace": "longhorn-system",
                "secret": "longhorn-vault-acme-tls",
                "dns_name": "longhorn.w386.k8s.my.lan",
                "ingress": "longhorn/ingress-longhorn-ingress.yaml",
                "legacy_secret": "longhorn-tls",
            },
        }
        renewer = (ROOT / "vault/cron-job-vault-pki-renewer.yaml").read_text(
            encoding="utf-8"
        )

        for path, expected in candidates.items():
            with self.subTest(path=path):
                certificate = load_yaml(path)
                ingress = load_yaml(expected["ingress"])

                self.assertEqual(
                    certificate["metadata"]["namespace"],
                    expected["namespace"],
                )
                self.assertEqual(
                    certificate["spec"],
                    {
                        "secretName": expected["secret"],
                        "duration": "720h",
                        "renewBefore": "168h",
                        "dnsNames": [expected["dns_name"]],
                        "issuerRef": {
                            "group": "cert-manager.io",
                            "kind": "ClusterIssuer",
                            "name": "vault-acme",
                        },
                    },
                )
                self.assertNotEqual(
                    expected["secret"],
                    expected["legacy_secret"],
                )
                self.assertEqual(
                    ingress["spec"]["tls"][0]["secretName"],
                    expected["secret"],
                )
                self.assertIn(expected["legacy_secret"], renewer)
                self.assertNotIn(expected["secret"], renewer)

    def test_network_policies_limit_acme_control_and_validation_paths(self):
        egress = load_yaml(
            "vault/network-policy-vault-allow-egress-acme-http01.yaml"
        )
        traefik_egress = load_yaml(
            "traefik/"
            "network-policy-traefik-allow-egress-ingress-namespaces.yaml"
        )
        self.assertEqual(
            egress["spec"]["egress"][0]["ports"],
            [
                {"protocol": "TCP", "port": 80},
                {"protocol": "TCP", "port": 443},
            ],
        )
        self.assertEqual(
            egress["spec"]["egress"][1]["to"],
            [{"ipBlock": {"cidr": "192.168.1.210/32"}}],
        )
        allowed_namespaces = {
            peer["namespaceSelector"]["matchLabels"]
            ["kubernetes.io/metadata.name"]
            for peer in traefik_egress["spec"]["egress"][0]["to"]
        }
        self.assertIn("cert-manager", allowed_namespaces)

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
