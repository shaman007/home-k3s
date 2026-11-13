"""Failure, recovery and original-command preservation for inactive CronJob gates."""

import contextlib
import copy
import importlib.util
import io
import json
import subprocess  # nosec B404
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

import yaml

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    """Load a standalone repository tool without modifying sys.path."""
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "tools/bootstrap" / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GATE = load("cron_dependency_gate")
GENERATOR = load("prepare_cron_gate")


class CronDependencyTests(unittest.TestCase):
    """No provider success means no work, with bounded waiting and observable skip."""

    def setUp(self):
        self.config = {
            "mode": "skip",
            "budget_seconds": 3,
            "interval_seconds": 1,
            "probe_seconds": 1,
            "checks": [
                {
                    "name": "provider",
                    "url": "http://api.example.svc.cluster.local/ready",
                }
            ],
        }
        self.now = 0
        self.logs = []

    def advance(self, seconds):
        """Deterministic monotonic time without wall-clock waits."""
        self.now += seconds

    def wait(self, check_ready):
        """Use the real waiting loop with a synthetic provider and clock."""
        return GATE.wait(
            self.config,
            check_ready=check_ready,
            clock=lambda: self.now,
            sleep=self.advance,
            emit=self.logs.append,
        )

    def test_missing_provider_skips_and_fail_policy_is_not_success(self):
        """Missing provider skips and fail policy is not success."""
        self.assertEqual(self.wait(lambda *_: False), "skipped")
        self.assertEqual(self.now, 3)
        self.assertEqual(json.loads(self.logs[-1])["result"], "skipped")
        self.config["mode"] = "fail"
        self.assertEqual(self.wait(lambda *_: False), "unavailable")

    def test_recovery_before_budget_releases_work(self):
        """Recovery before budget releases work."""
        self.assertEqual(self.wait(lambda *_: self.now >= 2), "ready")
        self.assertEqual(self.now, 2)

    def test_all_providers_must_pass_same_iteration(self):
        """All providers must pass same iteration."""
        self.config["checks"].append(
            {"name": "second", "url": "http://b.example.svc.cluster.local/ready"}
        )
        self.assertEqual(
            self.wait(lambda c, _: (c["name"] == "provider") == (self.now % 2 == 0)),
            "skipped",
        )

    def test_probe_budget_is_capped_by_remaining_time(self):
        """Probe budget is capped by remaining time."""
        timeouts = []

        def check(_check, timeout):
            timeouts.append(timeout)
            self.advance(timeout)
            return False

        self.config["budget_seconds"] = 0.5
        self.assertEqual(self.wait(check), "skipped")
        self.assertEqual(timeouts, [0.5])

    def test_invalid_or_credential_bearing_config_never_probes(self):
        """Invalid or credential bearing config never probes."""
        urls = [
            "https://user:password@api.example.svc.cluster.local/ready",
            "http://public.example/",
            "file:///etc/passwd",
            "http://api.example.svc.cluster.local/ready?token=secret",
            "http://api.example.svc.cluster.local/ready#secret",
        ]
        for url in urls:
            config = copy.deepcopy(self.config)
            config["checks"][0]["url"] = url
            with self.subTest(url=url), self.assertRaises((ValueError, TypeError)):
                GATE.validate(config)
        for value in (float("nan"), float("inf"), -1, 301, True):
            config = copy.deepcopy(self.config)
            config["budget_seconds"] = value
            with self.subTest(value=value), self.assertRaises((ValueError, TypeError)):
                GATE.validate(config)

    def test_main_skips_without_exec_and_preserves_original_argv(self):
        """Main skips without exec and preserves original argv."""
        argv = [
            "gate.py",
            "--config",
            "fixture.json",
            "--",
            "python3",
            "/original.py",
            "literal arg",
        ]
        for result, expected in (("skipped", 0), ("unavailable", 75)):
            with (
                mock.patch.object(GATE.sys, "argv", argv),
                mock.patch.object(GATE.Path, "read_text", return_value="{}"),
                mock.patch.object(GATE, "wait", return_value=result),
                mock.patch.object(GATE.os, "execvp") as execute,
            ):
                self.assertEqual(GATE.main(), expected)
                execute.assert_not_called()
        with (
            mock.patch.object(GATE.sys, "argv", argv),
            mock.patch.object(GATE.Path, "read_text", return_value="{}"),
            mock.patch.object(GATE, "wait", return_value="ready"),
            mock.patch.object(GATE.os, "execvp") as execute,
        ):
            GATE.main()
            execute.assert_called_once_with(
                "python3", ["python3", "/original.py", "literal arg"]
            )

    def test_probe_timeout_and_error_are_sanitized(self):
        """Probe timeout and error are sanitized."""
        with mock.patch.object(
            GATE.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired("synthetic", 1),
        ):
            self.assertFalse(GATE.probe(self.config["checks"][0], 1))
        output = io.StringIO()
        with (
            contextlib.redirect_stdout(output),
            mock.patch.object(
                GATE.sys, "argv", ["gate", "--config", "fixture", "--", "work"]
            ),
            mock.patch.object(
                GATE.Path, "read_text", return_value='{"secret":"never-log-this"}'
            ),
        ):
            self.assertEqual(GATE.main(), 2)
        self.assertNotIn("never-log-this", output.getvalue())

    def test_real_exec_preserves_work_exit_and_skip_never_runs_work(self):
        """Exercise the real exec boundary in a disposable local process."""
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.json"
            config.write_text("{}")
            code = (
                "import importlib.util,sys; "
                "s=importlib.util.spec_from_file_location('g',sys.argv[1]); "
                "g=importlib.util.module_from_spec(s); s.loader.exec_module(g); "
                "result=sys.argv[3]; g.wait=lambda *a,**k:result; "
                "sys.argv=['gate','--config',sys.argv[2],'--',sys.executable,"
                "'-c','raise SystemExit(7)']; sys.exit(g.main())"
            )
            for result, expected in (("ready", 7), ("skipped", 0), ("unavailable", 75)):
                # Fixed local interpreter/code and synthetic configuration only.
                completed = subprocess.run(  # nosec B603
                    [sys.executable, "-c", code, GATE.__file__, str(config), result],
                    capture_output=True,
                    timeout=5,
                    check=False,
                )
                self.assertEqual(completed.returncode, expected, completed.stderr)

    def test_http_rejects_errors_and_redirects_without_following(self):
        """Http rejects errors and redirects without following."""
        hits = []

        class Handler(BaseHTTPRequestHandler):
            """Local readiness fixture; never logs request contents."""

            def do_GET(self):  # pylint: disable=invalid-name
                """Serve the fixed local health fixture."""
                hits.append(self.path)
                self.send_response(
                    200
                    if self.path == "/ready"
                    else 302
                    if self.path == "/redirect"
                    else 503
                )
                if self.path == "/redirect":
                    self.send_header("Location", "/ready")
                self.end_headers()

            def log_message(self, *_args):
                pass

        with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_port}"
                self.assertTrue(GATE.http_ready(base + "/ready", 1))
                self.assertFalse(GATE.http_ready(base + "/missing", 1))
                self.assertFalse(GATE.http_ready(base + "/redirect", 1))
                self.assertEqual(hits, ["/ready", "/missing", "/redirect"])
                self.assertTrue(GATE.probe({"url": base + "/ready"}, 3))
            finally:
                server.shutdown()
                thread.join()

    def test_candidate_is_inactive_preserves_work_and_existing_policies(self):
        """Candidate is inactive preserves work and existing policies."""
        original_path = ROOT / "metrics/cron-job-logs-check.yaml"
        before = original_path.read_bytes()
        original = yaml.safe_load(before)
        config_map, job = GENERATOR.candidate()
        pod = job["spec"]["jobTemplate"]["spec"]["template"]["spec"]
        old_pod = original["spec"]["jobTemplate"]["spec"]["template"]["spec"]
        wrapped = pod["containers"][0]
        self.assertEqual(wrapped["command"][5:], old_pod["containers"][0]["command"])
        for key in ("env", "image", "securityContext", "resources"):
            self.assertEqual(wrapped[key], old_pod["containers"][0][key])
        self.assertEqual(job["spec"]["schedule"], original["spec"]["schedule"])
        self.assertEqual(job["spec"]["concurrencyPolicy"], "Forbid")
        self.assertNotIn("suspend", job["spec"])
        self.assertEqual(
            config_map["data"]["gate.py"],
            (ROOT / "tools/bootstrap/cron_dependency_gate.py").read_text(),
        )
        config = GATE.validate(json.loads(config_map["data"]["config.json"]))
        self.assertEqual(
            config["checks"][0]["url"],
            "http://loki-gateway.loki.svc.cluster.local/loki/api/v1/labels",
        )
        self.assertEqual(original_path.read_bytes(), before)

    def test_only_reviewed_reports_get_versioned_immutable_configs(self):
        """No health reporter, backup or token renewal is silently skipped."""
        self.assertEqual(
            set(GENERATOR.REPORTS),
            {
                "logs-check",
                "external-access-daily-report",
                "wordpress-daily-report",
            },
        )
        for name in GENERATOR.REPORTS:
            cm, job = GENERATOR.candidate(name)
            self.assertIs(cm["immutable"], True)
            self.assertEqual(cm["metadata"]["namespace"], job["metadata"]["namespace"])
            pod = job["spec"]["jobTemplate"]["spec"]["template"]["spec"]
            self.assertEqual(
                pod["volumes"][-1]["configMap"]["name"], cm["metadata"]["name"]
            )
            self.assertEqual(GENERATOR.candidate(name), [cm, job])


if __name__ == "__main__":
    unittest.main()
