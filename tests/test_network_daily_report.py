"""Verdict guards: a model may interpret evidence, but cannot invent an all-clear."""

import datetime as dt
import io
import json
from unittest.mock import patch
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    "network_report", Path(__file__).parents[1] / "tools/network_daily_report.py"
)
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


class VerdictTests(unittest.TestCase):
    """Prevent unsupported all-clear verdicts and constrain expected-service exceptions."""

    def assessment(self, signature="ET MALWARE Known C2"):
        """Build an inbound network assessment targeting a configured public service."""
        return {
            "issues": [],
            "operational": False,
            "expected_public_ports": [443],
            "candidates": [
                {
                    "id": "E1",
                    "signature": signature,
                    "host": "81.19.4.105",
                    "peer": "203.0.113.1",
                    "direction": "inbound",
                    "port": 443,
                    "distinct_flows": 2,
                    "max_bytes_to_server": 1500,
                }
            ],
        }

    def finding(self, disposition):
        """Build an evidence-bearing analysis finding with the requested disposition."""
        return {
            "E1": {
                "disposition": disposition,
                "reason": "Measured connection evidence.",
                "action": "Check the specific connection.",
            }
        }

    def test_background_produces_qualified_all_clear(self):
        """Verify background produces qualified all clear."""
        data = self.assessment()
        report.apply_verdict(data, self.finding("background"))
        self.assertEqual(data["status"], "NO CONCERNING ACTIVITY DETECTED")
        self.assertEqual(data["issues"], [])

    def test_analysis_failure_never_produces_all_clear(self):
        """Verify analysis failure never produces all clear."""
        data = self.assessment()
        report.apply_verdict(data, {}, "timeout")
        self.assertEqual(data["status"], "ANALYSIS INCOMPLETE")

    def test_reputation_visit_to_expected_public_service_is_not_compromise(self):
        """Verify reputation visit to expected public service is not compromise."""
        data = self.assessment("ET DROP Spamhaus DROP Listed Traffic")
        report.apply_verdict(data, self.finding("threat"))
        self.assertEqual(data["status"], "NO CONCERNING ACTIVITY DETECTED")

    def test_unlisted_port_does_not_receive_expected_service_exception(self):
        """Verify unlisted port does not receive expected service exception."""
        for allowed_ports, port in (([443], 8443), ([8443], 443)):
            with self.subTest(allowed_ports=allowed_ports, port=port):
                data = self.assessment("ET DROP Spamhaus DROP Listed Traffic")
                data["expected_public_ports"] = allowed_ports
                data["candidates"][0]["port"] = port
                report.apply_verdict(data, self.finding("threat"))
                self.assertEqual(data["status"], "ANOMALY REQUIRES ATTENTION")
                self.assertEqual(len(data["issues"]), 1)

    def test_configured_nondefault_port_receives_expected_service_exception(self):
        """Verify configured nondefault port receives expected service exception."""
        data = self.assessment("ET DROP Spamhaus DROP Listed Traffic")
        data["expected_public_ports"] = [8443]
        data["candidates"][0]["port"] = 8443
        report.apply_verdict(data, self.finding("threat"))
        self.assertEqual(data["status"], "NO CONCERNING ACTIVITY DETECTED")

    def test_outbound_reputation_match_is_not_suppressed_as_inbound_noise(self):
        """Verify outbound reputation match is not suppressed as inbound noise."""
        data = self.assessment("ET CINS Poor Reputation IP")
        data["candidates"][0]["direction"] = "outbound"
        report.apply_verdict(data, self.finding("threat"))
        self.assertEqual(data["status"], "ANOMALY REQUIRES ATTENTION")

    def test_payload_alert_prevents_reputation_service_exception(self):
        """Verify payload alert prevents reputation service exception."""
        data = self.assessment("ET DROP Spamhaus DROP Listed Traffic")
        second = {**data["candidates"][0], "id": "E2", "signature": "ET EXPLOIT Specific Payload"}
        data["candidates"].append(second)
        findings = {**self.finding("anomaly"), "E2": self.finding("threat")["E1"]}
        report.apply_verdict(data, findings)
        self.assertEqual(data["status"], "POTENTIAL THREAT DETECTED")
        self.assertEqual(len(data["issues"]), 2)


class CollectorTests(unittest.TestCase):
    """Count final flow snapshots once without inflating observed traffic totals."""

    def test_flow_snapshots_are_deduplicated(self):
        """Verify flow snapshots are deduplicated."""
        now = dt.datetime.now(dt.timezone.utc)
        event = {
            "timestamp": (now - dt.timedelta(hours=1)).isoformat(),
            "event_type": "flow",
            "src_ip": "192.168.1.21",
            "dest_ip": "8.8.8.8",
            "flow_id": 123,
            "app_proto": "tls",
        }
        records = [
            {**event, "flow": {"bytes_toserver": 100, "bytes_toclient": 50}},
            {**event, "flow": {"bytes_toserver": 200, "bytes_toclient": 75}},
        ]
        payload = "\n".join(json.dumps(e) for e in records)
        with (
            patch.object(report.glob, "glob", return_value=["fixture"]),
            patch.object(
                report, "open", create=True, side_effect=lambda *a, **k: io.StringIO(payload)
            ),
        ):
            evidence = report.collect(now)
        client = evidence["clients"][0]
        self.assertEqual(client["flows"], 1)
        self.assertEqual(client["upload_bytes"], 200)
        self.assertEqual(client["download_bytes"], 75)
        self.assertEqual(client["flow_bytes"], 275)


if __name__ == "__main__":
    unittest.main()
