"""Keep the prepared Harbor BGP expansion narrow and reversible."""

from pathlib import Path
import ipaddress
import re
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "docs/migrations/harbor-bootstrap/udm-before.conf"
PREPARED = ROOT / "docs/bgp-trial/udm-services.conf"
NEW_PREFIX = "192.168.30.212/32"


class HarborBGPPreparation(unittest.TestCase):
    """Separate accepted-prefix preparation from required live-route monitoring."""

    def test_only_one_exact_host_prefix_is_added(self):
        """Do not turn a one-service addition into a broad subnet allowance."""
        before = set(re.findall(r"permit ([0-9.]+/\d+)", BASELINE.read_text()))
        after = set(re.findall(r"permit ([0-9.]+/\d+)", PREPARED.read_text()))
        self.assertEqual({"192.168.30.210/32", "192.168.30.211/32", "192.168.30.213/32"}, before)
        self.assertEqual(before | {NEW_PREFIX}, after)
        self.assertTrue(all(ipaddress.ip_network(prefix).prefixlen == 32 for prefix in after))

    def test_limit_peers_and_route_policy_are_preserved(self):
        """Allow four accepted prefixes per peer while preserving the rest byte-for-byte."""
        before, after = BASELINE.read_text(), PREPARED.read_text()
        self.assertIn("neighbor K8S-TRIAL maximum-prefix 3", before)
        self.assertEqual(1, after.count("neighbor K8S-TRIAL maximum-prefix 4"))
        restored = after.replace(
            "neighbor K8S-TRIAL maximum-prefix 4", "neighbor K8S-TRIAL maximum-prefix 3"
        )
        restored = restored.replace(
            "ip prefix-list K8S-TRIAL-ONLY seq 35 permit " + NEW_PREFIX + "\n", ""
        )
        self.assertEqual(before, restored)
        self.assertIn("route-map K8S-TRIAL-OUT deny 10", after)
        self.assertIn("route-map K8S-TRIAL-IN deny 100", after)

    def test_vip_is_only_in_dedicated_explicit_pool(self):
        """Keep the internal VIP explicit and isolated from other pools."""
        candidate = ipaddress.ip_address("192.168.30.212")
        for path in (ROOT / "metallb").glob("ip-address-pool-*.yaml"):
            for document in yaml.safe_load_all(path.read_text()):
                if not document or document.get("kind") != "IPAddressPool":
                    continue
                if document["metadata"]["name"] == "registry-bootstrap":
                    self.assertEqual([NEW_PREFIX], document["spec"]["addresses"])
                    self.assertFalse(document["spec"]["autoAssign"])
                    continue
                for address in document["spec"]["addresses"]:
                    if "-" in address:
                        first, last = map(ipaddress.ip_address, address.split("-", 1))
                        if candidate.version == first.version:
                            self.assertFalse(first <= candidate <= last)
                    else:
                        network = ipaddress.ip_network(address)
                        if candidate.version == network.version:
                            self.assertNotIn(candidate, network)


if __name__ == "__main__":
    unittest.main()
