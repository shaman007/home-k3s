import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('restricted_contexts', ROOT / 'tools/ci/check-restricted-contexts.py')
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


class RestrictedContextTests(unittest.TestCase):
    def pod(self):
        return {'securityContext': {'runAsNonRoot': True, 'seccompProfile': {'type': 'RuntimeDefault'}},
                'containers': [{'name': 'app', 'securityContext': {
                    'allowPrivilegeEscalation': False, 'capabilities': {'drop': ['ALL']}}}]}

    def test_valid_pod_context_inheritance(self):
        self.assertEqual([], policy.violations(self.pod()))

    def test_container_cannot_override_nonroot_with_root(self):
        pod = self.pod()
        pod['containers'][0]['securityContext']['runAsUser'] = 0
        self.assertTrue(any('zero' in e for e in policy.violations(pod)))

    def test_root_init_container_is_also_checked(self):
        pod = self.pod()
        pod['initContainers'] = [{'name': 'permissions', 'securityContext': {'runAsUser': 0}}]
        self.assertTrue(any('permissions' in e and 'zero' in e for e in policy.violations(pod)))

    def test_forbidden_extra_capability_is_rejected(self):
        pod = self.pod()
        pod['containers'][0]['securityContext']['capabilities']['add'] = ['CHOWN']
        self.assertTrue(any('added capabilities' in e for e in policy.violations(pod)))

    def test_host_mount_cannot_hide_behind_valid_contexts(self):
        pod = self.pod()
        pod['volumes'] = [{'name': 'host', 'hostPath': {'path': '/'}}]
        self.assertIn('hostPath', policy.violations(pod))

    def test_cronjob_template_is_included(self):
        pod = self.pod()
        doc = {'kind': 'CronJob', 'spec': {'jobTemplate': {'spec': {'template': {'spec': pod}}}}}
        self.assertEqual([pod], list(policy.templates(doc)))


if __name__ == '__main__':
    unittest.main()
