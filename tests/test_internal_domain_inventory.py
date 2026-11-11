"""Safety checks for the migration inventory's hostname-only output."""

import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/certificates/scan-internal-domain-usage.py"
spec = importlib.util.spec_from_file_location("domain_inventory", TOOL)
scanner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scanner)


class InternalDomainInventoryTest(unittest.TestCase):
    def test_complete_hostnames_and_fqdn_are_recognized(self):
        pattern = re.compile(scanner.PATTERN)
        for host in (
            "grafana.w386.k8s.my.lan",
            "api.k8s.my.lan",
            "openbao.openbao.svc.cluster.local",
            "host.local.",
        ):
            with self.subTest(host=host):
                self.assertEqual(pattern.findall("https://" + host + "/callback"), [host])
        for expression in (
            "self.language",
            "process.localhost",
            "foo.lan.evil.example",
            "config.localized",
        ):
            self.assertEqual(pattern.findall(expression), [])

    def test_scan_exports_hostnames_but_not_source_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "demo").mkdir()
            (root / "demo/config.txt").write_text(
                "password=fixture-secret-value url=https://grafana.w386.k8s.my.lan/\napi=https://api.k8s.my.lan\n"
            )
            (root / "demo/labels.yaml").write_text(
                "vault.w386.k8s.my.lan/token-policies: example\n"
            )
            (root / "demo/node_modules").mkdir()
            (root / "demo/node_modules/ignored.txt").write_text("ignored.w386.k8s.my.lan")
            output = root / "report.json"
            result = subprocess.run(
                [sys.executable, str(TOOL), "--root", str(root), "--output", str(output)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(output.read_text())
            self.assertNotIn("fixture-secret-value", output.read_text())
            self.assertEqual(report["counts"]["occurrences"], 3)
            self.assertEqual(
                set(report["counts"]["categories"]),
                {"ingress_hostname", "kubernetes_api", "metadata_annotation"},
            )
            subprocess.run(
                [sys.executable, str(TOOL), "--root", str(root), "--output", str(output)],
                check=True,
                capture_output=True,
            )
            self.assertEqual(json.loads(output.read_text())["counts"]["occurrences"], 3)


if __name__ == "__main__":
    unittest.main()
