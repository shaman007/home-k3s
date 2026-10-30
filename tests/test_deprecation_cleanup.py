import importlib.util
from ipaddress import ip_address, ip_network
from pathlib import Path
import re
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/ci"))


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools/ci" / filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


render = module("cleanup_render", "render-applications.py")
contracts = module("cleanup_contracts", "validate-runtime-contracts.py")


def document(path):
    return yaml.safe_load((ROOT / path).read_text())


class DeprecationCleanupTest(unittest.TestCase):
    def test_env_guard_is_in_the_real_argo_application_render(self):
        app = document("argocd/application-traefik-network-policy.yaml")
        source = app["spec"]["source"]
        config = document("tools/ci/validation-config.yaml")
        with tempfile.TemporaryDirectory() as scratch:
            output = render.render_source(app, source, [source], ROOT, Path(scratch), config["kubernetesVersion"])
        routes = [d for d in yaml.safe_load_all(output) if d["kind"] == "IngressRoute"]
        self.assertEqual(1, len(routes))
        self.assertEqual("block-external-env-probes", routes[0]["metadata"]["name"])
        self.assertEqual("traefik", routes[0]["spec"]["ingressClassName"])

    def test_env_guard_blocks_env_files_without_blocking_other_paths_or_lan(self):
        guard = document("traefik/ingress-route-block-external-env-probes.yaml")
        self.assertEqual(["websecure"], guard["spec"]["entryPoints"])
        route = guard["spec"]["routes"][0]
        self.assertEqual(1000, route["priority"])
        self.assertEqual([{"kind": "TraefikService", "name": "noop@internal"}], route["services"])
        # These regexes are read from the actual rule. The full expression check
        # also preserves AND composition and the trusted-client exclusion.
        rule = re.fullmatch(
            r"HostRegexp\(`([^`]+)`\) && PathRegexp\(`([^`]+)`\) && !ClientIP\(`([^`]+)`\)",
            route["match"],
        )
        self.assertIsNotNone(rule)
        host_pattern, path_pattern, trusted_cidr = rule.groups()
        self.assertNotIn("{host:", host_pattern)
        trusted = ip_network(trusted_cidr)
        self.assertEqual(ip_network("192.168.1.0/24"), trusted)

        def blocked(host, path, client):
            return bool(re.search(host_pattern, host) and re.search(path_pattern, path)
                        and ip_address(client) not in trusted)

        for path in ["/.env", "/.env.local", "/app/.env", "/app/.env.backup", "/.env/config"]:
            with self.subTest(path=path):
                self.assertTrue(blocked("plex.andreybondarenko.com", path, "203.0.113.1"))
                self.assertTrue(blocked("example.com", path, "2001:db8::1"))
                self.assertFalse(blocked("example.com", path, "192.168.1.42"))
        for path in ["/", "/identity", "/app/environment", "/app/file.env", "/.environment", "/.envoy"]:
            with self.subTest(path=path):
                self.assertFalse(blocked("example.com", path, "203.0.113.1"))

    def test_plex_preserves_nodeport_and_https_endpoints(self):
        service = document("plex/service-plex.yaml")["spec"]
        self.assertEqual("NodePort", service["type"])
        self.assertNotIn("externalIPs", service)
        self.assertEqual({"app": "plex"}, service["selector"])
        ports = {p["name"]: (p["port"], p.get("protocol", "TCP")) for p in service["ports"]}
        self.assertEqual({"plex": (32400, "TCP"), "dlna": (1900, "UDP"),
                          "avahi": (5353, "UDP"), "companion": (8324, "TCP"),
                          "gdm1": (32410, "UDP"), "gdm2": (32412, "UDP"),
                          "gdm3": (32413, "UDP"), "gdm4": (32414, "UDP"),
                          "dlna2": (32469, "TCP")}, ports)
        self.assertEqual(32355, next(p["nodePort"] for p in service["ports"] if p["name"] == "plex"))
        deployment = document("plex/deployment-plex.yaml")
        container = deployment["spec"]["template"]["spec"]["containers"][0]
        advertise = next(e["value"] for e in container["env"] if e["name"] == "ADVERTISE_IP")
        self.assertEqual({"http://192.168.30.209:32355/", "https://plex.andreybondarenko.com:443/"},
                         set(advertise.split(",")))
        ingress = document("plex/ingress-andreybondarenko-ingress.yaml")
        rule = ingress["spec"]["rules"][0]
        self.assertEqual("plex.andreybondarenko.com", rule["host"])
        self.assertEqual({"name": "plex", "port": {"number": 32400}}, rule["http"]["paths"][0]["backend"]["service"])

    def test_backup_address_is_requested_from_the_existing_metallb_pool(self):
        service = document("backup-rsync/service-backup-rsync.yaml")
        address = service["metadata"]["annotations"]["metallb.io/loadBalancerIPs"]
        self.assertEqual("192.168.30.213", address)
        self.assertEqual("metallb-l2", service["spec"]["loadBalancerClass"])
        self.assertNotIn("loadBalancerIP", service["spec"])
        pool = document("metallb/ip-address-pool-public-ingress.yaml")
        self.assertTrue(any(ip_address(address) in ip_network(cidr) for cidr in pool["spec"]["addresses"]))

    def test_runtime_contract_rejects_deprecated_service_fields(self):
        for field, value in [("externalIPs", ["192.0.2.1"]), ("loadBalancerIP", "192.0.2.1")]:
            with self.subTest(field=field):
                errors = contracts.check_deprecated_service_fields(Path("service.yaml"), 1,
                    {"kind": "Service", "spec": {field: value}})
                self.assertEqual(1, len(errors))
                self.assertIn("spec." + field, errors[0])
        self.assertEqual([], contracts.check_deprecated_service_fields(Path("service.yaml"), 1,
            {"kind": "Service", "spec": {"type": "NodePort"}}))
