"""Verdict guards: a model may interpret evidence, but cannot invent an all-clear."""

import datetime as dt
import io
import json
import hashlib
import tempfile
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
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

    def collect_records(self, records):
        """Collect synthetic lines at a fixed UTC instant without reading host telemetry."""
        now = dt.datetime(2026, 11, 11, 12, tzinfo=dt.timezone.utc)
        payload = "\n".join(
            record if isinstance(record, str) else json.dumps(record) for record in records
        )
        with (
            patch.object(report.glob, "glob", return_value=["fixture"]),
            patch.object(
                report, "open", create=True, side_effect=lambda *_a, **_k: io.StringIO(payload)
            ),
        ):
            return report.collect(now)

    def inbound_alert(self, flow):
        """Build a reputation-only inbound signal using routable remote addresses."""
        return {
            "timestamp": "2026-11-11T11:00:00+00:00",
            "event_type": "alert",
            "flow_id": 7,
            "src_ip": "8.8.8.8",
            "dest_ip": "192.168.1.21",
            "dest_port": 443,
            "flow": flow,
            "alert": {
                "signature": "ET DROP Spamhaus DROP Listed Traffic",
                "signature_id": 1,
                "severity": 2,
            },
        }

    def test_final_flow_evidence_outside_window_still_prevents_probe_suppression(self):
        """Correlate final session evidence without counting it as in-window traffic."""
        alert = self.inbound_alert({"pkts_toclient": 0})
        final = {
            **alert,
            "event_type": "flow",
            "timestamp": "2026-11-11T12:00:01+00:00",
            "flow": {
                "pkts_toserver": 2,
                "pkts_toclient": 2,
                "state": "established",
                "bytes_toserver": 200,
                "bytes_toclient": 100,
            },
            "tls": {"sni": "fixture.invalid"},
        }
        evidence = self.collect_records([alert, final])
        self.assertEqual(evidence["event_counts"], {"alert": 1})
        self.assertEqual(evidence["background_alerts"], {})
        self.assertEqual(len(evidence["incidents"]), 1)
        incident = evidence["incidents"][0]
        self.assertEqual(incident["states"], {"established": 1})
        self.assertEqual(incident["max_response_packets"], 2)
        self.assertEqual(incident["domains"], ["fixture.invalid"])

    def test_probe_thresholds_retain_established_and_larger_responses(self):
        """Exclude only unestablished low-response probes at the reviewed boundaries."""
        for state, sent, received, background in (
            ("new", 120, 80, True),
            ("new", 121, 80, False),
            ("new", 120, 81, False),
            ("established", 120, 80, False),
        ):
            alert = self.inbound_alert(
                {
                    "state": state,
                    "pkts_toclient": 1,
                    "bytes_toserver": sent,
                    "bytes_toclient": received,
                }
            )
            alert["tcp"] = {"rst": True}
            with self.subTest(state=state, sent=sent, received=received):
                result = self.collect_records([alert])
                self.assertEqual(bool(result["incidents"]), not background)

    def test_window_boundaries_and_malformed_record_accounting(self):
        """Include the start, exclude the end and retain malformed-record statistics."""
        record = {
            "timestamp": "2026-11-10T12:00:00+00:00",
            "event_type": "stats",
            "stats": {"capture": {"kernel_packets": 12}},
        }
        result = self.collect_records(
            [
                record,
                {**record, "timestamp": "2026-11-11T12:00:00+00:00"},
                {**record, "timestamp": "2026-11-10T11:59:59+00:00"},
                "{malformed",
                {"timestamp": "invalid"},
            ]
        )
        self.assertEqual(result["event_counts"], {"stats": 1})
        self.assertEqual(result["malformed_records"], 2)
        self.assertEqual(result["first_observed"], record["timestamp"])
        self.assertEqual(result["last_observed"], record["timestamp"])
        self.assertEqual(result["latest_sensor_stats"], record["stats"])


class AssessmentTests(unittest.TestCase):
    """Protect expected-port classification and monitoring failure precedence."""

    def evidence(self):
        """Build complete synthetic telemetry with one inbound reputation candidate."""
        return {
            "window_end": "2026-11-11T12:00:00+00:00",
            "first_observed": "2026-11-10T13:00:00+00:00",
            "last_observed": "2026-11-11T11:59:30+00:00",
            "clients": [],
            "latest_sensor_stats": {"capture": {"kernel_packets": 100, "kernel_drops": 0}},
            "incidents": [
                {
                    "id": "E1",
                    "host": "192.168.1.21",
                    "peer": "8.8.8.8",
                    "signature": "ET CINS Poor Reputation",
                    "direction": "inbound",
                    "port": 443,
                    "distinct_flows": 2,
                    "max_bytes_to_server": 1024,
                }
            ],
        }

    def assess(self, evidence, config, degraded=False):
        """Keep service, disk and baseline inspection entirely inside the fixture."""
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.object(report, "BASE", Path(directory)),
                patch.object(
                    report.subprocess,
                    "run",
                    return_value=SimpleNamespace(stdout="failed" if degraded else "active"),
                ),
                patch.object(
                    report.shutil,
                    "disk_usage",
                    return_value=SimpleNamespace(free=1 if degraded else 50, total=100),
                ),
            ):
                return report.assess(evidence, config)

    def test_preclassification_honors_custom_ports_direction_and_transfer_limits(self):
        """Keep unlisted ports, outbound visits and threshold-sized exchanges unresolved."""
        for port, direction, flows, sent, background in (
            (8443, "inbound", 19, 65535, True),
            (443, "inbound", 19, 65535, False),
            (8443, "outbound", 19, 65535, False),
            (8443, "inbound", 20, 65535, False),
            (8443, "inbound", 19, 65536, False),
        ):
            evidence = self.evidence()
            evidence["incidents"][0].update(
                port=port, direction=direction, distinct_flows=flows, max_bytes_to_server=sent
            )
            with self.subTest(port=port, direction=direction, flows=flows, sent=sent):
                assessment = self.assess(evidence, {"expected_public_ports": [8443]})
                self.assertEqual("preclassification" in assessment["candidates"][0], background)
                self.assertEqual(assessment["expected_public_ports"], [8443])

    def test_payload_corroboration_blocks_public_service_background_exception(self):
        """Retain a substantive signature on the same connection as an actionable signal."""
        evidence = self.evidence()
        evidence["incidents"].append(
            {**evidence["incidents"][0], "id": "E2", "signature": "ET EXPLOIT fixture"}
        )
        result = self.assess(evidence, {})
        self.assertTrue(all("preclassification" not in item for item in result["candidates"]))

    def test_monitoring_failures_preserve_issue_order_and_prevent_all_clear(self):
        """Keep service, disk, freshness and capture-loss gates independently visible."""
        evidence = self.evidence()
        evidence["last_observed"] = "2026-11-11T11:54:59+00:00"
        evidence["latest_sensor_stats"]["capture"]["kernel_drops"] = 2
        result = self.assess(evidence, {}, degraded=True)
        self.assertEqual(result["status"], "MONITORING DEGRADED")
        self.assertTrue(result["operational"])
        self.assertEqual([issue["id"] for issue in result["issues"]], ["I1", "I2", "I3", "I4"])
        self.assertEqual(
            [issue["title"] for issue in result["issues"]],
            [
                "Monitoring service unavailable",
                "Monitoring storage is nearly full",
                "Telemetry is stale",
                "Sensor is losing a material share of mirrored packets",
            ],
        )


class ModelTransportTests(unittest.TestCase):
    """Keep report evidence behind verified TLS and close failures without network access."""

    def test_certificate_pin_is_checked_before_request_and_connections_always_close(self):
        """Close success, pin mismatch, connect failure and HTTP failure paths."""
        certificate = b"synthetic-certificate"
        config = {
            "ollama_ip": "192.0.2.1",
            "ollama_host": "model.invalid",
            "ollama_cert_sha256": hashlib.sha256(certificate).hexdigest(),
        }
        for failure in (None, "pin", "connect", "response", "read", "http"):
            connection = MagicMock()
            connection.sock.getpeercert.return_value = (
                b"different-certificate" if failure == "pin" else certificate
            )
            if failure == "connect":
                connection.connect.side_effect = OSError("fixture connection failed")
            connection.getresponse.return_value.status = 500 if failure == "http" else 200
            connection.getresponse.return_value.read.return_value = b"fixture-response"
            if failure == "response":
                connection.getresponse.side_effect = OSError("fixture response failed")
            if failure == "read":
                connection.getresponse.return_value.read.side_effect = OSError(
                    "fixture read failed"
                )
            with (
                self.subTest(failure=failure),
                patch.object(report.ssl, "create_default_context"),
                patch.object(report.http.client, "HTTPSConnection", return_value=connection),
            ):
                if failure:
                    with self.assertRaises((RuntimeError, OSError)):
                        report.request_model(config, b"sensitive-fixture-body")
                else:
                    self.assertEqual(
                        report.request_model(config, b"fixture-body"), b"fixture-response"
                    )
                connection.close.assert_called_once()
                if failure in ("pin", "connect"):
                    connection.request.assert_not_called()
                else:
                    self.assertEqual(connection.request.call_args.args[:2], ("POST", "/api/chat"))

    def test_incomplete_model_stream_never_produces_findings(self):
        """Reject empty content, unfinished output and length-limited results."""
        for message in (
            {"message": {"content": ""}, "done": True},
            {"message": {"content": "{}"}, "done": False},
            {"message": {"content": "{}"}, "done": True, "done_reason": "length"},
        ):
            with self.subTest(message=message), self.assertRaisesRegex(RuntimeError, "Incomplete"):
                report.parse_model_stream(json.dumps(message).encode())

    def test_model_batches_require_every_known_id_and_ignore_unrequested_ids(self):
        """Retain bounded schemas and reject missing findings across the twelve-item boundary."""
        assessment = {"candidates": [{"id": f"E{index}"} for index in range(13)]}

        def make_response(omit):
            """Bind a fresh response stream and batch history for one completion case."""
            batches = []

            def response(_config, body):
                """Reply from the actual outgoing constrained schema without opening a socket."""
                payload = json.loads(body)
                schema = payload["format"]
                ids = list(schema["properties"])
                self.assertEqual(schema["required"], ids)
                self.assertFalse(schema["additionalProperties"])
                batches.append(ids)
                findings = {
                    key: {"disposition": "background", "reason": "fixture", "action": "None"}
                    for key in ids
                }
                findings["unrequested"] = {"disposition": "threat"}
                if omit and len(batches) == 2:
                    findings.pop(ids[-1])
                return json.dumps(
                    {"message": {"content": json.dumps(findings)}, "done": True}
                ).encode()

            return batches, response

        for omit_last in (False, True):
            batches, response = make_response(omit_last)
            with (
                self.subTest(omit_last=omit_last),
                patch.object(report, "request_model", side_effect=response),
            ):
                if omit_last:
                    with self.assertRaisesRegex(RuntimeError, "omitted incident evidence IDs"):
                        report.summarize(assessment, {"model": "gpt-oss:20b"})
                else:
                    findings = report.summarize(assessment, {"model": "gpt-oss:20b"})
                    self.assertEqual(set(findings), {f"E{index}" for index in range(13)})
            self.assertEqual(list(map(len, batches)), [12, 1])

    def test_report_submission_keeps_starttls_before_message_delivery(self):
        """Do not submit a message until both EHLO and STARTTLS have completed."""
        for tls_failure in (False, True):
            smtp = MagicMock()
            if tls_failure:
                smtp.starttls.side_effect = OSError("fixture TLS failure")
            with (
                self.subTest(tls_failure=tls_failure),
                patch.object(report.smtplib, "SMTP") as factory,
            ):
                factory.return_value.__enter__.return_value = smtp
                if tls_failure:
                    with self.assertRaises(OSError):
                        report.submit_message({"smtp_host": "mail.invalid"}, "fixture-message")
                    smtp.send_message.assert_not_called()
                else:
                    report.submit_message({"smtp_host": "mail.invalid"}, "fixture-message")
                    self.assertEqual(
                        [call[0] for call in smtp.method_calls],
                        ["ehlo", "starttls", "ehlo", "send_message"],
                    )


if __name__ == "__main__":
    unittest.main()
