"""Keep negative CLI resources noncompliant with their target policy."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('audit_cases', ROOT/'tools/kyverno/test-audit-policies.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class AuditFixtureTests(unittest.TestCase):
    def test_seccomp_negative_companion_is_unconfined(self):
        container = audit.noncompliant_container('restrict-seccomp-strict', 'unapproved')
        self.assertEqual(container['securityContext']['seccompProfile']['type'], 'Unconfined')

    def test_other_negative_fixtures_target_their_policy(self):
        for policy, field, expected in [
            ('require-run-as-nonroot', 'runAsNonRoot', False),
            ('disallow-privilege-escalation', 'allowPrivilegeEscalation', True),
            ('disallow-privileged-containers', 'privileged', True),
            ('require-drop-all-capabilities', 'capabilities', {'drop': ['ALL'], 'add': ['SYS_ADMIN']}),
        ]:
            with self.subTest(policy=policy):
                self.assertEqual(audit.noncompliant_container(policy, 'unapproved')['securityContext'][field], expected)


if __name__ == '__main__':
    unittest.main()
