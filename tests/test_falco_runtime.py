"""Protect runtime sensor output privacy and the cross-namespace delivery boundary."""
import datetime
import http.server
import json
import os
import re
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

    def test_redirect_diagnostics_have_an_explicit_safe_field_allowlist(self):
        """Retain numeric/socket context without argv, env or exception widening."""
        values = yaml.safe_load((ROOT / 'falco/values.yaml').read_text())
        rules = yaml.safe_load(values['customRules']['runtime-safe-output.yaml'])
        redirect = next(r for r in rules if r['rule'] == 'Redirect STDOUT/STDIN to Network Connection in Container')
        diagnostic = {'proc.pid', 'thread.tid', 'evt.type', 'evt.rawres', 'fd.num', 'fd.type', 'fd.name'}
        existing = {'proc.name', 'proc.exepath', 'proc.pname', 'container.id', 'container.name',
                    'container.image.repository', 'k8s.ns.name', 'k8s.pod.name', 'user.uid'}
        self.assertEqual(existing | diagnostic, set(re.findall(r'%([a-zA-Z0-9_.]+)', redirect['output'])))
        self.assertEqual('and container.id != "runtime"', redirect['condition'])
        self.assertEqual({'rule', 'output', 'priority', 'override', 'condition', 'exceptions'}, set(redirect))
        self.assertEqual('WARNING', redirect['priority'])
        self.assertNotIn('argocd', redirect['condition'])
        docs = list(yaml.safe_load_all((ROOT / 'falco/sidekick.yaml').read_text()))
        config = yaml.safe_load(next(d for d in docs if d['kind'] == 'ConfigMap')['data']['config.yaml'])
        for field in diagnostic:
            self.assertEqual('', config['alertmanager']['extralabels'][field.replace('.', '_')])

    def test_backup_ssh_exception_is_limited_to_reviewed_inbound_socket(self):
        values = yaml.safe_load((ROOT / 'falco/values.yaml').read_text())
        rules = yaml.safe_load(values['customRules']['runtime-safe-output.yaml'])
        redirect = next(r for r in rules if r['rule'].startswith('Redirect STDOUT'))
        self.assertEqual('append', redirect['override']['exceptions'])
        self.assertEqual(1, len(redirect['exceptions']))
        exception = redirect['exceptions'][0]
        self.assertEqual(['='] * len(exception['fields']), exception['comps'])
        self.assertEqual(4, len(exception['values']))
        processes = set()
        descriptors = set()
        for row in exception['values']:
            self.assertEqual(len(exception['fields']), len(row))
            scope = dict(zip(exception['fields'], row))
            descriptors.add(scope.pop('fd.num'))
            processes.add((scope.pop('proc.name'), scope.pop('proc.exepath'), scope.pop('proc.pname')))
            self.assertEqual({
                'k8s.ns.name': 'backup-rsync', 'container.name': 'sshd',
                'container.image.repository': 'harbor.andreybondarenko.com/quay/panubo/sshd',
                'container.image.tag': '1.10.0', 'user.uid': 0, 'evt.type': 'dup2',
                'fd.type': 'ipv4', 'fd.l4proto': 'tcp',
                'fd.is_server': 'true', 'fd.cip': '192.168.30.79', 'fd.sport': 22,
            }, scope)
        self.assertEqual({0, 1}, descriptors)
        self.assertEqual({('sshd', '/usr/sbin/sshd', 'sshd'),
                          ('sshd-session', '/usr/lib/ssh/sshd-session', 'sshd-session')}, processes)
        for rule in rules:
            if rule is not redirect:
                self.assertNotIn('exceptions', rule)

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
                    for index, executable in enumerate(['/bin/sh', '/bin/sh', '/tmp/new-probe'] * 2):
                        timestamp = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=index)
                        payload = {
                            'rule':('Terminal shell in container' if index < 3 else 'Redirect STDOUT/STDIN to Network Connection in Container'), 'priority':'Warning', 'source':'syscall',
                            'time':timestamp.isoformat(), 'hostname':'fixture-node',
                            'output':'fixture-event-' + str(index), 'tags':['container'],
                            'output_fields':{'evt.time':int(timestamp.timestamp()*1e9),
                                             'proc.exepath':executable, 'proc.name':executable.rsplit('/',1)[-1],
                                             'proc.pname':'fixture-parent', 'container.id':'fixture-container',
                                             'k8s.ns.name':'fixture', 'k8s.pod.name':'fixture-pod', 'user.uid':65534},
                        }
                        if index >= 3:
                            number = index - 3
                            payload['output_fields'].update({
                                'proc.pid':1000+number, 'thread.tid':2000+number,
                                'evt.type':'dup3', 'evt.rawres':number,
                                'fd.num':30+number, 'fd.type':'ipv4',
                                'fd.name':f'127.0.0.1:{40000+number}->127.0.0.1:9000',
                            })
                            payload['output'] += f' | pid={1000+number} tid={2000+number} syscall=dup3 result={number} fd={30+number} fd_type=ipv4 connection=127.0.0.1:{40000+number}->127.0.0.1:9000'
                        request = urllib.request.Request(f'http://127.0.0.1:{port}/',
                            data=json.dumps(payload).encode(), headers={'Content-Type':'application/json'})
                        with urllib.request.urlopen(request, timeout=5) as response:
                            self.assertEqual(200, response.status)
                    for _ in range(100):
                        alerts = [a for url, body in received if url == '/api/v2/alerts' for a in body]
                        records = [entry for url, body in received if url == '/loki/api/v1/push'
                                   for stream in body['streams'] for entry in stream['values']]
                        if len(alerts) == 6 and len(records) == 6:
                            break
                        time.sleep(.1)
                    self.assertEqual(6, len(alerts))
                    self.assertEqual(6, len(records), 'Every detailed event must still reach Loki')
                    by_event = {a['annotations']['description'].split(' | ')[0]:a for a in alerts}
                    self.assertEqual(by_event['fixture-event-0']['labels'], by_event['fixture-event-1']['labels'])
                    self.assertNotEqual(by_event['fixture-event-0']['labels'], by_event['fixture-event-2']['labels'])
                    self.assertEqual('', by_event['fixture-event-0']['labels']['evt_time'])
                    self.assertIn('evt.time', json.dumps(records))
                    self.assertEqual(by_event['fixture-event-3']['labels'], by_event['fixture-event-4']['labels'])
                    self.assertNotEqual(by_event['fixture-event-3']['labels'], by_event['fixture-event-5']['labels'])
                    self.assertIn('pid=1000 tid=2000 syscall=dup3', by_event['fixture-event-3']['annotations']['description'])
                    self.assertIn('connection=127.0.0.1:40000->127.0.0.1:9000', by_event['fixture-event-3']['annotations']['description'])
                    events = [json.loads(line) for _, line in records
                              if json.loads(line)['rule'] == 'Redirect STDOUT/STDIN to Network Connection in Container']
                    self.assertEqual({1000, 1001, 1002}, {e['output_fields']['proc.pid'] for e in events})
                    self.assertEqual({2000, 2001, 2002}, {e['output_fields']['thread.tid'] for e in events})
                    self.assertEqual(3, len({e['output_fields']['fd.name'] for e in events}))
                    self.assertTrue(all(e['output_fields']['evt.type'] == 'dup3' for e in events))
                finally:
                    process.terminate()
                    process.wait(timeout=10)
