"""Security preconditions must survive Python's optimized execution mode."""

import copy
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import yaml


ROOT = Path(__file__).resolve().parents[1]


class OptimizedSecurityGuardsTest(unittest.TestCase):
    """Require security preconditions to reject unsafe inputs even under Python optimization."""
    def test_mail_smoke_check_rejects_unsafe_context_in_optimized_mode(self):
        """Verify mail smoke check rejects unsafe context in optimized mode."""
        path = ROOT / "tools/security/test-mail-capability-guards.py"
        document = yaml.safe_load((ROOT / "mail/deployment-dovecot.yaml").read_text())
        for optimization in (0, 2):
            namespace = {"__name__": "mail_smoke_guard_fixture", "__file__": str(path)}
            exec(
                compile(path.read_text(), str(path), "exec", optimize=optimization), namespace
            )
            with patch.object(
                namespace["subprocess"], "run", side_effect=RuntimeError("Unexpected execution")
            ):
                with patch.object(namespace["yaml"], "safe_load", return_value=document):
                    arguments, _ = namespace["command"]("dovecot")
                    self.assertIn("--read-only", arguments)
                    self.assertIn("--cap-drop=ALL", arguments)
                for field, value in (
                    ("allowPrivilegeEscalation", True),
                    ("readOnlyRootFilesystem", False),
                    ("capabilities", {"add": ["SYS_ADMIN"]}),
                ):
                    with self.subTest(optimization=optimization, field=field):
                        unsafe = copy.deepcopy(document)
                        unsafe["spec"]["template"]["spec"]["containers"][0]["securityContext"][
                            field
                        ] = value
                        with patch.object(namespace["yaml"], "safe_load", return_value=unsafe):
                            with self.assertRaises(AssertionError):
                                namespace["command"]("dovecot")

    def test_rejection_and_preflight_cases_with_optimization(self):
        # These suites exercise malformed exception catalogs, changed workload
        # identities, unhealthy storage and absent admission mutations. They
        # must still reject those inputs when Python strips assert statements.
        """Verify rejection and preflight cases with optimization."""
        for pattern in (
            "test_kyverno_capability_exceptions.py",
            "test_longhorn_component_security.py",
            "test_longhorn_recurring_security.py",
            "test_infra_guard_backfill.py",
        ):
            with self.subTest(pattern=pattern):
                result = subprocess.run(
                    [
                        sys.executable,
                        "-O",
                        "-B",
                        "-m",
                        "unittest",
                        "discover",
                        "-s",
                        "tests",
                        "-p",
                        pattern,
                        "-q",
                    ],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                )
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
