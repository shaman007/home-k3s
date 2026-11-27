"""Exercise the actual Alloy pipeline with synthetic audit events and a local Loki sink.

ALLOY_BINARY=/path/to/alloy python3 -m unittest tests.test_kubernetes_audit
No cluster access, credentials or external network calls.
"""
import datetime
import ctypes
import ctypes.util
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


def free_port():
    """Reserve a loopback port temporarily."""
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def event(identity, *, resource='secrets', verb='get', namespace='openbao',
          name='example', stage='ResponseComplete', code=200, subresource='',
          annotations=None, impersonated=None):
    """Use a fabricated secret marker to prove payloads never reach Loki."""
    obj = {
        'apiVersion': 'audit.k8s.io/v1', 'kind': 'Event', 'auditID': identity,
        'stage': stage, 'stageTimestamp': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'verb': verb, 'user': {'username': 'human'},
        'objectRef': {'resource': resource, 'namespace': namespace, 'name': name,
                      'subresource': subresource},
        'responseStatus': {'code': code}, 'annotations': annotations or {},
        'requestURI': '/api/v1?command=FABRICATED-SECRET-MARKER',
        'requestObject': {'data': {'password': 'FABRICATED-SECRET-MARKER'}},
        'responseObject': {'data': {'token': 'FABRICATED-SECRET-MARKER'}},
        'userAgent': 'FABRICATED-SECRET-MARKER',
    }
    if impersonated:
        obj['impersonatedUser'] = {'username': impersonated}
    return obj


class AuditPolicyBoundaryTests(unittest.TestCase):
    """Safety boundaries which protect the live API and host."""

    def test_reviewed_exceptions_match_generated_config(self):
        """CI must catch policy drift even without the optional Alloy binary."""
        from tools.monitoring.generate_audit_exceptions import START, END, render, condition
        rules = json.loads((ROOT / 'tools/monitoring/audit_secret_readers.json').read_text())['rules']
        text = (ROOT / 'kubernetes-audit/config-map-audit-alloy.yaml').read_text()
        block = text[text.index(START):text.index(END) + len(END)]
        self.assertEqual(render(rules), block)
        for rule in rules:
            self.assertNotIn('*', rule['actor'])
            if rule['actor'] == 'talos:admin':
                self.assertTrue(rule['source_ips'])
                self.assertEqual('Go-http-client/2.0', rule['user_agent'])
                if 'get' in rule['verbs']:
                    self.assertEqual('talos-backup', rule['namespace'])
                    self.assertEqual(['talos-backup-secrets'], rule['names'])
            if rule['actor'] == 'system:serviceaccount:external-secrets:external-secrets' and 'get' in rule['verbs']:
                self.assertTrue(rule['namespace'])
                self.assertTrue(rule['names'])
        with self.assertRaises(ValueError):
            condition({'actor':'talos:admin','namespace':None,'verbs':['get']})
        with self.assertRaises(ValueError):
            condition({'actor':'system:*','namespace':'monitoring','verbs':['get']})

    def test_admission_policies_are_observation_only(self):
        docs = list(yaml.safe_load_all((ROOT / 'kubernetes-audit/admission-audit-annotations.yaml').read_text()))
        for doc in docs:
            if doc['kind'] == 'ValidatingAdmissionPolicy':
                self.assertEqual('Ignore', doc['spec']['failurePolicy'])
                self.assertEqual([{'expression': 'true'}], doc['spec']['validations'])
            else:
                self.assertEqual(['Audit'], doc['spec']['validationActions'])

    def test_collector_has_no_api_token_or_broad_host_mount(self):
        doc = yaml.safe_load((ROOT / 'kubernetes-audit/daemon-set-audit-alloy.yaml').read_text())
        spec = doc['spec']['template']['spec']
        self.assertFalse(spec['automountServiceAccountToken'])
        mounts = {v['name']: v for v in spec['containers'][0]['volumeMounts']}
        self.assertTrue(mounts['audit']['readOnly'])
        self.assertEqual({'/var/log/audit/kube', '/var/mnt/kubernetes-audit-positions'},
                         {v['hostPath']['path'] for v in spec['volumes'] if 'hostPath' in v})
        self.assertFalse(spec['containers'][0]['securityContext'].get('privileged', False))


@unittest.skipUnless(os.environ.get('ALLOY_BINARY'), 'set ALLOY_BINARY for the real pipeline test')
class AlloyPipelineTests(unittest.TestCase):
    """Real parser, Go templates, metrics and serialized Loki output."""

    def test_detection_sanitization_and_stage_deduplication(self):
        received = []

        class Sink(http.server.BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                received.append(self.rfile.read(int(self.headers['Content-Length'])))
                self.send_response(204)
                self.end_headers()

            def log_message(self, *args):
                pass

        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            logfile = directory / 'audit.log'
            logfile.touch()
            sink = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Sink)
            threading.Thread(target=sink.serve_forever, daemon=True).start()
            port = free_port()
            config = yaml.safe_load((ROOT / 'kubernetes-audit/config-map-audit-alloy.yaml').read_text())['data']['config.alloy']
            config = config.replace('/audit/kube-apiserver.log', str(logfile))
            config = config.replace('http://loki-gateway.loki.svc.cluster.local', f'http://127.0.0.1:{sink.server_port}')
            path = directory / 'config.alloy'
            path.write_text(config)
            with (directory / 'alloy.log').open('w+') as log:
                process = subprocess.Popen([os.environ['ALLOY_BINARY'], 'run', str(path),
                                            '--storage.path=' + str(directory / 'positions'),
                                            '--server.http.listen-addr=127.0.0.1:' + str(port)],
                                           env={'AUDIT_NODE_NAME': 'fixture-node', 'PATH': os.defpath},
                                           stdout=log, stderr=log)
                try:
                    deadline = time.monotonic() + 20
                    while time.monotonic() < deadline:
                        if process.poll() is not None:
                            log.seek(0)
                            self.fail(log.read())
                        try:
                            with urllib.request.urlopen(f'http://127.0.0.1:{port}/-/ready', timeout=1):
                                break
                        except OSError:
                            time.sleep(.1)
                    else:
                        self.fail('Alloy did not become ready')
                    # Allow the file reader to initialize tail-from-end on empty file.
                    time.sleep(1)
                    events = [event('secret'), event('secret-denied', code=403), event('secret-missing', code=404),
                              event('list', verb='list'),
                              event('watch', verb='watch', stage='ResponseStarted'),
                              event('watch-end', verb='watch'),
                              event('received', stage='RequestReceived'),
                              event('exec', resource='pods', verb='create', subresource='exec', stage='ResponseStarted', code=101),
                              event('exec-end', resource='pods', verb='create', subresource='exec'),
                              event('db-exec', resource='pods', namespace='immich', name='immich-postgres-0', verb='create', subresource='exec', stage='ResponseStarted'),
                              event('ordinary-exec', resource='pods', namespace='year', name='year-1', verb='create', subresource='exec', stage='ResponseStarted'),
                              event('rbac', resource='rolebindings', verb='patch', annotations={'homelab-audit-bindings/grant':'ClusterRole:custom-role'}),
                              event('role', resource='roles', verb='update', annotations={'homelab-audit-roles/dangerous':'wildcard-or-escalation'}),
                              event('privileged', resource='pods', verb='create', annotations={'homelab-audit-pods/privileged':'privileged'}),
                              event('psa-denied', resource='pods', verb='create', code=403, annotations={'pod-security.kubernetes.io/audit-violations':'privileged (container "x")'}),
                              event('ordinary-pod', resource='pods', verb='create')]
                    trusted = event('trusted', namespace='kyverno')
                    trusted['user']['username'] = 'system:serviceaccount:kyverno:kyverno-admission-controller'
                    wrong_ns = event('wrong-namespace', namespace='openbao')
                    wrong_ns['user'] = trusted['user']
                    impersonated = event('impersonated', namespace='kyverno', impersonated='human')
                    impersonated['user'] = trusted['user']
                    events += [trusted, wrong_ns, impersonated]
                    dry = event('dry', resource='rolebindings', verb='create', annotations={'homelab-audit-bindings/grant':'ClusterRole:admin'})
                    dry['requestURI'] += '&dryRun=All'
                    events.append(dry)
                    fake_dry = event('get-dry-query')
                    fake_dry['requestURI'] += '&dryRun=All'
                    events.append(fake_dry)
                    # Exercise every reviewed exception through actual Alloy, not a Python mirror.
                    policy = json.loads((ROOT / 'tools/monitoring/audit_secret_readers.json').read_text())['rules']
                    boundary_ids = set()
                    for i, rule in enumerate(policy):
                        verb = rule['verbs'][0]
                        namespace = rule['namespace']
                        if namespace == '*namespaced*':
                            namespace = 'fixture-namespace'
                        trusted_event = event('expected-' + str(i), verb=verb, namespace=namespace,
                                              name=rule.get('names', ['example'])[0],
                                              stage='ResponseStarted' if verb == 'watch' else 'ResponseComplete')
                        trusted_event['user']['username'] = rule['actor']
                        if rule.get('source_ips'):
                            trusted_event['sourceIPs'] = [rule['source_ips'][0]]
                            trusted_event['userAgent'] = rule['user_agent']
                        events.append(trusted_event)
                        # Exceptions never suppress denials, impersonation, or other identities.
                        for suffix in ['denied', 'failed', 'impersonated', 'human']:
                            changed = json.loads(json.dumps(trusted_event))
                            identity = 'boundary-' + str(i) + '-' + suffix
                            changed['auditID'] = identity
                            if suffix == 'denied':
                                changed['responseStatus']['code'] = 403
                                changed['stage'] = 'ResponseComplete'
                            elif suffix == 'failed':
                                changed['responseStatus']['code'] = 404
                                changed['stage'] = 'ResponseComplete'
                            elif suffix == 'impersonated':
                                changed['impersonatedUser'] = {'username':'human'}
                            else:
                                changed['user']['username'] = 'human'
                            events.append(changed)
                            boundary_ids.add(identity)
                    talos = next(e for e in events if e['auditID'].startswith('expected-') and e['user']['username'] == 'talos:admin')
                    for suffix, field, value in [('wrong-ip','sourceIPs',['203.0.113.5']),
                                                 ('wrong-agent','userAgent','kubectl/test'),
                                                 ('wrong-secret','objectRef',dict(talos['objectRef'], name='other')),
                                                 ('wrong-namespace','objectRef',dict(talos['objectRef'], namespace='openbao'))]:
                        changed = json.loads(json.dumps(talos))
                        changed['auditID'] = 'talos-' + suffix
                        changed[field] = value
                        events.append(changed)
                        boundary_ids.add(changed['auditID'])
                    for identity, namespace, verb, stage in [
                        ('metallb-wrong-namespace', 'openbao', 'watch', 'ResponseStarted'),
                        ('metallb-direct-get', 'metallb-system', 'get', 'ResponseComplete'),
                    ]:
                        changed = event(identity, namespace=namespace, verb=verb, stage=stage)
                        changed['user']['username'] = 'system:serviceaccount:metallb-system:metallb-controller'
                        events.append(changed)
                        boundary_ids.add(identity)
                    # A retry of an existing NVIDIA binding must not hide a real grant.
                    for resource, kind, names in [
                        ('rolebindings', 'Role', ['nvidia-dcgm-exporter', 'nvidia-device-plugin',
                         'nvidia-device-plugin-mps-control-daemon', 'nvidia-gpu-feature-discovery',
                         'nvidia-mig-manager', 'nvidia-operator-validator']),
                        ('clusterrolebindings', 'ClusterRole', ['nvidia-device-plugin',
                         'nvidia-device-plugin-mps-control-daemon', 'nvidia-gpu-feature-discovery',
                         'nvidia-mig-manager', 'nvidia-operator-validator']),
                    ]:
                        for name in names:
                            base = event('noop-' + resource + '-' + name, resource=resource,
                                         namespace='gpu-operator', name=name, verb='create', code=409,
                                         annotations={'homelab-audit-bindings/grant': kind + ':' + name})
                            base['user']['username'] = 'system:serviceaccount:gpu-operator:gpu-operator'
                            events.append(base)
                            for suffix in ['success', 'denied', 'human', 'impersonated', 'namespace',
                                           'name', 'role', 'verb', 'dangerous']:
                                changed = json.loads(json.dumps(base))
                                changed['auditID'] += '-' + suffix
                                if suffix in ['success', 'denied']:
                                    changed['responseStatus']['code'] = 201 if suffix == 'success' else 403
                                elif suffix == 'human':
                                    changed['user']['username'] = 'human'
                                elif suffix == 'impersonated':
                                    changed['impersonatedUser'] = {'username': 'human'}
                                elif suffix in ['namespace', 'name']:
                                    changed['objectRef'][suffix] = 'other'
                                elif suffix == 'role':
                                    changed['annotations']['homelab-audit-bindings/grant'] = 'ClusterRole:admin'
                                elif suffix == 'verb':
                                    changed['verb'] = 'patch'
                                else:
                                    changed['annotations']['homelab-audit-roles/dangerous'] = 'escalation'
                                events.append(changed)
                                boundary_ids.add(changed['auditID'])
                    # Direct-read exceptions are constrained to one Secret in one namespace.
                    for actor, namespace, name in [
                        ('cert-manager:cert-manager-cainjector', 'cert-manager', 'cert-manager-webhook-ca'),
                        ('cert-manager:cert-manager-cainjector', 'cert-manager', 'godaddy-webhook-serving'),
                        ('monitoring:platform-health-report', 'mail', 'mail-tls'),
                    ]:
                        for field in ['namespace', 'name']:
                            changed = event('secret-scope-' + actor + '-' + name + '-' + field,
                                            namespace=namespace, name=name)
                            changed['user']['username'] = 'system:serviceaccount:' + actor
                            changed['objectRef'][field] = 'other'
                            events.append(changed)
                            boundary_ids.add(changed['auditID'])
                    unknown = event('eso-unknown-secret', namespace='monitoring', name='unreviewed-secret')
                    unknown['user']['username'] = 'system:serviceaccount:external-secrets:external-secrets'
                    events.append(unknown)
                    boundary_ids.add('eso-unknown-secret')
                    with logfile.open('a') as stream:
                        for item in events:
                            stream.write(json.dumps(item) + '\n')
                    deadline = time.monotonic() + 20
                    metrics = ''
                    while time.monotonic() < deadline:
                        with urllib.request.urlopen(f'http://127.0.0.1:{port}/metrics', timeout=2) as reply:
                            metrics = '\n'.join(line for line in reply.read().decode().splitlines() if line.startswith('homelab_'))
                        if 'outcome="failed"' in metrics and 'outcome="dry-run"' in metrics and received:
                            break
                        time.sleep(.2)
                    self.assertIn('homelab_audit_last_received_timestamp_seconds', metrics)
                    self.assertIn('homelab_audit_last_detection_timestamp_seconds', metrics)
                    for rule in ['secret_read', 'sensitive_exec', 'dangerous_rbac', 'privileged_pod']:
                        self.assertIn(f'detection="{rule}"', metrics)
                    self.assertIn('outcome="dry-run"', metrics)
                    self.assertIn('outcome="failed"', metrics)
                    self.assertIn('outcome="allowed"', metrics)
                    self.assertIn('outcome="denied"', metrics)
                    detection_values = [float(line.rsplit(' ', 1)[1]) for line in metrics.splitlines()
                                        if line.startswith('homelab_audit_last_detection_timestamp_seconds{')]
                    self.assertTrue(detection_values)
                    self.assertTrue(all(abs(value - time.time()) < 30 for value in detection_values))
                    self.assertNotIn('actor=', metrics)
                    self.assertNotIn('target_name=', metrics)
                    # Native Loki protobuf strings are length-delimited. Extract the
                    # JSON log records without a third-party protobuf dependency.
                    # Fedora already supplies libsnappy; no package installation.
                    snappy = ctypes.CDLL(ctypes.util.find_library('snappy'))
                    snappy.snappy_uncompressed_length.argtypes = [ctypes.c_char_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
                    snappy.snappy_uncompress.argtypes = [ctypes.c_char_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.POINTER(ctypes.c_size_t)]
                    records = []
                    for body in received:
                        length = ctypes.c_size_t()
                        self.assertEqual(0, snappy.snappy_uncompressed_length(body, len(body), ctypes.byref(length)))
                        output = ctypes.create_string_buffer(length.value)
                        self.assertEqual(0, snappy.snappy_uncompress(body, len(body), output, ctypes.byref(length)))
                        data = output.raw[:length.value]
                        decoder = json.JSONDecoder()
                        text = data.decode('utf-8', errors='replace')
                        for pos, char in enumerate(text):
                            if char == '{':
                                try:
                                    record, _ = decoder.raw_decode(text[pos:])
                                except ValueError:
                                    continue
                                if 'audit_id' in record:
                                    records.append(record)
                    actual = {r['audit_id'] for r in records}
                    expected = {'secret','secret-denied','secret-missing','list','watch','exec','db-exec','rbac','role','privileged','psa-denied','wrong-namespace','impersonated','dry','get-dry-query'}
                    expected |= boundary_ids
                    self.assertEqual(expected, actual)
                    self.assertEqual(len(expected), len(records))
                    by_id = {r['audit_id']: r for r in records}
                    self.assertEqual('allowed', by_id['secret']['outcome'])
                    self.assertEqual('denied', by_id['secret-denied']['outcome'])
                    self.assertEqual('failed', by_id['secret-missing']['outcome'])
                    self.assertEqual('dry-run', by_id['dry']['outcome'])
                    self.assertEqual('allowed', by_id['get-dry-query']['outcome'])
                    self.assertNotIn('FABRICATED-SECRET-MARKER', json.dumps(records))
                    self.assertNotIn('requestObject', json.dumps(records))
                    self.assertNotIn('requestURI', json.dumps(records))
                finally:
                    process.terminate()
                    process.wait(timeout=10)
                    sink.shutdown()
                    sink.server_close()
