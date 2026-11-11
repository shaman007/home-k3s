"""Security preconditions must survive Python's optimized execution mode."""

from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]


class OptimizedSecurityGuardsTest(unittest.TestCase):
    def test_rejection_and_preflight_cases_with_optimization(self):
        # These suites exercise malformed exception catalogs, changed workload
        # identities, unhealthy storage and absent admission mutations. They
        # must still reject those inputs when Python strips assert statements.
        for pattern in (
            "test_kyverno_capability_exceptions.py",
            "test_longhorn_component_security.py",
            "test_longhorn_recurring_security.py",
            "test_infra_guard_backfill.py",
        ):
            with self.subTest(pattern=pattern):
                result = subprocess.run(
                    [sys.executable, "-O", "-B", "-m", "unittest", "discover",
                     "-s", "tests", "-p", pattern, "-q"],
                    cwd=ROOT, capture_output=True, text=True, timeout=60,
                )
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
