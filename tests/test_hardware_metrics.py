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

    def test_device_discovery_rejects_non_disk_names_and_deduplicates_nvme(self):
        """Only anchored SATA/NVMe sysfs names may become command arguments."""
        names = [
            "sda",
            "sdab",
            "nvme0n1",
            "nvme0n2",
            "nvme2n1",
            "loop0",
            "sda;id",
            "--help",
            "nvme0n1-extra",
            "sdA",
            "nvme0",
        ]
        with patch.object(
            collector.Path, "iterdir", return_value=[Path("/sys/block") / name for name in names]
        ):
            self.assertEqual(
                collector.smart_devices(),
                [Path("/dev/nvme0"), Path("/dev/nvme2"), Path("/dev/sda"), Path("/dev/sdab")],
            )

    def test_gpu_collection_uses_fixed_executable_and_bounded_argv(self):
        """GPU telemetry cannot select another executable or omit its execution deadline."""
        response = SimpleNamespace(returncode=1, stdout="")
        with patch.object(collector.subprocess, "run", return_value=response) as run:
            lines = collector.gpu_metrics()
        argv = run.call_args.args[0]
        self.assertEqual(argv[0], "/usr/bin/nvidia-smi")
        self.assertEqual(len(argv), 3)
        self.assertTrue(argv[1].startswith("--query-gpu=index,name,uuid,"))
        self.assertEqual(argv[2], "--format=csv,noheader,nounits")
        self.assertEqual(
            run.call_args.kwargs,
            {
                "check": False,
                "capture_output": True,
                "text": True,
                "timeout": 20,
            },
        )
        self.assertIn("linux_host_gpu_collector_success 0", lines)

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
