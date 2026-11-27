"""Render real Alertmanager templates; no SMTP or cluster access."""
import json
import os
from pathlib import Path
import shutil
import subprocess  # nosec B404 -- installed amtool, local templates only
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
AMTOOL = os.environ.get('AMTOOL_BINARY') or shutil.which('amtool')


def fixture(name, **labels):
    labels = dict(alertname=name, priority='warning', **labels)
    alert = dict(status='firing', labels=labels,
                 annotations={'summary': 'Example', 'description': 'Details https://example.invalid/runbook'},
                 startsAt='2026-11-27T10:18:35Z', endsAt='2026-11-27T10:28:35Z',
                 generatorURL='https://example.invalid/prometheus', fingerprint='fixture')
    return dict(receiver='alert-emailer', status='firing', alerts=[alert],
                groupLabels={'alertname': name}, commonLabels=dict(labels),
                commonAnnotations=alert['annotations'], externalURL='https://example.invalid')


class EmailLanguageTests(unittest.TestCase):
    def test_email_probe_does_not_notify_telegram(self):
        cm = yaml.safe_load((ROOT / 'metrics/kubernetes-prometheus/config-map-alertmanager-config.yaml').read_text())
        config = yaml.safe_load(cm['data']['config.yml'])
        route = config['route']['routes'][0]
        self.assertEqual('email-format-test', route['receiver'])
        self.assertEqual(['alertname="NotificationEmailTest"', 'notification_test="true"'], route['matchers'])
        receiver = next(r for r in config['receivers'] if r['name'] == route['receiver'])
        self.assertNotIn('telegram_configs', receiver)
        self.assertEqual(config['receivers'][0]['email_configs'], receiver['email_configs'])

    def test_email_copy_is_english(self):
        cm = yaml.safe_load((ROOT / 'metrics/kubernetes-prometheus/alert.yaml').read_text())
        self.assertNotRegex(cm['data']['homelab-email.tmpl'], r'[\u0400-\u04ff]')
        self.assertIn('<html lang="en">', cm['data']['homelab-email.tmpl'])


@unittest.skipUnless(AMTOOL, 'install amtool or set AMTOOL_BINARY for rendering')
class EmailRenderingTests(unittest.TestCase):
    def render(self, data, part='text'):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            cm = yaml.safe_load((ROOT / 'metrics/kubernetes-prometheus/alert.yaml').read_text())
            for name, text in cm['data'].items():
                (tmp / name).write_text(text)
            (tmp / 'data.json').write_text(json.dumps(data))
            result = subprocess.run([AMTOOL, 'template', 'render',
                '--template.glob=' + str(tmp / '*.tmpl'),
                '--template.data=' + str(tmp / 'data.json'),
                '--template.type=' + ('html' if part == 'html' else 'text'),
                '--template.text={{ template "homelab.email.' + part + '" . }}'],
                check=True, capture_output=True, text=True)
            return result.stdout

    def test_audit_is_honest_about_missing_event_details(self):
        data = fixture('KubernetesUnexpectedSecretRead', job='kubernetes-audit',
                       node='w386', namespace='kube-system', outcome='allowed',
                       owner='homelab', cluster='prometheus')
        text = self.render(data)
        self.assertIn('Secret read outside exceptions', text)
        self.assertIn('request allowed', text)
        self.assertIn('Actor, target and event count', text)
        self.assertIn('API server: w386', text)
        self.assertIn('11:18:35 CET', text)
        for noise in ['kube-system', 'owner', 'prometheus', 'Labels:', 'Annotations:']:
            self.assertNotIn(noise, text)
        self.assertEqual('Review · Secret read outside exceptions · w386',
                         self.render(data, 'subject'))

    def test_group_keeps_each_target_and_html_escapes_payload(self):
        data = fixture('Redirect STDOUT/STDIN to Network Connection in Container',
                       job='falco', k8s_ns_name='metallb-system', k8s_pod_name='frr-a')
        data['alerts'][0]['annotations']['description'] = 'dup3 fd=0 <script>alert(1)</script>'
        other = json.loads(json.dumps(data['alerts'][0]))
        other['labels']['k8s_pod_name'] = 'frr-b'
        data['alerts'].append(other)
        data['commonLabels'].pop('k8s_pod_name')
        text = self.render(data)
        self.assertIn('Pod: frr-a', text)
        self.assertIn('Pod: frr-b', text)
        self.assertIn('dup3 fd=0', text)
        self.assertIn('targets: 2', self.render(data, 'subject'))
        html = self.render(data, 'html')
        self.assertNotIn('<script>', html)
        self.assertIn('&lt;script&gt;', html)

    def test_html_has_one_action_button_and_separate_event_cards(self):
        data = fixture('KubeJobFailed', namespace='longhorn-system', job_name='trim-example')
        html = self.render(data, 'html')
        self.assertIn('href="https://example.invalid/#/alerts"', html)
        self.assertEqual(1, html.count('View in Alertmanager'))
        self.assertNotIn('https://example.invalid/runbook', html)
        self.assertIn('trim-example', html)
        for field in ['Started', 'Status', 'Namespace', 'Job', 'Rule']:
            self.assertIn('<strong>' + field + ':</strong>', html)
        self.assertNotIn('<strong>', self.render(data))
        self.assertIn('role="presentation"', html)
        self.assertIn('background-color:#fef3c7', html)
        data['commonLabels']['priority'] = 'critical'
        self.assertIn('background-color:#fee2e2', self.render(data, 'html'))

    def test_target_down_subject_identifies_the_source(self):
        data = fixture('TargetDown', job='alertmanager')
        self.assertEqual('Review · Monitoring target unreachable · alertmanager',
                         self.render(data, 'subject'))

    def test_critical_and_unknown_rules_keep_useful_context(self):
        data = fixture('SomeFutureRule', job='exporter', namespace='mail',
                       instance='mail:9090', device='disk-a')
        data['commonLabels']['priority'] = 'critical'
        self.assertTrue(self.render(data, 'subject').startswith('Urgent · Example'))
        text = self.render(data)
        for expected in ['Details', 'Endpoint: mail:9090', 'Device: disk-a', 'Rule: SomeFutureRule']:
            self.assertIn(expected, text)
        self.assertEqual(1, text.count('https://'))
        self.assertIn('View in Alertmanager: https://example.invalid/#/alerts', text)
        data['status'] = 'resolved'
        data['alerts'][0]['status'] = 'resolved'
        self.assertTrue(self.render(data, 'subject').startswith('Resolved'))
