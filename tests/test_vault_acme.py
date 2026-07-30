from base64 import b64decode
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]


def load_yaml(path: str) -> dict:
    return yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))


def load_yaml_documents(path: str) -> list[dict]:
    return list(
        yaml.safe_load_all((ROOT / path).read_text(encoding="utf-8"))
    )


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

    def test_first_service_cutover_removes_cronjob_permissions(self):
        candidates = {
            "argocd-deploy/certificate-argocd-vault-acme-tls.yaml": {
                "namespace": "argocd",
                "secret": "argocd-vault-acme-tls",
                "dns_name": "argocd.w386.k8s.my.lan",
                "ingress": "argocd-deploy/ingress-argocd-ingress.yaml",
                "legacy_secret": "argocd-tls",
                "renewer_role": "argocd-deploy/role-vault-pki-renewer.yaml",
            },
            "longhorn/ingress-certificate-longhorn-vault-acme-tls.yaml": {
                "namespace": "longhorn-system",
                "secret": "longhorn-vault-acme-tls",
                "dns_name": "longhorn.w386.k8s.my.lan",
                "ingress": "longhorn/ingress-longhorn-ingress.yaml",
                "legacy_secret": "longhorn-tls",
                "renewer_role": "longhorn/ingress-role-vault-pki-renewer.yaml",
            },
        }
        renewer = (ROOT / "vault/cron-job-vault-pki-renewer.yaml").read_text(
            encoding="utf-8"
        )

        for path, expected in candidates.items():
            with self.subTest(path=path):
                certificate = load_yaml(path)
                ingress = load_yaml(expected["ingress"])
                renewer_role = load_yaml_documents(
                    expected["renewer_role"]
                )[0]

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
                self.assertNotIn(expected["legacy_secret"], renewer)
                self.assertNotIn(expected["secret"], renewer)
                self.assertEqual(renewer_role["rules"], [])

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

    def test_mempalace_http01_path_is_solver_scoped(self):
        solver_ingress = load_yaml(
            "mempalace/"
            "network-policy-allow-cert-manager-http01-solver.yaml"
        )
        traefik_egress = load_yaml(
            "traefik/network-policy-traefik-allow-egress-mempalace.yaml"
        )

        self.assertEqual(
            solver_ingress["spec"]["podSelector"]["matchLabels"],
            {"acme.cert-manager.io/http01-solver": "true"},
        )
        self.assertEqual(
            solver_ingress["spec"]["ingress"][0]["ports"],
            [{"protocol": "TCP", "port": 8089}],
        )
        solver_egress = traefik_egress["spec"]["egress"][1]
        self.assertEqual(
            solver_egress["to"][0]["podSelector"]["matchLabels"],
            {"acme.cert-manager.io/http01-solver": "true"},
        )
        self.assertEqual(
            solver_egress["ports"],
            [{"protocol": "TCP", "port": 8089}],
        )

    def test_second_service_cutover_removes_cronjob_permissions(self):
        candidates = {
            "mempalace/certificate-mempalace-vault-acme-tls.yaml": {
                "namespace": "mempalace",
                "secret": "mempalace-vault-acme-tls",
                "dns_name": "mempalace.w386.k8s.my.lan",
                "ingress": "mempalace/ingress-mempalace.yaml",
                "legacy_secret": "mempalace-tls",
                "renewer_role": "mempalace/role-vault-pki-renewer.yaml",
            },
            "nextcloud/certificate-office-vault-acme-tls.yaml": {
                "namespace": "nextcloud",
                "secret": "office-vault-acme-tls",
                "dns_name": "office.w386.k8s.my.lan",
                "ingress": "nextcloud/ingress-office-ingress.yaml",
                "legacy_secret": "office-tls",
                "renewer_role": "nextcloud/role-vault-pki-renewer.yaml",
            },
        }
        renewer = (ROOT / "vault/cron-job-vault-pki-renewer.yaml").read_text(
            encoding="utf-8"
        )

        for path, expected in candidates.items():
            with self.subTest(path=path):
                certificate = load_yaml(path)
                ingress = load_yaml(expected["ingress"])
                renewer_role = load_yaml_documents(
                    expected["renewer_role"]
                )[0]

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
                self.assertEqual(
                    ingress["spec"]["tls"][0]["secretName"],
                    expected["secret"],
                )
                self.assertNotIn(expected["legacy_secret"], renewer)
                self.assertNotIn(expected["secret"], renewer)
                self.assertEqual(renewer_role["rules"], [])

    def test_final_service_cutover_removes_cronjob_permissions(self):
        candidates = {
            "metrics/ingress-certificate-alerts-vault-acme-tls.yaml": {
                "namespace": "monitoring",
                "secret": "alerts-vault-acme-tls",
                "dns_name": "alerts.w386.k8s.my.lan",
                "ingress": "metrics/ingress-alerts-ingress.yaml",
                "legacy_secret": "alerts-tls",
                "renewer_role": "metrics/ingress-role-vault-pki-renewer.yaml",
            },
            "metrics/ingress-certificate-grafana-vault-acme-tls.yaml": {
                "namespace": "monitoring",
                "secret": "grafana-vault-acme-tls",
                "dns_name": "grafana.w386.k8s.my.lan",
                "ingress": "metrics/ingress-grafana-ingress.yaml",
                "legacy_secret": "grafana-tls",
                "renewer_role": "metrics/ingress-role-vault-pki-renewer.yaml",
            },
            "metrics/ingress-certificate-prometheus-vault-acme-tls.yaml": {
                "namespace": "monitoring",
                "secret": "prometheus-vault-acme-tls",
                "dns_name": "prometheus.w386.k8s.my.lan",
                "ingress": "metrics/ingress-prometheus-ingress.yaml",
                "legacy_secret": "prometheus-tls",
                "renewer_role": "metrics/ingress-role-vault-pki-renewer.yaml",
            },
            "mail/certificate-rspamd-vault-acme-tls.yaml": {
                "namespace": "mail",
                "secret": "rspamd-vault-acme-tls",
                "dns_name": "rspamd.w386.k8s.my.lan",
                "ingress": "mail/ingress-rspamd-ingress.yaml",
                "legacy_secret": "rspamd-tls",
                "renewer_role": "mail/role-vault-pki-renewer.yaml",
            },
        }
        renewer = (ROOT / "vault/cron-job-vault-pki-renewer.yaml").read_text(
            encoding="utf-8"
        )

        for path, expected in candidates.items():
            with self.subTest(path=path):
                certificate = load_yaml(path)
                ingress = load_yaml(expected["ingress"])
                renewer_role = load_yaml_documents(
                    expected["renewer_role"]
                )[0]

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
                self.assertEqual(
                    ingress["spec"]["tls"][0]["secretName"],
                    expected["secret"],
                )
                self.assertNotIn(expected["legacy_secret"], renewer)
                self.assertNotIn(expected["secret"], renewer)
                self.assertEqual(renewer_role["rules"], [])

        self.assertNotIn("w386-k8s-my-lan-wildcard", renewer)
        self.assertNotIn("wildcard_targets", renewer)

    def test_vault_ingress_cutover_removes_direct_renewal(self):
        certificate = load_yaml(
            "vault/certificate-vault-ingress-vault-acme-tls.yaml"
        )
        ingress = load_yaml("vault/ingress-vault-ingress.yaml")
        renewer = (ROOT / "vault/cron-job-vault-pki-renewer.yaml").read_text(
            encoding="utf-8"
        )

        self.assertEqual(certificate["metadata"]["namespace"], "vault")
        self.assertEqual(
            certificate["spec"],
            {
                "secretName": "vault-ingress-vault-acme-tls",
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
        self.assertEqual(
            ingress["spec"]["tls"][0]["secretName"],
            "vault-ingress-vault-acme-tls",
        )
        renewer_role = load_yaml("vault/role-vault-pki-renewer.yaml")
        renewer_policy = (
            ROOT / "vault/policy-vault-pki-renewer.hcl"
        ).read_text(encoding="utf-8")

        self.assertNotIn('secret_needs_renewal "vault" "vault-tls"', renewer)
        self.assertNotIn('issue_cert "vault-ingress"', renewer)
        self.assertIn(
            'secret_needs_renewal "vault" "vault-server-tls"',
            renewer,
        )
        self.assertNotIn("vault-ingress-vault-acme-tls", renewer)
        self.assertEqual(
            renewer_role["rules"][0]["resourceNames"],
            ["vault-server-tls"],
        )
        self.assertIn('path "pki-root/issue/vault-server"', renewer_policy)
        self.assertNotIn("w386-k8s-my-lan-wildcard", renewer_policy)
        self.assertNotIn("pki-root/issue/vault-ingress", renewer_policy)

    def test_final_service_http01_paths_are_solver_scoped(self):
        for path in (
            "mail/network-policy-allow-cert-manager-http01-solver.yaml",
            "metrics/ingress-network-policy-allow-cert-manager-http01-solver.yaml",
            "vault/network-policy-vault-allow-cert-manager-http01-solver.yaml",
        ):
            with self.subTest(path=path):
                policy = load_yaml(path)
                self.assertEqual(
                    policy["spec"]["podSelector"]["matchLabels"],
                    {"acme.cert-manager.io/http01-solver": "true"},
                )
                self.assertEqual(
                    policy["spec"]["ingress"][0]["ports"],
                    [{"protocol": "TCP", "port": 8089}],
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
