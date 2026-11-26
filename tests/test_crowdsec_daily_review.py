"""Routine scans stay in daily review; exclusions require known blackholes."""
import json
from pathlib import Path
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]


class CrowdSecDailyReviewTest(unittest.TestCase):
    """Exercise shipped collectors using real-format logs without live services."""

    def setUp(self):
        self.code = {"__name__": "test_report"}
        source = yaml.safe_load((ROOT / "metrics/config-map-external-access-daily-report-scripts.yaml").read_text())["data"]["external-access-daily-report.py"]
        exec(compile(source, "daily-report", "exec"), self.code)

    def collect(self, requests):
        event = 'time="2026-11-26T20:21:50Z" level=info msg="Ip 5.253.84.92 performed \'crowdsecurity/http-cve-probing\' (1 events over 0s) at 2026-11-26 20:21:50 +0000 UTC"'
        def query(_base, query, *_args):
            lines = [event, event] if 'namespace="crowdsec"' in query else [json.dumps(x) for x in requests]
            return iter((1795724510000000000, line, {}) for line in lines)
        self.code["loki_query_iter"] = query
        return self.code["collect_security_stats"]("unused", 0, 2)

    def request(self, **extra):
        return {"ClientHost": "5.253.84.92", "RequestHost": "example.com", "RequestPath": "/wp-json/batch/v1?secret=remove", "DownstreamStatus": 404, "RouterName": "wordpress-app@kubernetes", **extra}

    def test_normal_rejected_probe_is_reviewed_without_replay_duplicates(self):
        stats = self.collect([self.request()])
        self.assertEqual(1, stats["sources"]["5.253.84.92"])
        text = "\n".join(self.code["render_security_section"](stats))
        self.assertIn("Only rejected/error", text)
        self.assertNotIn("secret=remove", text)
        self.assertIn("example.com/wp-json/batch/v1", text)

    def test_only_known_blackholes_are_excluded(self):
        for override in [{"ServiceName": "noop@internal"}, {"RouterName": "traefik-block-external-env-probes-abc123@kubernetescrd"}]:
            stats = self.collect([self.request(**override)])
            self.assertFalse(stats["sources"])
            self.assertEqual(1, stats["ignored_blackhole_detections"])
        stats = self.collect([self.request(RouterName="other-blackhole-like-name@kubernetes")])
        self.assertTrue(stats["sources"])

    def test_mixed_blackhole_and_application_traffic_is_not_excluded(self):
        stats = self.collect([self.request(ServiceName="noop@internal"), self.request(DownstreamStatus=200)])
        self.assertEqual(1, stats["sources"]["5.253.84.92"])
        self.assertIn("not proof of exploitation", stats["rows"][0]["assessment"])

    def test_requests_outside_detection_window_do_not_raise_review(self):
        event = 'time="2026-11-26T20:21:50Z" msg="Ip 5.253.84.92 performed \'crowdsecurity/http-cve-probing\' (1 events over 0s)"'
        self.code["loki_query_iter"] = lambda _b, query, *_a: iter([(1795724510000000000, event, {})] if 'namespace="crowdsec"' in query else [(1795724500000000000, json.dumps(self.request(DownstreamStatus=200)), {})])
        stats = self.code["collect_security_stats"]("unused", 0, 2)
        self.assertIn("outcome unknown", stats["rows"][0]["assessment"])

    def test_missing_http_evidence_stays_unknown(self):
        stats = self.collect([])
        self.assertTrue(stats["sources"])
        self.assertIn("outcome unknown", stats["rows"][0]["assessment"])

    def test_routine_scan_rules_removed_but_login_detector_kept(self):
        config = yaml.safe_load((ROOT / "metrics/kubernetes-prometheus/config-map-prometheus-server-conf.yaml").read_text())
        rules = yaml.safe_load(config["data"]["prometheus.rules"])
        names = {r.get("alert") for g in rules["groups"] for r in g["rules"]}
        self.assertNotIn("CrowdSecExploitAttempt", names)
        self.assertNotIn("CrowdSecPersistentScanning", names)
        self.assertIn("KeycloakLoginFailureBurst", names)
