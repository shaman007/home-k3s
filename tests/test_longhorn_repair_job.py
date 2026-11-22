"""One-off repair cleanup must never discard unsuccessful diagnostics early."""

from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from tools.longhorn import repair_job


class RepairJobTests(unittest.TestCase):
    def test_manifest_preserves_workload_but_not_cronjob_tracking(self):
        source = {'spec': {'jobTemplate': {
            'metadata': {'labels': {'app.kubernetes.io/instance': 'longhorn',
                                    'recurring-job.longhorn.io': 'trim-daily-a'},
                         'annotations': {'argocd.argoproj.io/tracking-id': 'source'}},
            'spec': {'ttlSecondsAfterFinished': 10, 'template': {
                'spec': {'containers': [{'name': 'trim', 'image': 'existing'}]}}}}}}
        original = deepcopy(source)
        job = repair_job.job_manifest(source, 'trim-daily-a-repair-test')
        self.assertEqual(source, original)
        self.assertEqual(job['spec']['template'], source['spec']['jobTemplate']['spec']['template'])
        self.assertEqual(job['spec']['ttlSecondsAfterFinished'], 86400)
        self.assertNotIn('annotations', job['metadata'])
        self.assertNotIn('ownerReferences', job['metadata'])
        self.assertNotIn('app.kubernetes.io/instance', job['metadata']['labels'])

    def run_state(self, conditions, uid='original'):
        calls = []
        job = {'metadata': {'uid': uid, 'resourceVersion': '17'},
               'status': {'succeeded': 1, 'conditions': conditions}}

        def kubectl(verb, *args):
            calls.append((verb, args))
            return job

        return kubectl, calls

    def test_success_shortens_ttl_with_identity_and_version_guards(self):
        kubectl, calls = self.run_state([{'type': 'Complete', 'status': 'True'}])
        repair_job.retain_success(kubectl, 'repair', 'original', 10)
        patch = json.loads(calls[-1][1][-1])
        self.assertEqual(patch, [
            {'op': 'test', 'path': '/metadata/uid', 'value': 'original'},
            {'op': 'test', 'path': '/metadata/resourceVersion', 'value': '17'},
            {'op': 'add', 'path': '/spec/ttlSecondsAfterFinished', 'value': 60}])

    def test_failed_or_replaced_job_is_never_patched(self):
        for conditions, uid in [([{'type': 'Failed', 'status': 'True'}], 'original'),
                                ([{'type': 'Complete', 'status': 'True'}], 'replacement')]:
            with self.subTest(uid=uid, conditions=conditions):
                kubectl, calls = self.run_state(conditions, uid)
                with self.assertRaises(RuntimeError):
                    repair_job.retain_success(kubectl, 'repair', 'original', 10)
                self.assertEqual([verb for verb, _ in calls], ['get'])

    def test_success_count_alone_does_not_authorize_cleanup(self):
        kubectl, calls = self.run_state([{'type': 'SuccessCriteriaMet', 'status': 'True'}])
        ticks = iter([0, 0, 11, 11])
        with self.assertRaisesRegex(RuntimeError, 'timed out'):
            repair_job.retain_success(kubectl, 'repair', 'original', 10,
                                      clock=lambda: next(ticks), sleep=lambda _: None)
        self.assertEqual([verb for verb, _ in calls], ['get'])

    def test_default_plan_never_calls_kubernetes(self):
        with patch.object(repair_job, 'run_command') as runner:
            with patch('builtins.print'):
                self.assertEqual(repair_job.main(['trim-daily-a']), 0)
            runner.assert_not_called()

    def test_execute_creates_then_shortens_only_completed_job(self):
        from types import SimpleNamespace
        cronjob = {'spec': {'jobTemplate': {'spec': {'template': {
            'spec': {'containers': [{'name': 'trim', 'image': 'existing'}]}}}}}}
        completed = {'metadata': {'uid': 'original', 'resourceVersion': '17'},
                     'status': {'conditions': [{'type': 'Complete', 'status': 'True'}]}}
        results = [cronjob, {'metadata': {'uid': 'original'}}, completed, {}]
        with patch.object(repair_job, 'user_executable', return_value='/usr/bin/kubectl'):
            with patch.object(repair_job, 'run_command', side_effect=[
                SimpleNamespace(returncode=0, stdout=json.dumps(item)) for item in results
            ]) as runner:
                with patch('builtins.print'):
                    self.assertEqual(repair_job.main(['trim-daily-b', '--execute']), 0)
        commands = [call.args[0] for call in runner.call_args_list]
        self.assertEqual([command[1] for command in commands], ['get', 'create', 'get', 'patch'])
        for command in commands:
            self.assertIn('admin@home-k8s', command)
            self.assertIn('longhorn-system', command)
        created = json.loads(runner.call_args_list[1].kwargs['input'])
        self.assertEqual(created['spec']['ttlSecondsAfterFinished'], 86400)
        self.assertTrue(created['metadata']['name'].startswith('trim-daily-b-repair-'))
