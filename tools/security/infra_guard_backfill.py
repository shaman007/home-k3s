"""Guarded GitOps backfill: exact contracts, admission previews, sequential rollouts."""
import copy
import json
import os
from pathlib import Path
import ssl
import time
import urllib.request


def reviewed(doc, entry):
    assert doc['kind'] == entry['kind'] and doc['metadata']['name'] == entry['name']
    assert doc['metadata']['namespace'] == entry['namespace']
    pod = doc['spec']['template']['spec']
    assert pod.get('serviceAccountName', 'default') == entry['serviceAccount']
    for key, value in entry['labels'].items():
        assert doc['spec']['template']['metadata']['labels'].get(key) == value
    for section in ['containers', 'initContainers']:
        actual, expected = pod.get(section, []), entry['fixture']['spec']['template']['spec'].get(section, [])
        assert len(actual) == len(expected)
        for a, e in zip(actual, expected):
            assert all(a.get(k, []) == e.get(k, []) for k in ['name', 'image', 'command', 'args', 'volumeMounts'])
    assert pod.get('volumes', []) == entry['fixture']['spec']['template']['spec'].get('volumes', [])
    for target in entry['targets']:
        assert pod[target['section']][target['index']]['name'] == target['name']
    if entry['kind'] == 'DaemonSet':
        assert doc['spec']['updateStrategy'] == entry['fixture']['spec']['updateStrategy']
        assert doc['spec']['updateStrategy']['rollingUpdate']['maxUnavailable'] == 1


def expected_spec(doc, entry):
    spec = copy.deepcopy(doc['spec'])
    if entry.get('podGuards'):
        pod = spec['template']['spec']
        pod['securityContext'] = {**(pod.get('securityContext') or {}), **entry['podGuards']}
    for target in entry['targets']:
        container = spec['template']['spec'][target['section']][target['index']]
        container['securityContext'] = {**(container.get('securityContext') or {}), **target['guards']}
    return spec


def ready(doc):
    s = doc.get('status', {})
    if s.get('observedGeneration', 0) < doc['metadata'].get('generation', 1): return False
    if doc['kind'] == 'Deployment':
        n = doc['spec'].get('replicas', 1)
        return n > 0 and all(s.get(k) == n for k in ['replicas', 'updatedReplicas', 'readyReplicas', 'availableReplicas'])
    n = s.get('desiredNumberScheduled', 0)
    return n > 0 and all(s.get(k) == n for k in ['updatedNumberScheduled', 'numberReady', 'numberAvailable'])


def patch(doc):
    result = [{'op':'test', 'path':'/metadata/resourceVersion', 'value':doc['metadata']['resourceVersion']}]
    if doc['metadata'].get('annotations') is None:
        result.append({'op':'add','path':'/metadata/annotations','value':{}})
    result.append({'op':'add','path':'/metadata/annotations/hardening.home-k3s~1infra-guards','value':'v1'})
    return result


def main(config_dir=Path('/config'), account=Path('/var/run/secrets/kubernetes.io/serviceaccount')):
    entries = json.loads((config_dir/'catalog.json').read_text())['entries']
    context = ssl.create_default_context(cafile=str(account/'ca.crt'))
    token = (account/'token').read_text().strip()
    base = 'https://' + os.environ['KUBERNETES_SERVICE_HOST'] + ':' + os.environ['KUBERNETES_SERVICE_PORT']
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=context))

    def request(e, changes=None, dry=False):
        resource = 'deployments' if e['kind'] == 'Deployment' else 'daemonsets'
        url = base + '/apis/apps/v1/namespaces/' + e['namespace'] + '/' + resource + '/' + e['name']
        if dry: url += '?dryRun=All'
        headers = {'Authorization':'Bearer ' + token}
        if changes is not None: headers['Content-Type'] = 'application/json-patch+json'
        req = urllib.request.Request(url, method='GET' if changes is None else 'PATCH', headers=headers,
                                     data=None if changes is None else json.dumps(changes).encode())
        with opener.open(req, timeout=15) as response: return json.load(response)

    def storage_check():
        if not any(e['namespace'] == 'longhorn-system' for e in entries): return
        from storage_guard import storage_healthy
        documents=[]
        for resource in ['volumes','nodes']:
            req=urllib.request.Request(base+'/apis/longhorn.io/v1beta2/namespaces/longhorn-system/'+resource, headers={'Authorization':'Bearer '+token})
            with opener.open(req,timeout=15) as response:documents.append(json.load(response))
        storage_healthy(*documents)

    # Every contract and dry-run mutation must pass before the hook writes anything.
    for attempt in range(30):
        try:
            storage_check()
            for e in entries:
                original = request(e); reviewed(original, e)
                assert ready(original), e['name'] + ': not fully ready'
                assert request(e, patch(original), True)['spec'] == expected_spec(original, e), e['name'] + ': unexpected admission result'
            break
        except AssertionError:
            if attempt == 29: raise
            time.sleep(3)
    for e in entries:
        storage_check()
        original = request(e); reviewed(original, e)
        assert ready(original), e['name'] + ': readiness changed'
        expected = expected_spec(original, e)
        if expected != original['spec']:
            assert request(e, patch(original), True)['spec'] == expected
            assert request(e, patch(original))['spec'] == expected
        deadline = time.monotonic() + 300
        stable_since = None
        while True:
            current = request(e)
            assert current['spec'] == expected, e['name'] + ': unexpected spec change'
            if ready(current):
                if stable_since is None: stable_since = time.monotonic()
                if time.monotonic() - stable_since >= 15: break
            else: stable_since = None
            if time.monotonic() >= deadline: raise RuntimeError(e['name'] + ': rollout failed; later targets untouched')
            time.sleep(3)
        storage_check()
        print(e['namespace'] + '/' + e['name'] + ': guards and rollout verified', flush=True)


if __name__ == '__main__':
    main()
