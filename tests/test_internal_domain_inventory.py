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
TOOL = ROOT / "tools/certificates/scan_internal_domain_usage.py"
spec = importlib.util.spec_from_file_location("domain_inventory", TOOL)
scanner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scanner)


class InternalDomainInventoryTest(unittest.TestCase):
    """Find complete internal hostnames without exporting surrounding source secrets."""

    def test_complete_hostnames_and_fqdn_are_recognized(self):
        """Verify complete hostnames and fqdn are recognized."""
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
        """Verify scan exports hostnames but not source secrets."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "demo").mkdir()
            (root / "demo/config.txt").write_text(
                (
                    "password=fixture-secret-value "
                    "url=https://grafana.w386.k8s.my.lan/\napi"
                    "=https://api.k8s.my.lan\n"
                )
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


class DomainInventoryTests(unittest.TestCase):
    """Verify report privacy and classification precedence using synthetic files."""

    def test_annotation_precedes_ingress_and_source_is_not_copied(self):
        """Metadata hostnames stay metadata even when an ingress replacement exists."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "repo" / "config.yaml"
            path.parent.mkdir()
            path.write_text("private-marker /token-policies host=APP.MY.LAN.\n")
            entries = scanner.collect_entries(
                f"{path}:1:APP.MY.LAN.\n", root, {"app.my.lan": "public.example"}
            )
        self.assertEqual(
            entries,
            [
                {
                    "repository": "repo",
                    "path": "repo/config.yaml",
                    "line": 1,
                    "hostname": "app.my.lan",
                    "category": "metadata_annotation",
                    "usage": "configuration_or_code",
                    "replacement": "public.example",
                }
            ],
        )
        self.assertNotIn("private-marker", str(entries))

    def test_cluster_service_is_not_a_dot_local_candidate(self):
        """Cluster service names must not be mistaken for migration candidates."""
        for host in ("backend.svc", "backend.ns.svc.cluster.local"):
            with self.subTest(host=host):
                self.assertEqual(scanner.hostname_category(host, {}, False), "cluster_service")
        self.assertEqual(
            scanner.hostname_category("printer.local", {}, False),
            "dot_local_candidate_requires_review",
        )

    def test_test_paths_take_precedence_over_documentation(self):
        """Documentation fixtures remain tests while historical artifacts remain distinguishable."""
        for name, expected in (
            ("repo/tests/fixture.md", "tests"),
            ("repo/docs/guide.md", "documentation"),
            ("repo/docs/snapshot.yaml", "staged_or_historical_artifact"),
            ("repo/app/config.yaml", "configuration_or_code"),
        ):
            path = Path(name)
            with self.subTest(path=name):
                self.assertEqual(scanner.path_usage(path, path.parts), expected)


if __name__ == "__main__":
    unittest.main()
