#!/usr/bin/env python3
"""Preflight native mutations, then roll reviewed workloads one at a time."""
import copy
import json
import os
from pathlib import Path
import ssl
import time
import urllib.error
import urllib.request

NAMESPACE = 'longhorn-system'
MARKER = 'hardening.home-k3s/component-security'


def security(entry):
    return {'runAsNonRoot': entry['uid'] != 0, 'runAsUser': entry['uid'], 'runAsGroup': entry['gid'],
            'allowPrivilegeEscalation': False, 'privileged': False,
            'capabilities': {'drop': ['ALL']}, 'seccompProfile': {'type': 'RuntimeDefault'}}


def reviewed(doc, entry):
    meta, pod = doc['metadata'], doc['spec']['template']['spec']
    assert doc['kind'] == entry['kind'] and meta['namespace'] == NAMESPACE and meta['name'] == entry['name']
    assert doc['spec']['template']['metadata']['labels']['app'] == entry['name']
    assert pod['serviceAccountName'] == entry['serviceAccount']
    assert len(pod['containers']) == entry['count'] and not pod.get('initContainers')
    c = pod['containers'][entry['index']]
    assert c['name'] == entry['container'] and c['image'] == entry['image']
    assert c.get('command', []) == entry['command'] and c.get('args', []) == entry['args']
    if entry['kind'] == 'DaemonSet':
        for index in range(entry['count']):
            if index == entry['index']: continue
            actual = pod['containers'][index]
            expected = entry['fixture']['spec']['template']['spec']['containers'][index]
            assert actual['name'] == expected['name'] and actual['image'] == expected['image']
            assert actual['securityContext']['privileged'] is True
        assert doc['spec']['updateStrategy'] == entry['fixture']['spec']['updateStrategy']


def expected_spec(doc, entry):
    spec = copy.deepcopy(doc['spec'])
    c = spec['template']['spec']['containers'][entry['index']]
    c['securityContext'] = {**(c.get('securityContext') or {}), **security(entry)}
    return spec


def ready(doc):
    status = doc.get('status', {})
    if status.get('observedGeneration', 0) < doc['metadata'].get('generation', 1): return False
    if doc['kind'] == 'Deployment':
        count = doc['spec'].get('replicas', 1)
        return (count > 0 and status.get('updatedReplicas', 0) == count and status.get('replicas', 0) == count
                and status.get('readyReplicas', 0) == count and status.get('availableReplicas', 0) == count)
    count = status.get('desiredNumberScheduled', 0)
    return count > 0 and status.get('updatedNumberScheduled', 0) == count and status.get('numberReady', 0) == count and status.get('numberAvailable', 0) == count


def annotation_patch(doc):
    patch = [{'op': 'test', 'path': '/metadata/resourceVersion', 'value': doc['metadata']['resourceVersion']}]
    if doc['metadata'].get('annotations') is None: patch.append({'op': 'add', 'path': '/metadata/annotations', 'value': {}})
    patch.append({'op': 'add', 'path': '/metadata/annotations/' + MARKER.replace('/', '~1'), 'value': 'v1'})
    return patch


def main(config_dir=Path('/config'), account=Path('/var/run/secrets/kubernetes.io/serviceaccount')):
    entries = json.loads((config_dir/'catalog.json').read_text())['entries']
    context = ssl.create_default_context(cafile=str(account/'ca.crt'))
    token = (account/'token').read_text().strip()
    base = 'https://' + os.environ['KUBERNETES_SERVICE_HOST'] + ':' + os.environ['KUBERNETES_SERVICE_PORT']
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=context))

    def request(entry, patch=None, dry=False):
        resource = 'deployments' if entry['kind'] == 'Deployment' else 'daemonsets'
        url = base+'/apis/apps/v1/namespaces/'+NAMESPACE+'/'+resource+'/'+entry['name']
        if dry: url += '?dryRun=All'
        headers = {'Authorization': 'Bearer '+token}
        if patch is not None: headers['Content-Type'] = 'application/json-patch+json'
        req = urllib.request.Request(url, headers=headers, method='PATCH' if patch is not None else 'GET',
                                     data=json.dumps(patch).encode() if patch is not None else None)
        try:
            with opener.open(req, timeout=15) as response: return json.load(response)
        except urllib.error.HTTPError as error:
            raise RuntimeError(f'{entry["name"]}: Kubernetes HTTP {error.code}') from None

    # Complete all safety checks before the first persistent write.
    for attempt in range(30):
        try:
            for entry in entries:
                original = request(entry); reviewed(original, entry)
                assert ready(original), f'{entry["name"]}: workload is not fully healthy'
                preview = request(entry, annotation_patch(original), dry=True)
                assert preview['spec'] == expected_spec(original, entry), f'{entry["name"]}: unexpected or absent admission mutation'
            break
        except AssertionError:
            if attempt == 29: raise
            time.sleep(3)
    for entry in entries:
        # Refetch to tolerate harmless controller resourceVersion updates during earlier rollouts.
        original = request(entry); reviewed(original, entry)
        assert ready(original), f'{entry["name"]}: became unhealthy before mutation'
        expected = expected_spec(original, entry)
        if original['spec'] != expected:
            patch = annotation_patch(original)
            assert request(entry, patch, dry=True)['spec'] == expected
            assert request(entry, patch)['spec'] == expected
        deadline = time.monotonic()+300
        while True:
            current = request(entry)
            assert current['spec'] == expected, f'{entry["name"]}: spec changed during rollout'
            if ready(current): break
            if time.monotonic() >= deadline: raise RuntimeError(f'{entry["name"]}: rollout timed out; later targets were not changed')
            time.sleep(3)
        print(f'{entry["name"]}: security context and completed rollout verified', flush=True)
    for path in ['/', '/v1']:
        req = urllib.request.Request('http://longhorn-frontend'+path)
        with opener.open(req, timeout=15) as response:
            assert response.status == 200, 'UI HTTP check failed'
    print('Component backfill complete; UI static and API proxy HTTP checks passed', flush=True)


if __name__ == '__main__': main()
