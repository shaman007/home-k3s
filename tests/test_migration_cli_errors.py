"""Migration CLI diagnostics must not chain sensitive underlying exceptions."""

import ast
from pathlib import Path
import subprocess
import traceback
import unittest


ROOT = Path(__file__).resolve().parents[1]


class MigrationCliErrorsTest(unittest.TestCase):
    """Exercise the actual entry-point handlers without running migration operations."""

    def run_handler(self, relative_path, error):
        """Compile only the source entry point and substitute a failing main function."""
        path = ROOT / relative_path
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        entry = tree.body[-1]
        self.assertIsInstance(entry, ast.If)
        self.assertEqual(ast.unparse(entry.test), "__name__ == '__main__'")

        def fail():
            raise error

        namespace = {"__name__": "__main__", "main": fail, "subprocess": subprocess}
        program = ast.Module(body=[entry], type_ignores=[])
        with self.assertRaises(SystemExit) as caught:
            exec(compile(program, str(path), "exec"), namespace)
        return caught.exception

    def test_underlying_command_and_response_details_are_suppressed(self):
        """Generic traceback formatting must retain guidance and omit sensitive context."""
        cases = [
            (
                "tools/firefox-sync/migrate-mariadb.py",
                subprocess.CalledProcessError(1, ["sensitive-source-sentinel"]),
                "Keep Sync stopped",
            ),
            (
                "tools/certificates/inventory-sso.py",
                ValueError("sensitive-source-sentinel"),
                "details suppressed",
            ),
            (
                "tools/certificates/migrate-sso.py",
                ValueError("sensitive-source-sentinel"),
                "sensitive details suppressed",
            ),
        ]
        for path, error, guidance in cases:
            with self.subTest(path=path):
                result = self.run_handler(path, error)
                diagnostic = "".join(traceback.format_exception(result))
                self.assertIn(guidance, str(result))
                self.assertNotIn("sensitive-source-sentinel", diagnostic)

    def test_reviewed_runtime_guidance_is_preserved(self):
        """Operational precondition failures keep their actionable, sanitized message."""
        guidance = "Stop Firefox Sync before importing or comparing frozen data"
        result = self.run_handler("tools/firefox-sync/migrate-mariadb.py", RuntimeError(guidance))
        self.assertEqual(str(result), guidance)
        self.assertTrue(result.__suppress_context__)
