"""Keep callback recovery scoped to the protected hosts and safe homepage links."""

import json
import re
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

import yaml

ROOT = Path(__file__).resolve().parents[1]


class PageParser(HTMLParser):
    """Collect navigation and active content from the recovery page."""

    def __init__(self):
        super().__init__()
        self.links = []
        self.active = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a":
            self.links.append(attrs.get("href"))
        if tag in {"script", "base", "iframe", "form"}:
            self.active.append(tag)
        self.active.extend(k for k in attrs if k.startswith("on"))


class OidcCallbackErrorsTest(unittest.TestCase):
    """Verify recovery cannot change ordinary application or authentication routes."""

    @classmethod
    def setUpClass(cls):
        cls.values = yaml.safe_load((ROOT / "traefik-private/values.yaml").read_text())
        cls.objects = {
            o["kind"]: o
            for o in cls.values["extraObjects"]
            if o["metadata"]["name"] == "oidc-callback-errors"
        }

    def test_exact_callback_hosts_and_security_order(self):
        """Catch only callback 500s after the internal source check, before OIDC."""
        spec = self.objects["IngressRoute"]["spec"]
        self.assertEqual("traefik-private", spec["ingressClassName"])
        self.assertEqual(["websecure"], spec["entryPoints"])
        self.assertEqual(1, len(spec["routes"]))
        route = spec["routes"][0]
        client = json.loads(
            (ROOT / "keycloak/config/traefik-admin.client.json").read_text()
        )
        hosts = {u.split("/")[2] for u in client["redirectUris"]}
        expected = (
            "("
            + " || ".join(f"Host(`{h}`)" for h in sorted(hosts))
            + ") && Path(`/oidc/callback`)"
        )
        self.assertEqual(expected, route["match"])
        self.assertGreater(route["priority"], 100)
        self.assertEqual(
            ["internal-clients-only", "oidc-callback-errors", "admin-oidc"],
            [m["name"] for m in route["middlewares"]],
        )
        errors = self.objects["Middleware"]["spec"]["errors"]
        self.assertEqual(["500"], errors["status"])
        self.assertEqual("/callback-error.html", errors["query"])
        self.assertEqual([], errors["errorRequestHeaders"])
        self.assertNotIn("statusRewrites", errors)
        # Existing application ingress chains stay unchanged.
        for path in [
            *ROOT.glob("metrics/ingress-*.yaml"),
            *ROOT.glob("longhorn/ingress-*.yaml"),
        ]:
            doc = next(
                (
                    d
                    for d in yaml.safe_load_all(path.read_text())
                    if d and d["kind"] == "Ingress"
                ),
                None,
            )
            if doc is None:
                continue
            chain = (
                doc.get("metadata", {})
                .get("annotations", {})
                .get("traefik.ingress.kubernetes.io/router.middlewares", "")
            )
            self.assertNotIn("oidc-callback-errors", chain)

    def test_page_returns_to_current_origin_without_callback_query(self):
        """The link drops stale code/state on every protected host, without scripts."""
        page = self.objects["ConfigMap"]["data"]["callback-error.html"]
        parser = PageParser()
        parser.feed(page)
        self.assertEqual(["/"], parser.links)
        self.assertEqual([], parser.active)
        self.assertIn("Открыть главную", page)
        route = self.objects["IngressRoute"]["spec"]["routes"][0]
        for host in re.findall(r"Host\(`([^`]+)`\)", route["match"]):
            self.assertEqual(
                f"https://{host}/",
                urljoin(
                    f"https://{host}/oidc/callback?code=expired&state=old",
                    parser.links[0],
                ),
            )
        nginx = self.objects["ConfigMap"]["data"]["nginx.conf"]
        self.assertIn('Cache-Control "no-store"', nginx)
        self.assertIn('Referrer-Policy "no-referrer"', nginx)
        self.assertIn("location / { return 404; }", nginx)

    def test_resources_fit_namespace_limit_range(self):
        """Catch admission rejection before callback page pods are deployed."""
        limits = next(
            d
            for d in yaml.safe_load_all(
                (ROOT / "namespaces/limit-ranges.yaml").read_text()
            )
            if d and d["metadata"].get("namespace") == "traefik"
        )["spec"]["limits"]
        container = self.objects["Deployment"]["spec"]["template"]["spec"][
            "containers"
        ][0]
        resources = container["resources"]
        # This workload and the namespace contract use Mi memory and m CPU units.
        for entry in limits:
            if entry["type"] != "Container":
                continue
            minimum = entry["min"]
            for section in ("requests", "limits"):
                self.assertGreaterEqual(
                    int(resources[section]["memory"].removesuffix("Mi")),
                    int(minimum["memory"].removesuffix("Mi")),
                )
            self.assertGreaterEqual(
                int(resources["requests"]["cpu"].removesuffix("m")),
                int(minimum["cpu"].removesuffix("m")),
            )

    def test_error_service_wiring_and_port(self):
        """The replacement page resolves to a ready, non-root static HTTP backend."""
        errors = self.objects["Middleware"]["spec"]["errors"]
        service = self.objects["Service"]
        self.assertEqual(service["metadata"]["name"], errors["service"]["name"])
        self.assertEqual(service["spec"]["ports"][0]["port"], errors["service"]["port"])
        pod = self.objects["Deployment"]["spec"]["template"]
        self.assertEqual(service["spec"]["selector"], pod["metadata"]["labels"])
        container = pod["spec"]["containers"][0]
        self.assertTrue(container["securityContext"]["runAsNonRoot"])
        self.assertTrue(container["securityContext"]["readOnlyRootFilesystem"])
        self.assertEqual("/healthz", container["readinessProbe"]["httpGet"]["path"])
        app = yaml.safe_load(
            (ROOT / "argocd/application-traefik-private.yaml").read_text()
        )
        self.assertEqual(
            self.values, yaml.safe_load(app["spec"]["source"]["helm"]["values"])
        )
