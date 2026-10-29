#!/usr/bin/env python3
"""Check core Linux Restricted contexts in rendered namespaces that enforce it.

This is a CI regression guard for common settings, not a replacement for the
API server's versioned Pod Security Admission checks or runtime verification.
"""
import argparse
import json
from pathlib import Path
import yaml


def violations(spec):
    errors = []
    pod = spec.get('securityContext') or {}
    for flag in ('hostNetwork', 'hostPID', 'hostIPC'):
        if spec.get(flag):
            errors.append(flag)
    if any('hostPath' in v for v in (spec.get('volumes') or [])):
        errors.append('hostPath')
    for c in (spec.get('containers') or []) + (spec.get('initContainers') or []):
        security = c.get('securityContext') or {}
        def fail(reason):
            errors.append(c['name'] + ': ' + reason)
        if security.get('privileged'):
            fail('privileged')
        if security.get('allowPrivilegeEscalation') is not False:
            fail('allowPrivilegeEscalation must be false')
        caps = security.get('capabilities') or {}
        if 'ALL' not in caps.get('drop', []):
            fail('must drop ALL capabilities')
        if set(caps.get('add', [])) - {'NET_BIND_SERVICE'}:
            fail('unsupported added capabilities')
        if security.get('runAsNonRoot', pod.get('runAsNonRoot')) is not True:
            fail('runAsNonRoot must be true')
        if security.get('runAsUser', pod.get('runAsUser')) == 0:
            fail('runAsUser cannot be zero')
        profile = security.get('seccompProfile', pod.get('seccompProfile')) or {}
        if profile.get('type') not in {'RuntimeDefault', 'Localhost'}:
            fail('seccompProfile required')
    return errors


def templates(doc):
    kind = doc.get('kind')
    if kind == 'Pod':
        yield doc['spec']
    elif kind == 'CronJob':
        yield doc['spec']['jobTemplate']['spec']['template']['spec']
    elif kind in {'Deployment', 'DaemonSet', 'StatefulSet', 'Job', 'ReplicaSet', 'ReplicationController'}:
        yield doc['spec']['template']['spec']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rendered', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    applications = {}
    enforced = set()
    for path in (root / 'argocd').glob('*.yaml'):
        app = yaml.safe_load(path.read_text())
        if not isinstance(app, dict) or app.get('kind') != 'Application':
            continue
        applications[app['metadata']['name']] = app
        if app['spec'].get('syncPolicy', {}).get('managedNamespaceMetadata', {}).get('labels', {}).get('pod-security.kubernetes.io/enforce') == 'restricted':
            enforced.add(app['spec']['destination']['namespace'])
    documents = []
    for name in json.loads((args.rendered / 'inventory.json').read_text()):
        ns = applications[name]['spec']['destination']['namespace']
        for doc in yaml.safe_load_all((args.rendered / (name + '.yaml')).read_text()):
            if not isinstance(doc, dict):
                continue
            documents.append((ns, doc))
            if doc.get('kind') == 'Namespace' and doc.get('metadata', {}).get('labels', {}).get('pod-security.kubernetes.io/enforce') == 'restricted':
                enforced.add(doc['metadata']['name'])
    errors = []; count = 0
    for namespace, doc in documents:
        namespace = doc.get('metadata', {}).get('namespace', namespace)
        if namespace not in enforced:
            continue
        for spec in templates(doc):
            count += 1
            errors.extend(f'{namespace}/{doc["kind"]}/{doc["metadata"]["name"]}: {e}' for e in violations(spec))
    for error in errors:
        print(error)
    print(f'Restricted context check: {count} templates; {len(errors)} errors')
    return bool(errors)


if __name__ == '__main__':
    raise SystemExit(main())
