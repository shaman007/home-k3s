from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]


def load_yaml(path: str) -> dict:
    return yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))


def load_yaml_documents(path: str) -> list[dict]:
    content = (ROOT / path).read_text(encoding="utf-8")
    return [document for document in yaml.safe_load_all(content) if document]


class CertManagerMigrationTest(unittest.TestCase):
    PRODUCTION_CERTIFICATES = {
        "bitwarden/certificate-bitwarden-tls.yaml": (
            "bitwarden", "bitwarden-tls", ["bitwarden.andreybondarenko.com"]
        ),
        "convertx/certificate-convertx-tls.yaml": (
            "convertx", "convertx-tls", ["convert.andreybondarenko.com"]
        ),
        "dawarich/certificate-dawarich-tls.yaml": (
            "dawarich", "dawarich-tls", ["dawarich.andreybondarenko.com"]
        ),
        "harbor/certificate-harbor-tls.yaml": (
            "harbor", "harbor-tls", ["harbor.andreybondarenko.com"]
        ),
        "hister/certificate-hister-tls.yaml": (
            "hister", "hister-tls", ["hister.andreybondarenko.com"]
        ),
        "homeassistant/certificate-homeassistant-tls.yaml": (
            "homeassistant", "homeassistant-tls", ["ha.andreybondarenko.com"]
        ),
        "immich/certificate-immich-tls.yaml": (
            "immich", "immich-tls", ["immich.andreybondarenko.com"]
        ),
        "karakeep/certificate-karakeep-tls.yaml": (
            "karakeep", "karakeep-tls", ["keep.andreybondarenko.com"]
        ),
        "keycloak/certificate-keycloak-tls.yaml": (
            "keycloak", "keycloak-tls", ["sso.andreybondarenko.com"]
        ),
        "mastodon/certificate-mastodon-tls.yaml": (
            "mastodon", "mastodon-tls", ["mastodon.andreybondarenko.com"]
        ),
        "synapse/certificate-matrix-tls.yaml": (
            "matrix", "matrix-tls", ["shaman007.com"]
        ),
        "nextcloud/certificate-nextcloud-tls.yaml": (
            "nextcloud",
            "nextcloud-tls",
            ["cloud.andreybondarenko.com", "office.andreybondarenko.com"],
        ),
        "open-webui/certificate-open-webui-tls.yaml": (
            "open-webui", "open-webui-tls", ["chat.andreybondarenko.com"]
        ),
        "plex/certificate-plex-tls.yaml": (
            "plex", "plex-tls", ["plex.andreybondarenko.com"]
        ),
        "seaweedfs/certificate-seaweedfs-tls.yaml": (
            "seaweedfs", "seaweedfs-tls", ["s3.andreybondarenko.com"]
        ),
        "your-spotify/certificate-spotify-tls.yaml": (
            "spotify",
            "spotify-tls",
            ["spt.andreybondarenko.com", "spt-server.andreybondarenko.com"],
        ),
        "stirling-pdf/certificate-stirling-pdf-tls.yaml": (
            "stirling-pdf", "stirling-pdf-tls", ["pdf.andreybondarenko.com"]
        ),
        "wordpress/certificate-wordpress-tls.yaml": (
            "wordpress", "wordpress-tls", ["andreybondarenko.com"]
        ),
    }

    NAMESPACES_REQUIRING_SOLVER_POLICY = {
        "harbor": "harbor",
        "hister": "hister",
        "immich": "immich",
        "karakeep": "karakeep",
        "keycloak": "keycloak",
        "mastodon": "mastodon",
        "nextcloud": "nextcloud",
        "plex": "plex",
        "seaweedfs": "seaweedfs",
        "your-spotify": "spotify",
        "stirling-pdf": "stirling-pdf",
        "wordpress": "wordpress",
    }

    CUTOVER_INGRESSES = {
        "convertx/ingress-andreybondarenko-ingress.yaml": (
            "convert.andreybondarenko.com", "convertx-tls"
        ),
        "dawarich/ingress-andreybondarenko-ingress.yaml": (
            "dawarich.andreybondarenko.com", "dawarich-tls"
        ),
        "hister/ingress-andreybondarenko-ingress.yaml": (
            "hister.andreybondarenko.com", "hister-tls"
        ),
        "immich/ingress-andreybondarenko-ingress.yaml": (
            "immich.andreybondarenko.com", "immich-tls"
        ),
        "open-webui/ingress-open-webui.yaml": (
            "chat.andreybondarenko.com", "open-webui-tls"
        ),
        "seaweedfs/ingress-andreybondarenko-ingress.yaml": (
            "s3.andreybondarenko.com", "seaweedfs-tls"
        ),
        "stirling-pdf/ingress-andreybondarenko-ingress.yaml": (
            "pdf.andreybondarenko.com", "stirling-pdf-tls"
        ),
    }

    CUTOVER_INGRESS_ROUTES = {
        "open-webui/ingress-route-sensitive-throttle.yaml": (
            "sensitive-path-throttle", "open-webui-tls"
        ),
    }

    PENDING_INGRESS_ROUTES = (
        "bitwarden/ingress-route-sensitive-throttle.yaml",
        "harbor/ingress-route-sensitive-throttle.yaml",
        "homeassistant/ingress-route-sensitive-throttle.yaml",
        "karakeep/ingress-route-sensitive-throttle.yaml",
        "keycloak/ingress-route-sensitive-throttle.yaml",
        "mastodon/ingress-route-sensitive-throttle.yaml",
        "nextcloud/ingress-route-sensitive-throttle.yaml",
        "plex/ingress-route-sensitive-throttle.yaml",
        "wordpress/ingress-route-sensitive-throttle.yaml",
    )

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

    def test_routes_have_production_certificates(self):
        issuer_ref = {
            "group": "cert-manager.io",
            "kind": "ClusterIssuer",
            "name": "letsencrypt-prod",
        }

        for path, (namespace, secret_name, dns_names) in self.PRODUCTION_CERTIFICATES.items():
            with self.subTest(path=path):
                certificate = load_yaml(path)
                self.assertEqual(certificate["metadata"]["name"], secret_name)
                self.assertEqual(certificate["metadata"]["namespace"], namespace)
                self.assertEqual(
                    certificate["metadata"]["annotations"][
                        "argocd.argoproj.io/sync-wave"
                    ],
                    "-1",
                )
                self.assertEqual(certificate["spec"]["secretName"], secret_name)
                self.assertEqual(certificate["spec"]["dnsNames"], dns_names)
                self.assertEqual(certificate["spec"]["issuerRef"], issuer_ref)

        pending_ingresses = [
            "bitwarden/ingress-andreybondarenko-ingress.yaml",
            "harbor/ingress-andreybondarenko-ingress.yaml",
            "homeassistant/ingress-ha-andreybondarenko.yaml",
            "karakeep/ingress-andreybondarenko-ingress.yaml",
            "keycloak/ingress-andreybondarenko-ingress.yaml",
            "mastodon/ingress-andreybondarenko-ingress.yaml",
            "synapse/ingress-andreybondarenko-ingress.yaml",
            "nextcloud/ingress-andreybondarenko-ingress.yaml",
            "nextcloud/ingress-nextcloud-ui.yaml",
            "nextcloud/ingress-nextcloud-uploads.yaml",
            "plex/ingress-andreybondarenko-ingress.yaml",
            "your-spotify/ingress-andreybondarenko-ingress.yaml",
            "your-spotify/ingress-andreybondarenko-web-ingress.yaml",
            "wordpress/ingress-andreybondarenko-ingress.yaml",
        ]
        for path in pending_ingresses:
            with self.subTest(path=path):
                ingress = load_yaml(path)
                self.assertEqual(
                    ingress["metadata"]["annotations"][
                        "traefik.ingress.kubernetes.io/router.tls.certresolver"
                    ],
                    "letsencrypt",
                )

    def test_cutover_routes_use_cert_manager_secrets(self):
        resolver_annotation = (
            "traefik.ingress.kubernetes.io/router.tls.certresolver"
        )

        for path, (host, secret_name) in self.CUTOVER_INGRESSES.items():
            with self.subTest(path=path):
                ingress = load_yaml(path)
                self.assertNotIn(
                    resolver_annotation,
                    ingress["metadata"].get("annotations", {}),
                )
                self.assertEqual(ingress["spec"]["tls"], [{
                    "hosts": [host],
                    "secretName": secret_name,
                }])

    def test_cutover_ingress_routes_use_cert_manager_secrets(self):
        for path, (name, secret_name) in self.CUTOVER_INGRESS_ROUTES.items():
            with self.subTest(path=path):
                routes = [
                    document
                    for document in load_yaml_documents(path)
                    if document["kind"] == "IngressRoute"
                ]
                self.assertEqual(len(routes), 1)
                self.assertEqual(routes[0]["metadata"]["name"], name)
                self.assertEqual(
                    routes[0]["spec"]["tls"],
                    {"secretName": secret_name},
                )

    def test_pending_ingress_routes_still_use_native_acme(self):
        for path in self.PENDING_INGRESS_ROUTES:
            with self.subTest(path=path):
                routes = [
                    document
                    for document in load_yaml_documents(path)
                    if document["kind"] == "IngressRoute"
                ]
                self.assertEqual(len(routes), 1)
                self.assertEqual(
                    routes[0]["spec"]["tls"],
                    {"certResolver": "letsencrypt"},
                )

    def test_default_deny_namespaces_allow_only_traefik_to_solver(self):
        expected_from = [{
            "namespaceSelector": {
                "matchLabels": {"kubernetes.io/metadata.name": "traefik"}
            },
            "podSelector": {
                "matchLabels": {"app.kubernetes.io/name": "traefik"}
            },
        }]

        for folder, namespace in self.NAMESPACES_REQUIRING_SOLVER_POLICY.items():
            path = f"{folder}/network-policy-allow-cert-manager-http01-solver.yaml"
            with self.subTest(path=path):
                policy = load_yaml(path)
                self.assertEqual(policy["metadata"]["namespace"], namespace)
                self.assertEqual(
                    policy["metadata"]["annotations"][
                        "argocd.argoproj.io/sync-wave"
                    ],
                    "-2",
                )
                self.assertEqual(policy["spec"]["podSelector"], {
                    "matchLabels": {
                        "acme.cert-manager.io/http01-solver": "true"
                    }
                })
                self.assertEqual(policy["spec"]["policyTypes"], ["Ingress"])
                self.assertEqual(policy["spec"]["ingress"], [{
                    "from": expected_from,
                    "ports": [{"protocol": "TCP", "port": 8089}],
                }])

    def test_mastodon_application_includes_certificates(self):
        application = load_yaml("argocd/application-mastodon-custom.yaml")
        include = application["spec"]["source"]["directory"]["include"]
        self.assertIn("certificate-*.yaml", include)


if __name__ == "__main__":
    unittest.main()
