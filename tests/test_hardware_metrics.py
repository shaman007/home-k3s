"""Protect SMART failure visibility and standby-safe collection without hardware access."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "hardware_metrics",
    Path(__file__).resolve().parents[1]
    / "metrics/linux-host-node-exporter/collect_hardware_metrics.py",
)
collector = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collector)


class HardwareMetricsTests(unittest.TestCase):
    """Verify unhealthy disks remain visible and unreadable data cannot appear successful."""

    def test_failed_health_is_readable_and_does_not_retry(self):
        """SMART failure exit bits must not hide a readable failing health assessment."""
        response = SimpleNamespace(
            returncode=8, stdout=json.dumps({"smart_status": {"passed": False}})
        )
        with (
            patch.object(collector, "smart_devices", return_value=[Path("/dev/sda")]),
            patch.object(collector.subprocess, "run", return_value=response) as run,
            patch.object(collector.time, "sleep") as sleep,
        ):
            lines = collector.smart_metrics()
        self.assertIn("linux_host_smart_collector_success 1", lines)
        self.assertTrue(
            any(
                line.startswith("linux_host_smart_health_passed{") and line.endswith(" 0")
                for line in lines
            )
        )
        self.assertEqual(run.call_count, 1)
        self.assertEqual(
            run.call_args.args[0], ["/usr/bin/smartctl", "-n", "standby", "-a", "-j", "/dev/sda"]
        )
        sleep.assert_not_called()

    def test_invalid_json_retries_once_and_reports_failure(self):
        """Two malformed responses produce explicit scrape and collector failures."""
        response = SimpleNamespace(returncode=0, stdout="invalid-json")
        with (
            patch.object(collector, "smart_devices", return_value=[Path("/dev/nvme0")]),
            patch.object(collector.subprocess, "run", return_value=response) as run,
            patch.object(collector.time, "sleep") as sleep,
        ):
            lines = collector.smart_metrics()
        self.assertIn('linux_host_smart_scrape_success{device="nvme0"} 0', lines)
        self.assertIn("linux_host_smart_collector_success 0", lines)
        self.assertEqual(run.call_count, 2)
        self.assertEqual(run.call_args.args[0], ["/usr/bin/smartctl", "-a", "-j", "/dev/nvme0"])
        sleep.assert_called_once_with(1)

    def test_nonfinite_statistics_are_omitted(self):
        """Unavailable numeric values cannot enter Prometheus output as NaN or infinity."""
        lines = []
        collector.append_smart_statistics(
            lines,
            {
                "temperature": {"current": "NaN"},
                "power_on_time": {"hours": "inf"},
                "nvme_smart_health_information_log": {"media_errors": 3},
            },
            {"device": "nvme0"},
        )
        self.assertEqual(lines, ['linux_host_smart_nvme_media_errors_total{device="nvme0"} 3'])
