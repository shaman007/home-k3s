"""Safety contracts for the explicit OpenBao TLS recovery stages; no live API."""
import importlib.util
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('transition', ROOT / 'tools/bootstrap/openbao_tls_transition.py')
transition = importlib.util.module_from_spec(spec)
spec.loader.exec_module(transition)


class OpenBaoTLSRecoverySafety(unittest.TestCase):
    def test_rollback_restores_exact_spec_and_never_puts_key_in_argv(self):
        old_key = 'TEST-ONLY-SENSITIVE-MARKER'
        old = {'metadata': {'annotations': {'issuer': 'old'}}, 'data': {'tls.key': old_key}}
        original = {'kind': 'Certificate', 'spec': {'issuerRef': {'name': 'old-issuer'}}}
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary)
            (state / 'baseline.json').write_text(json.dumps({'objects': [original]}))
            with mock.patch.object(transition, 'run', return_value=json.dumps([old]).encode()), \
                 mock.patch.object(transition, 'kube') as kube:
                transition.rollback(state)
        self.assertEqual(2, kube.call_count)
        cert_args = kube.call_args_list[0].args
        cert_patch = json.loads(cert_args[-1])
        self.assertEqual('replace', cert_patch[0]['op'])
        self.assertEqual('/spec', cert_patch[0]['path'])
        key_call = kube.call_args_list[1]
        self.assertIn('--patch-file=/dev/stdin', key_call.args)
        self.assertNotIn(old_key, ' '.join(str(x) for x in key_call.args))
        self.assertIn(old_key, key_call.kwargs['payload'].decode())
        data_patch = json.loads(key_call.kwargs['payload'])
        self.assertEqual({'op': 'replace', 'path': '/data', 'value': old['data']}, data_patch[0])

    def test_command_failure_does_not_echo_stderr_secrets(self):
        result = types.SimpleNamespace(returncode=1, stdout=b'', stderr=b'SENSITIVE-EXCEPTION-DATA')
        with mock.patch.object(transition.subprocess, 'run', return_value=result):
            with self.assertRaises(RuntimeError) as caught:
                transition.run(['kubectl', 'get', 'secret'])
        self.assertNotIn('SENSITIVE-EXCEPTION-DATA', str(caught.exception))

    def test_all_kubernetes_calls_pin_the_cluster_and_timeout(self):
        with mock.patch.object(transition, 'run', return_value=b'{}') as runner:
            transition.kube('get', 'pods', '-n', 'openbao')
        argv = runner.call_args.args[0]
        self.assertIn('--context=admin@home-k8s', argv)
        self.assertIn('--request-timeout=20s', argv)
        self.assertNotIn('apply', argv)

    def test_clean_snapshot_excludes_status_and_client_side_apply_payload(self):
        obj = {'apiVersion': 'v1', 'kind': 'ConfigMap', 'metadata': {'name': 'test',
               'uid': 'not-restorable', 'annotations': {
                   'kubectl.kubernetes.io/last-applied-configuration': 'OLD-DATA', 'keep': 'yes'}},
               'data': {'key': 'public'}, 'status': {'not': 'desired'}}
        clean = transition.clean(obj)
        self.assertNotIn('status', clean)
        self.assertNotIn('uid', clean['metadata'])
        self.assertEqual({'keep': 'yes'}, clean['metadata']['annotations'])


if __name__ == '__main__':
    unittest.main()
