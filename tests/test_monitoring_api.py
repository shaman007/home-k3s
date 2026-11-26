"""Keep operator diagnostics read-only and outside sensitive audit operations."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from tools.ops import monitoring_api as api

ROOT = Path(__file__).resolve().parents[1]


class MonitoringApiTests(unittest.TestCase):
    """Guard credential boundaries and the API-only diagnostic path."""

    def test_grafana_rejects_external_urls_and_traversal(self):
        for path in ['https://example.com/api/user', '//example.com/api/user', '/api/%2e%2e/admin', '/login']:
            with self.subTest(path=path), self.assertRaises(ValueError):
                api.grafana_get(path)
        self.assertIsNone(api.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://example.com'))

    def test_only_consumer_environment_supplies_grafana_token(self):
        with patch.dict(api.os.environ, {}, clear=True), self.assertRaises(ValueError):
            api.grafana_get('/api/health')

    def test_alertmanager_uses_get_proxy_on_every_replica(self):
        calls = []
        def get(path):
            calls.append(path)
            if 'labelSelector' in path:
                return {'items': [{'metadata': {'name': n}, 'status': {'phase': 'Running'}} for n in ['am-a', 'am-b', 'am-c']]}
            return []
        with patch.object(api, 'kube_get', side_effect=get):
            result = api.alertmanager_get()
        self.assertEqual(3, len(result))
        self.assertEqual(4, len(calls))
        self.assertTrue(all('/proxy/api/v2/alerts' in path for path in calls[1:]))
        with self.assertRaises(ValueError):
            api.alertmanager_get('/api/v2/silences')

    def test_kubectl_never_execs_or_reads_secrets(self):
        with patch.object(api.subprocess, 'run') as run:
            run.return_value.stdout = '{}'
            api.kube_get('/api/v1/namespaces/monitoring/pods?labelSelector=app%3Dalertmanager')
        command = run.call_args.args[0]
        self.assertEqual(['kubectl', '--request-timeout=10s', 'get', '--raw'], command[:4])
        with self.assertRaises(ValueError):
            api.kube_get('/api/v1/namespaces/monitoring/secrets')
        self.assertNotIn('exec', command)
        self.assertNotIn('secrets', ' '.join(command))

    def test_network_access_is_limited_to_alertmanager_port(self):
        import yaml
        policy = yaml.safe_load((ROOT / 'metrics/cilium-network-policy-monitoring-allow-alertmanager-api.yaml').read_text())['spec']
        self.assertEqual({'app': 'alertmanager'}, policy['endpointSelector']['matchLabels'])
        ingress = policy['ingress'][0]
        self.assertEqual({'kube-apiserver', 'host', 'remote-node'}, set(ingress['fromEntities']))
        self.assertEqual([{'port': '9093', 'protocol': 'TCP'}], ingress['toPorts'][0]['ports'])
