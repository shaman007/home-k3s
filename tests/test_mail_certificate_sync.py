from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]


def load_yaml(path: str) -> dict:
    return yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))


class MailCertificateSyncTest(unittest.TestCase):
    def test_cert_manager_transition_releases_http01_from_traefik(self):
        application = load_yaml("argocd/application-cert-manager.yaml")
        issuer = load_yaml(
            "cert-manager/cluster-issuer-letsencrypt-prod.yaml"
        )
        staging_issuer = load_yaml(
            "cert-manager/cluster-issuer-letsencrypt-staging.yaml"
        )
        traefik = (ROOT / "argocd/application-traefik.yaml").read_text(
            encoding="utf-8"
        )

        self.assertIn("sources", application["spec"])
        self.assertEqual(
            application["metadata"]["finalizers"],
            ["resources-finalizer.argocd.argoproj.io"],
        )
        self.assertEqual(issuer["kind"], "ClusterIssuer")
        self.assertEqual(staging_issuer["kind"], "ClusterIssuer")
        self.assertIn("acme-staging", staging_issuer["spec"]["acme"]["server"])
        expected_solvers = [{"http01": {"ingress": {
            "ingressClassName": "traefik",
            "podTemplate": {"spec": {"resources": {
                "requests": {"cpu": "10m", "memory": "128Mi"},
                "limits": {"memory": "128Mi"},
            }}},
        }}}]
        self.assertEqual(issuer["spec"]["acme"]["solvers"], expected_solvers)
        self.assertEqual(
            staging_issuer["spec"]["acme"]["solvers"], expected_solvers
        )
        self.assertNotIn("httpChallenge:", traefik)
        self.assertNotIn("certificatesResolvers:", traefik)
        self.assertNotIn("certificatesResolvers:", (ROOT / "traefik/values.yaml").read_text())

    def test_mail_consumers_use_cert_manager_and_reload_on_renewal(self):
        for name in ("postfix", "dovecot"):
            with self.subTest(name=name):
                deployment = load_yaml(f"mail/deployment-{name}.yaml")
                volumes = deployment["spec"]["template"]["spec"]["volumes"]
                certs = next(v for v in volumes if v["name"] == "mail-certs")
                self.assertEqual(certs["secret"]["secretName"], "mail-tls")
                self.assertEqual(deployment["metadata"]["annotations"][
                    "secret.reloader.stakater.com/reload"], "mail-tls")

    def test_legacy_exporter_is_retired(self):
        for path in (
            "argocd/application-traefik-acme-exporter.yaml",
            "traefik-acme-exporter",
            "mail/secret-letsencrypt-prod.yaml",
            "mail/role-sync-le-tls.yaml",
            "mail/role-binding-sync-le-tls.yaml",
        ):
            self.assertFalse((ROOT / path).exists(), path)
        report = (ROOT / "metrics/config-map-platform-health-report-scripts.yaml").read_text()
        self.assertIn("/api/v1/namespaces/mail/secrets/mail-tls", report)
        self.assertNotIn("/api/v1/namespaces/mail/secrets/letsencrypt-prod", report)

    def test_traefik_no_longer_grants_mail_pod_exec(self):
        traefik = (ROOT / "argocd/application-traefik.yaml").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("sync-le-tls-traefik-readexec", traefik)
        self.assertNotIn("pods/exec", traefik)

if __name__ == "__main__":
    unittest.main()
