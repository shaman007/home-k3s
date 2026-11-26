"""Protect runtime sensor output privacy and the cross-namespace delivery boundary."""
import datetime
import http.server
import json
import os
from pathlib import Path
import socket
import subprocess  # nosec B404
import tempfile
import threading
import time
import unittest
import urllib.request

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


@unittest.skipUnless(os.environ.get('FALCOSIDEKICK_BINARY'),
                     'set FALCOSIDEKICK_BINARY for the native forwarding test')
class FalcosidekickGroupingTest(unittest.TestCase):
    """Exercise the deployed version against loopback sinks, never real receivers."""

    def test_time_does_not_split_alerts_but_different_executables_do(self):

        received = []

        class Sink(http.server.BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                received.append((self.path, json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
                self.send_response(200 if self.path == '/api/v2/alerts' else 204)
                self.end_headers()

            def log_message(self, *args):
                pass

        sink = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Sink)
        self.addCleanup(sink.server_close)
        self.addCleanup(sink.shutdown)
        threading.Thread(target=sink.serve_forever, daemon=True).start()
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        docs = list(yaml.safe_load_all((ROOT / 'falco/sidekick.yaml').read_text()))
        config = yaml.safe_load(next(d for d in docs if d['kind'] == 'ConfigMap')['data']['config.yaml'])
        config.update(listenaddress='127.0.0.1', listenport=port)
        for output in ['alertmanager', 'loki']:
            config[output]['hostport'] = f'http://127.0.0.1:{sink.server_port}'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.yaml'
            path.write_text(yaml.safe_dump(config))
            with (Path(directory) / 'sidekick.log').open('w+') as log:
                process = subprocess.Popen([os.environ['FALCOSIDEKICK_BINARY'], '-c', str(path)],
                                           stdout=log, stderr=log)
                try:
                    for _ in range(100):
                        if process.poll() is not None:
                            log.seek(0)
                            self.fail(log.read())
                        try:
                            with urllib.request.urlopen(f'http://127.0.0.1:{port}/ping', timeout=1):
                                break
                        except OSError:
                            time.sleep(.1)
                    else:
                        self.fail('Sidekick did not become ready')
                    for index, executable in enumerate(['/bin/sh', '/bin/sh', '/tmp/new-probe']):
                        timestamp = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=index)
                        payload = {
                            'rule':'Terminal shell in container', 'priority':'Warning', 'source':'syscall',
                            'time':timestamp.isoformat(), 'hostname':'fixture-node',
                            'output':'fixture-event-' + str(index), 'tags':['container'],
                            'output_fields':{'evt.time':int(timestamp.timestamp()*1e9),
                                             'proc.exepath':executable, 'proc.name':executable.rsplit('/',1)[-1],
                                             'proc.pname':'fixture-parent', 'container.id':'fixture-container',
                                             'k8s.ns.name':'fixture', 'k8s.pod.name':'fixture-pod', 'user.uid':65534},
                        }
                        request = urllib.request.Request(f'http://127.0.0.1:{port}/',
                            data=json.dumps(payload).encode(), headers={'Content-Type':'application/json'})
                        with urllib.request.urlopen(request, timeout=5) as response:
                            self.assertEqual(200, response.status)
                    for _ in range(100):
                        alerts = [a for url, body in received if url == '/api/v2/alerts' for a in body]
                        records = [entry for url, body in received if url == '/loki/api/v1/push'
                                   for stream in body['streams'] for entry in stream['values']]
                        if len(alerts) == 3 and len(records) == 3:
                            break
                        time.sleep(.1)
                    self.assertEqual(3, len(alerts))
                    self.assertEqual(3, len(records), 'Every detailed event must still reach Loki')
                    by_event = {a['annotations']['description']:a for a in alerts}
                    self.assertEqual(by_event['fixture-event-0']['labels'], by_event['fixture-event-1']['labels'])
                    self.assertNotEqual(by_event['fixture-event-0']['labels'], by_event['fixture-event-2']['labels'])
                    self.assertEqual('', by_event['fixture-event-0']['labels']['evt_time'])
                    self.assertIn('evt.time', json.dumps(records))
                finally:
                    process.terminate()
                    process.wait(timeout=10)
