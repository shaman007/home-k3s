"""Router-side BGP monitoring: missing paths must not look healthy."""

import copy
import importlib.util
import re
import io
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch
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
                for prefix, peers in zip(m.PREFIXES, [m.PEERS[1:], m.PEERS[:2], [m.PEERS[2]], m.PEERS[:2]])
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
            [2, 2, 1, 2],
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
        self.routes["items"].pop(2)
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

    def poll_snapshot(self, outcomes, fail_render=False):
        """Run bounded poll iterations and read the actual handler's in-memory metrics."""
        original_render = m.render

        def render(metrics, success, timestamp):
            if fail_render and success:
                raise ValueError("private-render-marker")
            return original_render(metrics, success, timestamp)

        with (
            patch.object(
                m, "Controller", return_value=SimpleNamespace(collect=Mock(side_effect=outcomes))
            ),
            patch.object(m.threading, "Thread") as thread,
            patch.object(m.http.server, "ThreadingHTTPServer") as server,
            patch.object(m.time, "time", return_value=123),
            patch.object(
                m.time, "sleep", side_effect=[None] * (len(outcomes) - 1) + [StopIteration]
            ),
            patch.object(m, "render", side_effect=render),
        ):
            m.main()
            with self.assertRaises(StopIteration):
                thread.call_args.kwargs["target"]()
            handler = server.call_args.args[1].__new__(server.call_args.args[1])
            handler.path = "/metrics"
            handler.wfile = io.BytesIO()
            with (
                patch.object(handler, "send_response"),
                patch.object(handler, "send_header"),
                patch.object(handler, "end_headers"),
            ):
                handler.do_get()
            return handler.wfile.getvalue().decode()

    def test_collection_failure_replaces_stale_samples_and_preserves_last_success(self):
        """An unexpected collection error cannot retain healthy metrics or expose diagnostics."""
        metrics = [("unifi_bgp_peer_established", {"peer": "fixture"}, 1)]
        body = self.poll_snapshot([metrics, RuntimeError("private-collection-marker")])
        self.assertIn("unifi_bgp_scrape_success 0\n", body)
        self.assertIn("unifi_bgp_last_success_timestamp_seconds 123\n", body)
        self.assertNotIn('peer="fixture"', body)
        self.assertNotIn("private-collection-marker", body)

    def test_render_failure_does_not_advance_last_success(self):
        """A snapshot that failed formatting must not become the last successful scrape."""
        body = self.poll_snapshot([[]], fail_render=True)
        self.assertIn("unifi_bgp_scrape_success 0\n", body)
        self.assertIn("unifi_bgp_last_success_timestamp_seconds 0\n", body)
        self.assertNotIn("private-render-marker", body)

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
        client.certificate_expiry = Mock(return_value=1893456000)
        self.assertIn(
            ("unifi_bgp_tls_certificate_expiry_timestamp_seconds", {}, 1893456000), client.collect()
        )
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
        """Require all four routes after the internal Harbor advertisement."""
        text = (ROOT / "docs/bgp-trial/udm-services.conf").read_text()
        self.assertEqual(set(m.PEERS), set(re.findall(r"neighbor ([0-9.]+) peer-group", text)))
        self.assertEqual(set(m.PREFIXES), set(re.findall(r"permit ([0-9.]+/32)", text)))

    def test_redirects_are_not_followed(self):
        """Verify redirects are not followed."""
        self.assertIsNone(
            m.NoRedirect().redirect_request(None, None, 302, "", {}, "https://elsewhere.invalid")
        )


class UniFiMetricsListenerTests(unittest.TestCase):
    """Keep metrics exposure on a deliberate interface while preserving pod scraping."""

    def test_metrics_listener_defaults_to_loopback_and_accepts_specific_pod_ip(self):
        """Select one interface without changing the metrics port or starting real resources."""
        for environment, expected in (
            ({}, "127.0.0.1"),
            ({"UNIFI_METRICS_ADDRESS": "10.42.1.17"}, "10.42.1.17"),
        ):
            with (
                self.subTest(address=expected),
                patch.dict(m.os.environ, environment, clear=True),
                patch.object(m, "Controller"),
                patch.object(m.threading, "Thread"),
                patch.object(m.http.server, "ThreadingHTTPServer") as server,
            ):
                m.main()
            self.assertEqual(server.call_args.args[0], (expected, 9131))
            server.return_value.serve_forever.assert_called_once()

    def test_invalid_or_wildcard_metrics_address_stops_before_controller(self):
        """Reject wildcard, unsupported IPv6 and non-address input before credentials or workers."""
        for address in (
            str(m.ipaddress.IPv4Address(0)),
            "::",
            "::1",
            "localhost",
            "10.42.1.17:9131",
            "",
        ):
            with (
                self.subTest(address=address),
                patch.dict(m.os.environ, {"UNIFI_METRICS_ADDRESS": address}),
                patch.object(m, "Controller") as controller,
                patch.object(m.threading, "Thread") as thread,
                patch.object(m.http.server, "ThreadingHTTPServer") as server,
            ):
                with self.assertRaisesRegex(ValueError, "specific IPv4"):
                    m.main()
            controller.assert_not_called()
            thread.assert_not_called()
            server.assert_not_called()

    def test_deployment_selects_pod_ip_without_host_network_or_public_service(self):
        """The existing ClusterIP service reaches the explicit pod interface and metrics port."""
        deployment = yaml.safe_load(
            (ROOT / "unifi/poller/deployment-unifi-poller.yaml").read_text()
        )
        pod = deployment["spec"]["template"]["spec"]
        self.assertFalse(pod.get("hostNetwork", False))
        exporter = next(c for c in pod["containers"] if c["name"] == "bgp-exporter")
        address = next(e for e in exporter["env"] if e["name"] == "UNIFI_METRICS_ADDRESS")
        self.assertEqual(address["valueFrom"]["fieldRef"]["fieldPath"], "status.podIP")
        self.assertEqual(exporter["ports"], [{"name": "bgp-metrics", "containerPort": 9131}])
        service = yaml.safe_load((ROOT / "unifi/poller/service-unifi-poller.yaml").read_text())
        self.assertEqual(service["spec"].get("type", "ClusterIP"), "ClusterIP")
        self.assertIn(
            {"name": "bgp", "port": 9131, "targetPort": "bgp-metrics"}, service["spec"]["ports"]
        )


class UniFiVerifiedTLSTests(unittest.TestCase):
    """Router identity validation must remain enabled even with legacy override variables."""

    def test_invalid_controller_origins_fail_before_transport_creation(self):
        """An HTTP or ambiguous endpoint cannot bypass the verified TLS transport."""
        for url in (
            "http://router.invalid",
            "https://user:private@router.invalid",
            "https://router.invalid/api",
            "https://router.invalid?token=private",
            "https://router.invalid#fragment",
            "https://router.invalid:bad",
            "https://router.invalid:0",
            "https://router.invalid/\n",
            "",
        ):
            with (
                self.subTest(url=url),
                patch.dict(m.os.environ, {"UNIFI_URL": url}, clear=True),
                patch.object(m.urllib.request, "build_opener") as transport,
            ):
                with self.assertRaisesRegex(ValueError, "HTTPS origin"):
                    m.Controller()
            transport.assert_not_called()

    def test_expiry_comes_from_the_live_verified_peer_and_closes_connections(self):
        """Use the named TLS peer's certificate date, not Kubernetes Secret readiness."""
        with patch.dict(m.os.environ, {"UNIFI_URL": "https://unifi.int.andreybondarenko.com"}):
            client = m.Controller()
        raw, tls = MagicMock(), MagicMock()
        raw.__enter__.return_value = raw
        tls.__enter__.return_value = tls
        tls.getpeercert.return_value = {"notAfter": "Jan  1 00:00:00 2030 GMT"}
        client.context = SimpleNamespace(wrap_socket=Mock(return_value=tls))
        with patch.object(m.socket, "create_connection", return_value=raw) as connect:
            self.assertEqual(client.certificate_expiry(), 1893456000)
        connect.assert_called_once_with(("unifi.int.andreybondarenko.com", 443), timeout=15)
        client.context.wrap_socket.assert_called_once_with(
            raw, server_hostname="unifi.int.andreybondarenko.com"
        )
        tls.__exit__.assert_called_once()
        raw.__exit__.assert_called_once()

    def test_system_trust_and_hostname_verification_cannot_be_disabled(self):
        """The verified-only client ignores the removed insecure-mode switch."""
        for value in ("true", "false", ""):
            with (
                self.subTest(legacy_override=value),
                patch.dict(
                    m.os.environ,
                    {
                        "UNIFI_URL": "https://unifi.int.andreybondarenko.com",
                        "UNIFI_VERIFY_TLS": value,
                    },
                    clear=True,
                ),
                patch.object(m.urllib.request, "build_opener"),
                patch.object(m.urllib.request, "HTTPSHandler") as https,
            ):
                controller = m.Controller()
            https.assert_called_once_with(context=controller.context)
            self.assertEqual(controller.context.verify_mode, m.ssl.CERT_REQUIRED)
            self.assertTrue(controller.context.check_hostname)
