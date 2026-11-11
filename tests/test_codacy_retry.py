"""Retries must preserve analyzer failure gates and discard only incomplete SARIF."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
ACTION = yaml.safe_load((ROOT / ".github/actions/codacy-scan/action.yml").read_text())


class CodacyRetryTests(unittest.TestCase):
    """Keep persistent failures fatal and prevent stale reports or broad deletion."""

    def test_attempts_preserve_rules_and_final_failure_is_fatal(self):
        """Every retry scans identically, and the final attempt cannot mask failure."""
        attempts = [step for step in ACTION["runs"]["steps"] if "uses" in step]
        self.assertEqual(len(attempts), 3)
        self.assertTrue(all(step["with"] == attempts[0]["with"] for step in attempts))
        self.assertTrue(all(step["uses"] == attempts[0]["uses"] for step in attempts))
        self.assertIs(attempts[0]["with"]["fail-if-incomplete"], True)
        self.assertEqual(attempts[0]["with"]["format"], "sarif")
        self.assertTrue(attempts[0]["continue-on-error"])
        self.assertTrue(attempts[1]["continue-on-error"])
        self.assertFalse(attempts[2].get("continue-on-error", False))
        self.assertEqual(attempts[1]["if"], "steps.attempt_1.outcome == 'failure'")
        self.assertEqual(attempts[2]["if"], "steps.attempt_2.outcome == 'failure'")

    def test_retry_removes_stale_report_and_preserves_other_files(self):
        """Execute each real retry shell fragment with a disposable stale scan report."""
        for step in ACTION["runs"]["steps"]:
            if "run" not in step:
                continue
            with self.subTest(step=step["name"]), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                output = root / "results-bandit.sarif"
                output.write_text("incomplete stale report")
                output.chmod(0o444)
                unrelated = root / "retained.txt"
                unrelated.write_text("retained")
                sleep = root / "sleep"
                sleep.write_text("#!/bin/sh\nexit 0\n")
                sleep.chmod(0o755)
                result = subprocess.run(
                    ["/bin/bash", "-e", "-o", "pipefail", "-c", step["run"]],
                    cwd=root,
                    env={
                        **os.environ,
                        "SCAN_OUTPUT": output.name,
                        "PATH": directory + ":/usr/bin:/bin",
                    },
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertFalse(output.exists())
                self.assertEqual(unrelated.read_text(), "retained")

    def test_retry_rejects_paths_outside_scanner_basename(self):
        """Unsafe output paths fail before removal or waiting."""
        cleanup = next(step["run"] for step in ACTION["runs"]["steps"] if "run" in step)
        with tempfile.TemporaryDirectory() as directory:
            protected = Path(directory) / "retained.sarif"
            protected.write_text("retained")
            for output in (str(protected), "../results-bandit.sarif", "retained.sarif"):
                with self.subTest(output=output):
                    result = subprocess.run(
                        ["/bin/bash", "-e", "-o", "pipefail", "-c", cleanup],
                        cwd=directory,
                        env={**os.environ, "SCAN_OUTPUT": output},
                        capture_output=True,
                        text=True,
                        timeout=5,
                        check=False,
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(protected.read_text(), "retained")
