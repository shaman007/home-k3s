"""Verify separation of public and private Traefik ingress classes."""

from pathlib import Path
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]


def chart_values(name):
    """Read inline Helm values from the named controller application."""
    app = yaml.safe_load((ROOT / f"argocd/application-{name}.yaml").read_text())
    return yaml.safe_load(app["spec"]["source"]["helm"]["values"])


class IngressClassSeparationTest(unittest.TestCase):
    """Keep public and private controllers, services, and CRD ownership separate."""
    def test_controllers_have_disjoint_explicit_class_filters(self):
        """Verify controllers have disjoint explicit class filters."""
        for name, ingress_class in [("traefik", "traefik"), ("traefik-private", "traefik-private")]:
            values = chart_values(name)
            self.assertEqual(ingress_class, values["ingressClass"]["name"])
            self.assertFalse(values["ingressClass"]["isDefaultClass"])
            for provider in ["kubernetesIngress", "kubernetesCRD"]:
                self.assertEqual(ingress_class, values["providers"][provider]["ingressClass"])

    def test_private_controller_does_not_own_shared_crds(self):
        """Verify private controller does not own shared CRDs."""
        app = yaml.safe_load((ROOT / "argocd/application-traefik-private.yaml").read_text())
        self.assertTrue(app["spec"]["source"]["helm"]["skipCrds"])

    def test_private_service_has_no_public_ipv6_and_restricts_sources(self):
        """Verify private service has no public IPv6 and restricts sources."""
        values = chart_values("traefik-private")
        self.assertEqual(values, yaml.safe_load((ROOT / "traefik-private/values.yaml").read_text()))
        service = values["service"]
        self.assertEqual(["IPv4"], service["spec"]["ipFamilies"])
        self.assertEqual("SingleStack", service["spec"]["ipFamilyPolicy"])
        self.assertEqual("192.168.30.211", service["annotations"]["metallb.io/loadBalancerIPs"])
        self.assertEqual(
            ["192.168.30.0/24", "192.168.4.0/24", "10.42.0.0/16"],
            service["spec"]["loadBalancerSourceRanges"],
        )

    def test_private_listener_preserves_encoded_wopi_urls(self):
        """Verify private listener preserves encoded WOPI urls."""
        public_flags = chart_values("traefik")["additionalArguments"]
        private_flags = chart_values("traefik-private")["additionalArguments"]
        required = {flag for flag in public_flags if ".encodedCharacters." in flag}
        self.assertTrue(required)
        self.assertTrue(required.issubset(set(private_flags)))

    def test_every_private_ingress_declares_its_own_tls_secret(self):
        """Verify every private ingress declares its own TLS secret."""
        for path in ROOT.rglob("ingress*.yaml"):
            if "DEPRECATED" in path.parts:
                continue
            for doc in yaml.safe_load_all(path.read_text()):
                if not isinstance(doc, dict) or doc.get("kind") != "Ingress":
                    continue
                if doc["spec"].get("ingressClassName") != "traefik-private":
                    continue
                hosts = {rule["host"] for rule in doc["spec"].get("rules", [])}
                tls = doc["spec"].get("tls", [])
                covered = {
                    host
                    for entry in tls
                    if entry.get("secretName")
                    for host in entry.get("hosts", [])
                }
                self.assertTrue(hosts.issubset(covered), str(path))

    def test_every_route_is_explicitly_classified(self):
        """Verify every route is explicitly classified."""
        count = 0
        for path in ROOT.rglob("*.yaml"):
            if any(
                part in path.parts
                for part in ["DEPRECATED", ".git", ".agents", "talos", "templates"]
            ):
                continue
            for document in yaml.safe_load_all(path.read_text()):
                if not isinstance(document, dict):
                    continue
                kind = document.get("kind")
                if kind == "Ingress":
                    hosts = [
                        rule.get("host", "") for rule in document.get("spec", {}).get("rules", [])
                    ]
                    expected = (
                        "traefik-private"
                        if any(
                            host.endswith((".k8s.my.lan", ".int.andreybondarenko.com"))
                            for host in hosts
                        )
                        else "traefik"
                    )
                    if path.relative_to(ROOT).as_posix() == "harbor/ingress-harbor-internal-registry.yaml":
                        self.assertEqual("harbor-internal-registry", document["metadata"]["name"])
                        self.assertEqual(["harbor.andreybondarenko.com"], hosts)
                        expected = "traefik-registry"
                    self.assertEqual(expected, document["spec"].get("ingressClassName"), str(path))
                    self.assertNotIn(
                        "kubernetes.io/ingress.class",
                        document.get("metadata", {}).get("annotations", {}),
                        str(path),
                    )
                    count += 1
                elif kind in ["IngressRoute", "IngressRouteTCP", "IngressRouteUDP"]:
                    matches = [
                        rule.get("match", "") for rule in document.get("spec", {}).get("routes", [])
                    ]
                    expected = (
                        "traefik-private"
                        if any(
                            any(
                                suffix in match
                                for suffix in (".k8s.my.lan", ".int.andreybondarenko.com")
                            )
                            for match in matches
                        )
                        else "traefik"
                    )
                    self.assertEqual(expected, document["spec"].get("ingressClassName"), str(path))
                    self.assertNotIn(
                        "kubernetes.io/ingress.class",
                        document["metadata"].get("annotations", {}),
                        str(path),
                    )
        self.assertGreater(count, 25)
