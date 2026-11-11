"""Secret selectors must stay data and fail before any Kubernetes command on invalid input."""

import base64
import importlib.util
import json
from pathlib import Path
import secrets
import subprocess
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "benchmark_key_fixture", Path(__file__).resolve().parents[1] / "tools/benchmark_credentials.py"
)
credentials = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(credentials)


class BenchmarkCredentialTests(unittest.TestCase):
    """Preserve key selection while rejecting flag injection and bounding external work."""

    def test_invalid_selectors_fail_before_process_creation(self):
        """Namespace/name syntax cannot carry flags, extra paths or shell expressions."""
        for reference in (
            "missing",
            "ns/name/extra",
            "/name",
            "ns/",
            "--raw/key",
            "ns/--raw=path",
            "ns/key;id",
            "ns/$(false)",
            "ns/key name",
            "Upper/key",
            "ns/key_name",
            "ns/..",
            "ns/a..b",
            "n" * 64 + "/key",
            "ns/" + "k" * 254,
        ):
            with (
                self.subTest(reference=reference),
                patch.object(credentials.subprocess, "check_output") as command,
            ):
                with self.assertRaises(ValueError):
                    credentials.load_api_key(reference)
                command.assert_not_called()

    def test_valid_selector_retains_key_and_deadlines(self):
        """A valid secret overrides the environment through fixed read-only bounded argv."""
        marker = secrets.token_urlsafe(18)
        document = {"data": {"key": base64.b64encode(("  " + marker + "\n").encode()).decode()}}
        with patch.object(
            credentials.subprocess, "check_output", return_value=json.dumps(document)
        ) as command:
            self.assertEqual(credentials.load_api_key("123-ns/key.v2"), marker)
        command.assert_called_once_with(
            "kubectl get secret -n 123-ns key.v2 -o json --request-timeout=15s".split(),
            shell=False,
            timeout=30,
        )
        self.assertEqual(
            credentials.secret_reference("n" * 63 + "/" + "k" * 253), ("n" * 63, "k" * 253)
        )

    def test_environment_key_needs_no_kubernetes_process(self):
        """No secret selector preserves the existing environment-only behavior."""
        marker = secrets.token_urlsafe(18)
        with (
            patch.dict(credentials.os.environ, {"LLM_API_KEY": marker}),
            patch.object(credentials.subprocess, "check_output") as command,
        ):
            self.assertEqual(credentials.load_api_key(None), marker)
        command.assert_not_called()

    def test_lookup_failure_never_falls_back_to_another_key(self):
        """A timed-out selected secret cannot silently use an unrelated environment credential."""
        with (
            patch.dict(credentials.os.environ, {"LLM_API_KEY": secrets.token_urlsafe(18)}),
            patch.object(
                credentials.subprocess,
                "check_output",
                side_effect=subprocess.TimeoutExpired("kubectl", 30),
            ),
        ):
            with self.assertRaises(subprocess.TimeoutExpired):
                credentials.load_api_key("fixture/key")
