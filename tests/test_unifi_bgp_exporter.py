"""Router-side BGP monitoring: missing paths must not look healthy."""

import copy
import importlib.util
import re
import io
from types import SimpleNamespace
from unittest.mock import Mock
import urllib.error
from pathlib import Path
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "unifi_bgp", ROOT / "tools/monitoring/unifi_bgp_exporter.py"
)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class UniFiBGPExporterTests(unittest.TestCase):
    """Reject missing or unexpected BGP state while preserving reviewed route metrics."""

    def setUp(self):
        self.neighbors = [
            {
                "vrf": "default",
                "neighbors": [
                    {
                        "peer": p,
                        "state": "Established",
                        "remote_as": 65040,
                        "advertised_routes_count": 0,
                    }
                    for p in m.PEERS
                ],
            }
        ]
        self.routes = {
            "items": [
                {
                    "origin": "BGP",
                    "destination": prefix,
                    "nexthops": [{"gateway": peer, "in_use": True} for peer in peers],
                }
                for prefix, peers in zip(m.PREFIXES, [m.PEERS[1:], m.PEERS[:2], [m.PEERS[2]]])
            ]
        }

    def metrics(self):
        """Index decoded BGP metric samples by name and sorted label pairs."""
        return {
            (name, tuple(sorted(labels.items()))): value
            for name, labels, value in m.decode(self.neighbors, self.routes)
        }

    def value(self, name, **labels):
        """Read one decoded metric using its name and exact labels."""
        return self.metrics()[(name, tuple(sorted(labels.items())))]

    def test_healthy_endpoint_dependent_counts(self):
        """Check healthy peer and route counts using both collection endpoints."""
        for p in m.PEERS:
            self.assertEqual(1, self.value("unifi_bgp_peer_established", peer=p))
        self.assertEqual(
            [2, 2, 1],
            [self.value("unifi_bgp_route_active_next_hops", prefix=p) for p in m.PREFIXES],
        )
        self.assertTrue(
            all(
                v == 0
                for (name, _), v in self.metrics().items()
                if name == "unifi_bgp_policy_violations"
            )
        )

    def test_missing_peer_emits_explicit_failure(self):
        """Verify missing peer emits explicit failure."""
        self.neighbors[0]["neighbors"].pop()
        self.assertEqual(0, self.value("unifi_bgp_peer_established", peer=m.PEERS[2]))

    def test_rejected_route_detected_even_if_other_routes_work(self):
        """Detect a missing expected route even when other routes remain usable."""
        self.routes["items"].pop()
        self.assertEqual(0, self.value("unifi_bgp_route_active_next_hops", prefix=m.PREFIXES[2]))
        self.assertEqual(2, self.value("unifi_bgp_route_active_next_hops", prefix=m.PREFIXES[0]))

    def test_inactive_or_unknown_next_hop_is_not_a_usable_path(self):
        """Verify inactive or unknown next hop is not a usable path."""
        route = self.routes["items"][2]
        route["nexthops"] = [
            {"gateway": m.PEERS[2], "in_use": False},
            {"gateway": "192.168.30.99", "in_use": True},
        ]
        self.assertEqual(0, self.value("unifi_bgp_route_active_next_hops", prefix=m.PREFIXES[2]))
        self.assertEqual(1, self.value("unifi_bgp_policy_violations", reason="unexpected_next_hop"))

    def test_unexpected_peer_prefix_and_as_are_reported(self):
        """Verify unexpected peer prefix and AS are reported."""
        self.neighbors[0]["neighbors"].append(
            {
                "peer": "192.168.30.99",
                "state": "Established",
                "remote_as": 65099,
                "advertised_routes_count": 1,
            }
        )
        self.routes["items"].append({"origin": "BGP", "destination": "0.0.0.0/0", "nexthops": []})
        for reason in ["unexpected_peer", "unexpected_prefix", "unexpected_remote_as"]:
            self.assertEqual(1, self.value("unifi_bgp_policy_violations", reason=reason))

    def test_wrong_as_is_not_a_healthy_expected_peer(self):
        """Verify wrong AS is not a healthy expected peer."""
        self.neighbors[0]["neighbors"][0]["remote_as"] = 65099
        self.assertEqual(0, self.value("unifi_bgp_peer_established", peer=m.PEERS[0]))

    def test_exports_are_exposed_and_connected_routes_are_ignored(self):
        """Verify exports are exposed and connected routes are ignored."""
        self.neighbors[0]["neighbors"][0]["advertised_routes_count"] = 2
        self.routes["items"].append(
            {"origin": "Kernel", "destination": "192.168.30.0/24", "nexthops": []}
        )
        self.assertEqual(2, self.value("unifi_bgp_exported_routes", peer=m.PEERS[0]))
        self.assertEqual(0, self.value("unifi_bgp_policy_violations", reason="unexpected_prefix"))

    def test_malformed_or_duplicate_data_is_not_silently_healthy(self):
        """Verify malformed or duplicate data is not silently healthy."""
        with self.assertRaises(ValueError):
            m.decode({}, self.routes)
        with self.assertRaises(ValueError):
            m.decode(self.neighbors, {})
        self.neighbors[0]["neighbors"].append(copy.deepcopy(self.neighbors[0]["neighbors"][0]))
        with self.assertRaises(ValueError):
            m.decode(self.neighbors, self.routes)

    def test_failed_collection_does_not_reexport_stale_routes(self):
        """Verify failed collection does not reexport stale routes."""
        text = m.render([], False, 123)
        self.assertIn("unifi_bgp_scrape_success 0", text)
        self.assertIn("unifi_bgp_last_success_timestamp_seconds 123", text)
        self.assertNotIn("unifi_bgp_route_active_next_hops{", text)

    def test_http_error_bodies_close_before_propagation(self):
        """Authentication and server failures cannot retain HTTP response resources."""
        client = object.__new__(m.Controller)
        client.base = "https://router.invalid"
        client.csrf = ""
        for status in (401, 403, 500):
            body = io.BytesIO(b"synthetic-error")
            error = urllib.error.HTTPError(client.base, status, "fixture", {}, body)
            client.opener = SimpleNamespace(open=Mock(side_effect=error))
            with self.subTest(status=status), self.assertRaises(urllib.error.HTTPError) as caught:
                client.request("/fixture")
            self.assertIs(caught.exception, error)
            self.assertTrue(body.closed)

    def test_only_read_endpoints_used_by_collection(self):
        """Restrict collection to the reviewed read-only router endpoints."""
        client = object.__new__(m.Controller)
        calls = []

        def get(path):
            calls.append(path)
            return self.neighbors if path.endswith("neighbors") else self.routes

        client.get = get
        self.assertTrue(client.collect())
        self.assertEqual(
            [
                "/proxy/network/v2/api/site/default/bgp/neighbors",
                "/proxy/network/v2/api/site/default/routes",
            ],
            calls,
        )

    def test_generated_configmap_matches_reviewed_source(self):
        """Verify generated ConfigMap matches reviewed source."""
        cm = yaml.safe_load((ROOT / "unifi/poller/config-map-unifi-bgp-exporter.yaml").read_text())
        self.assertEqual(
            (ROOT / "tools/monitoring/unifi_bgp_exporter.py").read_text(), cm["data"]["exporter.py"]
        )

    def test_reviewed_inventory_matches_router_configuration(self):
        """Keep reviewed BGP peer and route inventories aligned with router configuration."""
        text = (ROOT / "docs/bgp-trial/udm-services.conf").read_text()
        self.assertEqual(set(m.PEERS), set(re.findall(r"neighbor ([0-9.]+) peer-group", text)))
        self.assertEqual(set(m.PREFIXES), set(re.findall(r"permit ([0-9.]+/32)", text)))

    def test_redirects_are_not_followed(self):
        """Verify redirects are not followed."""
        self.assertIsNone(
            m.NoRedirect().redirect_request(None, None, 302, "", {}, "https://elsewhere.invalid")
        )
