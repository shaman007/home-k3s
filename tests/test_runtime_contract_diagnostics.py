"""Validation failures must not include manifest credential values."""

import importlib.util
from pathlib import Path
import tempfile
import traceback
import unittest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "runtime_contract_diagnostics", ROOT / "tools/ci/validate-runtime-contracts.py"
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
