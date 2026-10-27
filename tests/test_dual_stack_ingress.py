from ipaddress import ip_address, ip_network
from pathlib import Path
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]


class DualStackIngressTest(unittest.TestCase):
    def test_dual_stack_vips_preserve_primary_ipv4_and_match_pool(self):
        app = yaml.safe_load((ROOT / "argocd/application-traefik.yaml").read_text())
        embedded = yaml.safe_load(app["spec"]["source"]["helm"]["values"])
        standalone = yaml.safe_load((ROOT / "traefik/values.yaml").read_text())
        pool = yaml.safe_load((ROOT / "metallb/ip-address-pool-public-ingress.yaml").read_text())
        ranges = [ip_network(cidr) for cidr in pool["spec"]["addresses"]]
        for values in (embedded, standalone):
            service = values["service"]
            self.assertEqual(["IPv4", "IPv6"], service["spec"]["ipFamilies"])
            self.assertEqual("RequireDualStack", service["spec"]["ipFamilyPolicy"])
            addresses = service["annotations"]["metallb.io/loadBalancerIPs"].split(",")
            self.assertEqual("192.168.30.210", addresses[0])
            self.assertEqual([4, 6], [ip_address(value).version for value in addresses])
            for address in addresses:
                self.assertTrue(any(ip_address(address) in network for network in ranges))

    def test_manual_ipv6_node_allocations_are_unique_and_separate_from_services(self):
        patch = yaml.safe_load((ROOT / "talos/dual-stack-services.yaml").read_text())
        self.assertNotIn("podSubnets", patch["cluster"]["network"])
        services = patch["cluster"]["network"]["serviceSubnets"]
        self.assertEqual("10.43.0.0/16", services[0])
        ipv6_service = ip_network(services[1])
        self.assertEqual(6, ipv6_service.version)
        networks = []
        for path in ROOT.glob("talos/dual-stack-node-*.yaml"):
            node = yaml.safe_load(path.read_text())
            network = ip_network(node["machine"]["nodeAnnotations"]["network.cilium.io/ipv6-pod-cidr"])
            self.assertEqual(6, network.version)
            self.assertEqual(64, network.prefixlen)
            self.assertFalse(network.overlaps(ipv6_service))
            self.assertTrue(all(not network.overlaps(other) for other in networks))
            networks.append(network)
        self.assertEqual(3, len(networks))

    def test_native_smtp_uses_existing_backend_and_keeps_outgoing_ipv4(self):
        direct = yaml.safe_load((ROOT / "mail/ingress-route-tcp-postfix-smtp.yaml").read_text())
        existing = yaml.safe_load((ROOT / "mail/ingress-route-tcp-postfix-submission.yaml").read_text())
        self.assertEqual(["smtp"], direct["spec"]["entryPoints"])
        self.assertEqual(existing["spec"]["routes"], direct["spec"]["routes"])
        config = yaml.safe_load((ROOT / "mail/config-map-main-cf.yaml").read_text())["data"]
        self.assertIn("inet_protocols = ipv4", config["config"])
        self.assertIn("-o inet_protocols=all", config["master"])


if __name__ == "__main__":
    unittest.main()
