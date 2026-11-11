"""Fixture generation must be import-safe, bounded and complete before output writes."""

from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/kyverno/provider-cache/fixtures.py"


def load():
    """Import the generator without running its explicit CLI entry point."""
    spec = importlib.util.spec_from_file_location("provider_cache_fixture", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ProviderCacheFixtureTests(unittest.TestCase):
    """Preserve complete snapshots and deliberately adverse resource cases."""

    def test_import_does_not_read_cluster_or_create_output(self):
        """Importing the helper cannot consume CLI arguments or launch a Kubernetes command."""
        with (
            patch("sys.argv", ["fixtures"]),
            patch("subprocess.check_output") as command,
            patch.object(Path, "mkdir") as mkdir,
        ):
            load()
        command.assert_not_called()
        mkdir.assert_not_called()

    def test_snapshots_have_fixed_bounded_commands_and_preserve_resource_variants(self):
        """Keep snapshots/status stripping and every original/privileged workload/Pod pair."""
        module = load()
        snapshots = [
            json.dumps({"items": [{"kind": kind, "status": {"private": True}}]})
            for kind in ("ValidatingPolicy", "PolicyException")
        ]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "fixtures"
            with (
                patch("sys.argv", ["fixtures", str(output)]),
                patch.object(module.subprocess, "check_output", side_effect=snapshots) as command,
                redirect_stdout(io.StringIO()),
            ):
                module.main()
            self.assertEqual(len(command.call_args_list), 2)
            for call, resource, extra in zip(
                command.call_args_list,
                ("validatingpolicies.policies.kyverno.io", "policyexceptions.policies.kyverno.io"),
                ([], ["-n", "kyverno"]),
            ):
                self.assertEqual(
                    call.args[0],
                    ["kubectl", "get", resource, *extra, "-o", "json", "--request-timeout=15s"],
                )
                self.assertEqual(call.kwargs, {"shell": False, "timeout": 30})
            for name, kind in (("policies", "ValidatingPolicy"), ("exceptions", "PolicyException")):
                self.assertEqual(
                    json.loads((output / f"kyverno-cache-{name}.json").read_text()),
                    [{"kind": kind}],
                )
            resources = json.loads((output / "kyverno-cache-resources.json").read_text())
            entries = json.loads((ROOT / "kyverno/exception-catalog.json").read_text())["entries"]
            self.assertEqual(len(resources), len(entries) * 4)
            self.assertEqual(resources, module.resource_cases(ROOT))
            self.assertEqual(
                {p.name for p in output.iterdir()},
                {
                    "kyverno-cache-policies.json",
                    "kyverno-cache-exceptions.json",
                    "kyverno-cache-resources.json",
                },
            )

    def test_failed_collection_preserves_prior_files_and_creates_no_new_output(self):
        """A failed second API snapshot cannot leave a mixture of old and new fixtures."""
        module = load()
        for exists in (False, True):
            with self.subTest(existing=exists), tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "fixtures"
                if exists:
                    output.mkdir()
                    for name in ("policies", "exceptions", "resources"):
                        (output / f"kyverno-cache-{name}.json").write_text("retained")
                with (
                    patch("sys.argv", ["fixtures", str(output)]),
                    patch.object(
                        module.subprocess,
                        "check_output",
                        side_effect=[
                            '{"items": []}',
                            module.subprocess.TimeoutExpired("kubectl", 30),
                        ],
                    ),
                    patch.object(module, "resource_cases") as cases,
                ):
                    with self.assertRaises(module.subprocess.TimeoutExpired):
                        module.main()
                cases.assert_not_called()
                if exists:
                    self.assertTrue(all(p.read_text() == "retained" for p in output.iterdir()))
                else:
                    self.assertFalse(output.exists())
