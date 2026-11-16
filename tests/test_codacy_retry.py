"""Retries must preserve analyzer failure gates and discard only incomplete SARIF."""

import os
from pathlib import Path
import subprocess  # nosec B404
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
ACTION = yaml.safe_load((ROOT / ".github/actions/codacy-scan/action.yml").read_text())

WORKFLOW = yaml.safe_load((ROOT / ".github/workflows/codacy.yml").read_text())
STEPS = WORKFLOW["jobs"]["codacy-security-scan"]["steps"]


class CodacyRetryTests(unittest.TestCase):
    """Keep persistent failures fatal and prevent stale reports or broad deletion."""

    def test_attempts_preserve_rules_and_final_failure_is_fatal(self):
        """Every retry scans identically, and the final attempt cannot mask failure."""
        attempts = [step for step in STEPS if step.get("id", "").startswith("attempt_")]
        self.assertEqual(len(attempts), 3)
        self.assertTrue(all(step["with"] == attempts[0]["with"] for step in attempts))
        self.assertTrue(all(step["uses"] == attempts[0]["uses"] for step in attempts))
        scanner = ACTION["runs"]["steps"][0]
        self.assertEqual(scanner["shell"], "bash")
        self.assertNotIn("continue-on-error", scanner)
        self.assertTrue(all(step["timeout-minutes"] == 20 for step in attempts))
        self.assertGreater(WORKFLOW["jobs"]["codacy-security-scan"]["timeout-minutes"], 60)
        self.assertTrue(attempts[0]["continue-on-error"])
        self.assertTrue(attempts[1]["continue-on-error"])
        self.assertFalse(attempts[2].get("continue-on-error", False))
        self.assertEqual(attempts[1]["if"], "steps.attempt_1.outcome == 'failure'")
        self.assertEqual(attempts[2]["if"], "steps.attempt_2.outcome == 'failure'")

    def test_container_receives_utf8_and_failure_remains_fatal(self):
        """Exercise real command construction and cleanup with a recording Docker stub."""
        script = ROOT / ".github/actions/codacy-scan/run.sh"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            docker = root / "docker"
            docker.write_text(
                '#!/bin/bash\n'
                'if [[ "$1" == run ]]; then\n'
                '  printf "%s\\n" "$@" > "$DOCKER_ARGS"\n'
                '  exit "$SCAN_EXIT"\n'
                'fi\n'
                'printf "%s\\n" "$@" > "$CLEANUP_ARGS"\n'
            )
            docker.chmod(0o755)
            for exit_code in (0, 7):
                with self.subTest(exit_code=exit_code):
                    result = subprocess.run(
                        ["/bin/bash", str(script)], cwd=ROOT,
                        env={**os.environ, "PATH": directory + ":/usr/bin:/bin",
                             "CODACY_TOOL": "bandit", "CODACY_OUTPUT": "results-bandit.sarif",
                             "GITHUB_WORKSPACE": directory, "GITHUB_RUN_ID": "123",
                             "GITHUB_RUN_ATTEMPT": "1", "SCAN_EXIT": str(exit_code),
                             "DOCKER_ARGS": str(root / "args"),
                             "CLEANUP_ARGS": str(root / "cleanup")},
                        capture_output=True, text=True, timeout=5, check=False,
                    )
                    self.assertEqual(result.returncode, exit_code, result.stderr)
                    args = (root / "args").read_text().splitlines()
                    self.assertIn("JAVA_TOOL_OPTIONS=-Dfile.encoding=UTF-8", args)
                    self.assertIn("--fail-if-incomplete", args)
                    self.assertEqual(args[args.index("--tool-timeout") + 1], "20minutes")
                    self.assertEqual(args[args.index("--format") + 1], "sarif")
                    self.assertIn("@sha256:", next(a for a in args if a.startswith("codacy/")))
                    self.assertEqual((root / "cleanup").read_text().splitlines(),
                                     ["rm", "--force", "codacy-123-1-bandit"])

    def test_retry_removes_stale_report_and_preserves_other_files(self):
        """Execute each real retry shell fragment with a disposable stale scan report."""
        for step in STEPS:
            if not step["name"].startswith("Prepare retry"):
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
        cleanup = next(step["run"] for step in STEPS if step["name"].startswith("Prepare retry"))
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
