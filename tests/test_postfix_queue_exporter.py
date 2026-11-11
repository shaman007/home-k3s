"""Queue aggregation must not expose mail payloads or turn failures into zeroes."""

import json
from pathlib import Path
import shutil
import subprocess
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "tools/monitoring/postfix-queue-exporter.pl"
PERL = shutil.which("perl")
AVAILABLE = (
    PERL
    and subprocess.run(
        [PERL, "-MJSON::PP", "-MIO::Socket::INET", "-e", "1"], capture_output=True, check=False
    ).returncode
    == 0
)


@unittest.skipUnless(AVAILABLE, "Perl JSON::PP and IO::Socket::INET required")
class PostfixQueueTests(unittest.TestCase):
    def parse(self, records):
        return subprocess.run(
            [PERL, str(SOURCE), "--parse", "2000"],
            input="".join(json.dumps(x) + "\n" for x in records),
            capture_output=True,
            text=True,
            check=False,
        )

    def test_empty_queue_is_explicit_zero(self):
        result = self.parse([])
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.count("} 0\n"), 10)

    def test_counts_oldest_initial_arrival_and_payload_privacy(self):
        result = self.parse(
            [
                {
                    "queue_name": "deferred",
                    "arrival_time": 1000,
                    "sender": "PRIVATE",
                    "recipients": [{"address": "PRIVATE", "delay_reason": "PRIVATE"}],
                },
                {"queue_name": "deferred", "arrival_time": 1500},
                {"queue_name": "active", "arrival_time": 1900},
            ]
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('postfix_queue_messages{queue="deferred"} 2\n', result.stdout)
        self.assertIn('postfix_queue_oldest_age_seconds{queue="deferred"} 1000\n', result.stdout)
        self.assertIn('postfix_queue_oldest_age_seconds{queue="active"} 100\n', result.stdout)
        self.assertNotIn("PRIVATE", result.stdout)

    def test_invalid_snapshot_is_not_empty_queue(self):
        for record in [
            {"queue_name": "unknown", "arrival_time": 1000},
            {"queue_name": "active"},
            {"queue_name": "active", "arrival_time": "invalid"},
        ]:
            with self.subTest(record=record):
                result = self.parse([record])
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")

    def test_concurrent_arrival_does_not_fail_snapshot(self):
        result = self.parse([{"queue_name": "active", "arrival_time": 2001}])
        self.assertEqual(result.returncode, 0)
        self.assertIn('postfix_queue_oldest_age_seconds{queue="active"} 0\n', result.stdout)

    @unittest.skipIf(Path("/usr/sbin/postqueue").exists(), "requires absent postqueue")
    def test_failed_collection_exports_health_without_queue_zeroes(self):
        result = subprocess.run(
            [PERL, str(SOURCE), "--once"], capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("postfix_queue_scrape_success 0\n", result.stdout)
        self.assertNotIn("postfix_queue_messages", result.stdout)
        self.assertEqual(result.stderr, "")
