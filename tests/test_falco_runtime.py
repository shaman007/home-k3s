"""Protect runtime sensor output privacy and the cross-namespace delivery boundary."""
from pathlib import Path
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]


class FalcoRuntimeTest(unittest.TestCase):
    """These are security/coverage contracts, not proof of actual BPF attachment."""

    def test_only_requested_rules_can_emit_sanitized_events(self):
        values = yaml.safe_load((ROOT / 'falco/values.yaml').read_text())
        controls = values['falco']['rules']
        self.assertEqual({'disable': {'rule': '*'}}, controls[0])
        selected = {control['enable']['rule'] for control in controls[1:]}
        overrides = yaml.safe_load(values['customRules']['runtime-safe-output.yaml'])
        self.assertEqual(selected, {rule['rule'] for rule in overrides})
        self.assertEqual(3, len(selected))
        forbidden = ('proc.cmdline', 'proc.args', 'proc.env', 'evt.args', 'user.name')
        for rule in overrides:
            for field in forbidden:
                self.assertNotIn(field, rule['output'])
            self.assertIn('%container.id', rule['output'])
            self.assertIn('%k8s.pod.name', rule['output'])
            self.assertEqual('replace', rule['override']['output'])
        self.assertFalse(values['falco']['json_include_message_property'])
        self.assertEqual([], values['falco']['append_output'])
        self.assertFalse(values['falcoctl']['artifact']['follow']['enabled'])

    def test_no_kubernetes_credentials_or_host_mounts_in_forwarder(self):
        for account in yaml.safe_load_all((ROOT / 'falco/service-accounts.yaml').read_text()):
            self.assertFalse(account['automountServiceAccountToken'])
        docs = list(yaml.safe_load_all((ROOT / 'falco/sidekick.yaml').read_text()))
        spec = next(d for d in docs if d['kind'] == 'Deployment')['spec']['template']['spec']
        self.assertFalse(spec['automountServiceAccountToken'])
        self.assertTrue(spec['securityContext']['runAsNonRoot'])
        self.assertFalse(any('hostPath' in v for v in spec['volumes']))
        config = yaml.safe_load(next(d for d in docs if d['kind'] == 'ConfigMap')['data']['config.yaml'])
        self.assertEqual('/api/v2/alerts', config['alertmanager']['endpoint'])
        self.assertEqual('warning', config['alertmanager']['extralabels']['priority'])
        self.assertEqual('falco', config['alertmanager']['extralabels']['job'])

    def test_delivery_policy_is_actually_in_argocd_inventory(self):
        app = yaml.safe_load((ROOT / 'argocd/application-monitoring-network-policy.yaml').read_text())
        self.assertIn('network-policy-monitoring-falco.yaml', app['spec']['source']['directory']['include'])
        policies = list(yaml.safe_load_all((ROOT / 'metrics/network-policy-monitoring-falco.yaml').read_text()))
        receiver = next(p for p in policies if p['metadata']['name'] == 'alertmanager-allow-falcosidekick')
        source = receiver['spec']['ingress'][0]['from'][0]
        self.assertEqual('kube-system', source['namespaceSelector']['matchLabels']['kubernetes.io/metadata.name'])
        self.assertEqual({'app': 'falcosidekick'}, source['podSelector']['matchLabels'])
        self.assertEqual([{'port': 9093, 'protocol': 'TCP'}], receiver['spec']['ingress'][0]['ports'])
