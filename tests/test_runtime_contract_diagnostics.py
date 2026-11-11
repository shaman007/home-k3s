"""Validation failures must not include manifest credential values."""

import importlib.util
from contextlib import redirect_stdout
import io
from pathlib import Path
import tempfile
import traceback
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "runtime_contract_diagnostics", ROOT / "tools/ci/validate_runtime_contracts.py"
)
contracts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contracts)


class RuntimeContractDiagnosticsTest(unittest.TestCase):
    """Require manifest diagnostics to retain locations without exposing sensitive values."""

    def test_external_secret_errors_do_not_echo_manifest_values(self):
        """Verify external secret errors do not echo manifest values."""
        marker = "synthetic-sensitive-value-must-not-be-logged"
        for kind in ("ExternalSecret", "SecretStore", "ClusterSecretStore", "Secret"):
            for target in (None, {}, {"name": marker}):
                with self.subTest(kind=kind, target=target):
                    document = {
                        "kind": kind,
                        "spec": {
                            "target": target,
                            "refreshInterval": marker,
                            "data": [{"secretKey": marker, "remoteRef": {"key": marker}}],
                        },
                        "data": {"password": marker},
                    }
                    errors = contracts.check_external_secret_targets(
                        Path("fixture.yaml"), 1, document
                    )
                    errors += contracts.check_secret_refresh_intervals(
                        Path("fixture.yaml"), 1, document
                    )
                    self.assertNotIn(marker, "\n".join(errors))
                    if kind != "Secret":
                        self.assertTrue(errors)

    def test_malformed_yaml_traceback_has_location_without_source_snippet(self):
        """Verify malformed YAML traceback has location without source snippet."""
        marker = "synthetic-parser-secret-must-not-be-logged"
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "fixture.yaml"
            path.write_text("kind: Secret\nstringData:\n  password: [" + marker + "\n")
            try:
                contracts.load_documents(path)
            except RuntimeError as error:
                diagnostic = "".join(traceback.format_exception(error))
                self.assertIn("unable to parse YAML at line", diagnostic)
                self.assertNotIn(marker, diagnostic)
                self.assertNotIn("yaml.parser.ParserError", diagnostic)
            else:
                self.fail("Malformed YAML was accepted")

    def test_main_logs_contracts_and_locations_without_secret_values(self):
        """Exercise the reported logging sink with secret-bearing invalid manifests."""
        marker = "synthetic-sensitive-value-never-log"
        documents = [
            (
                index,
                {
                    "kind": kind,
                    "spec": {"target": {}, "refreshInterval": marker},
                    "data": {"password": marker},
                },
            )
            for index, kind in enumerate(
                ["ExternalSecret", "SecretStore", "ClusterSecretStore", "Secret"], 1
            )
        ]
        output = io.StringIO()
        with (
            patch.object(contracts, "repo_root", return_value=ROOT),
            patch.object(contracts, "tracked_yaml_files", return_value=[ROOT / "fixture.yaml"]),
            patch.object(contracts, "load_documents", return_value=documents),
            redirect_stdout(output),
        ):
            self.assertEqual(contracts.main(), 1)
        logged = output.getvalue()
        self.assertIn("fixture.yaml: document", logged)
        self.assertIn("15m", logged)
        self.assertIn("900", logged)
        self.assertNotIn(marker, logged)
        self.assertNotIn("password", logged)
