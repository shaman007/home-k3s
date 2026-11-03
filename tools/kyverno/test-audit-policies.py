#!/usr/bin/env python3
"""Exercise actual rendered CEL policies/exceptions with the pinned Kyverno CLI."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import yaml

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_POLICIES = {'require-run-as-nonroot', 'disallow-privilege-escalation',
                     'disallow-privileged-containers', 'require-drop-all-capabilities',
                     'restrict-seccomp-strict'}


def pod_spec(document):
    if document['kind'] == 'Pod':
        return document['spec']
    spec = document['spec']
    if document['kind'] == 'CronJob':
        spec = spec['jobTemplate']['spec']
    return spec['template']['spec']


def labels(document):
    if document['kind'] == 'Pod':
        return document['metadata']['labels']
    spec = document['spec']
    if document['kind'] == 'CronJob':
        spec = spec['jobTemplate']['spec']
    return spec['template']['metadata']['labels']


def snapshot(entry):
    ps = copy.deepcopy(entry['snapshot'])
    ps['serviceAccountName'] = entry['serviceAccount']
    ps['nodeSelector'] = {'audit.home-k3s/fixture-do-not-schedule': 'true'}
    meta = {'name': entry['name'], 'namespace': entry['namespace'], 'labels': copy.deepcopy(entry['labels'])}
    template = {'metadata': {'labels': copy.deepcopy(entry['labels'])}, 'spec': ps}
    kind = entry['kind']
    if kind == 'Pod':
        meta['ownerReferences'] = [entry['owner']]
        spec = ps
    elif kind == 'CronJob':
        spec = {'schedule': '0 * * * *', 'jobTemplate': {'spec': {'template': template}}}
    else:
        spec = {'selector': {'matchLabels': entry['labels']}, 'template': template}
    return {'apiVersion': 'v1' if kind == 'Pod' else 'batch/v1' if kind == 'CronJob' else 'apps/v1',
            'kind': kind, 'metadata': meta, 'spec': spec}


def derived_pod(entry):
    hash_value = hashlib.sha256((entry['namespace'] + '/' + entry['name']).encode()).hexdigest()[:8]
    kind, name = entry['kind'], entry['name']
    meta = {'namespace': entry['namespace'], 'labels': copy.deepcopy(entry['labels'])}
    if kind == 'Pod':
        return snapshot(entry)
    if kind == 'Deployment':
        owner_kind, owner_name = 'ReplicaSet', name + '-' + hash_value
        meta['labels']['pod-template-hash'] = hash_value
        meta['name'] = owner_name + '-approved'
    elif kind == 'StatefulSet':
        owner_kind, owner_name = kind, name
        meta['name'] = name + '-0'
    elif kind == 'DaemonSet':
        owner_kind, owner_name = kind, name
        meta['name'] = name + '-approved'
    else:
        owner_kind, owner_name = 'Job', name + '-29895000'
        meta['name'] = owner_name + '-approved'
    meta['ownerReferences'] = [{'apiVersion': 'batch/v1' if owner_kind == 'Job' else 'apps/v1',
                                'kind': owner_kind, 'name': owner_name,
                                'uid': '00000000-0000-0000-0000-000000000001', 'controller': True}]
    ps = copy.deepcopy(entry['snapshot'])
    ps['serviceAccountName'] = entry['serviceAccount']
    ps['nodeSelector'] = {'audit.home-k3s/fixture-do-not-schedule': 'true'}
    return {'apiVersion': 'v1', 'kind': 'Pod', 'metadata': meta, 'spec': ps}


def noncompliant_container(policy, name):
    sc = {'runAsUser': 1000, 'runAsNonRoot': True, 'allowPrivilegeEscalation': False,
          'capabilities': {'drop': ['ALL']}, 'seccompProfile': {'type': 'RuntimeDefault'}}
    if policy == 'require-run-as-nonroot':
        sc.update(runAsUser=0, runAsNonRoot=False)
    elif policy == 'disallow-privilege-escalation':
        sc['allowPrivilegeEscalation'] = True
    elif policy == 'require-drop-all-capabilities':
        sc['capabilities']['add'] = ['SYS_ADMIN']
    else:
        sc.update(privileged=True, allowPrivilegeEscalation=True)
    return {'name': name, 'image': 'registry.example.invalid/unapproved:1', 'securityContext': sc}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rendered', type=Path, required=True)
    parser.add_argument('--kyverno', default='kyverno')
    args = parser.parse_args()
    version = subprocess.check_output([args.kyverno, 'version'], text=True)
    if '1.19.2' not in version:
        raise SystemExit('Tests require the pinned Kyverno CLI 1.19.2')
    applications = {d['metadata']['name']: d for f in (ROOT / 'argocd').glob('*.yaml')
                    if isinstance(d := yaml.safe_load(f.read_text()), dict) and d.get('kind') == 'Application'}
    rendered = []
    for name in json.loads((args.rendered / 'inventory.json').read_text()):
        for document in yaml.safe_load_all((args.rendered / (name + '.yaml')).read_text()):
            if not isinstance(document, dict):
                continue
            if document.get('kind') in ('Deployment', 'StatefulSet', 'DaemonSet', 'CronJob', 'Pod'):
                document.setdefault('metadata', {}).setdefault('namespace', applications[name]['spec']['destination']['namespace'])
            rendered.append(document)
    policies = [d for d in rendered if d.get('kind') == 'ValidatingPolicy']
    assert {d['metadata']['name'] for d in policies} == EXPECTED_POLICIES
    assert all(d['spec']['validationActions'] == ['Audit'] and d['spec']['failurePolicy'] == 'Ignore'
               for d in policies)
    exceptions = list(yaml.safe_load_all((ROOT / 'kyverno/policy-exceptions-verified.yaml').read_text()))
    catalog = json.loads((ROOT / 'kyverno/exception-catalog.json').read_text())
    actual = {(d['kind'], d.get('metadata', {}).get('namespace', ''), d.get('metadata', {}).get('name')): d
              for d in rendered if d.get('kind') in ('Deployment', 'StatefulSet', 'DaemonSet', 'CronJob')}
    count = 0
    with tempfile.TemporaryDirectory(prefix='kyverno-audit-tests-') as temporary:
        work = Path(temporary)
        (work / 'policies.yaml').write_text(yaml.safe_dump_all(policies, sort_keys=False))
        (work / 'exceptions.yaml').write_text(yaml.safe_dump_all(exceptions, sort_keys=False))
        resources, results = [], []

        def case(document, expected, separate=False):
            nonlocal count
            count += len(expected)
            refs = [{'policy': policy, 'kind': document['kind'], 'resources': [document['metadata']['name']],
                     'result': result} for policy, result in expected.items()]
            if separate:
                folder = work / ('case-' + str(count))
                folder.mkdir()
                (folder / 'resources.yaml').write_text(yaml.safe_dump(document, sort_keys=False))
                test = {'apiVersion': 'cli.kyverno.io/v1alpha1', 'kind': 'Test',
                        'metadata': {'name': folder.name}, 'policies': ['../policies.yaml'],
                        'resources': ['resources.yaml'], 'exceptions': ['../exceptions.yaml'], 'results': refs}
                (folder / 'kyverno-test.yaml').write_text(yaml.safe_dump(test, sort_keys=False))
            else:
                resources.append(document)
                results.extend(refs)

        for index, entry in enumerate(catalog['entries']):
            expected_skip = {p: 'skip' for p in entry['policies']}
            document = snapshot(entry)
            current = actual.get((entry['kind'], entry['namespace'], entry['name']))
            if current:
                # Use actual chart/source output when available; operator-created
                # workloads retain reviewed sanitized snapshots in the catalog.
                ps = pod_spec(current)
                clean = {k: copy.deepcopy(ps[k]) for k in ['securityContext', 'serviceAccountName'] if k in ps}
                for section in ['containers', 'initContainers', 'ephemeralContainers']:
                    if section in ps:
                        clean[section] = [{k: copy.deepcopy(c[k]) for k in ['name', 'image', 'securityContext'] if k in c}
                                          for c in ps[section]]
                if document['kind'] == 'CronJob':
                    document['spec']['jobTemplate']['spec']['template']['spec'] = clean
                else:
                    document['spec']['template']['spec'] = clean
                labels(document).clear()
                labels(document).update(labels(current))
            case(document, expected_skip)
            if entry['kind'] != 'Pod':
                positive = derived_pod(entry)
                case(positive, expected_skip)
            else:
                positive = document
            def variant_name(document, token):
                suffix = hashlib.sha256((entry['namespace'] + '/' + entry['name'] + token).encode()).hexdigest()[:10]
                if entry['kind'] == 'StatefulSet':
                    # Valid unique ordinals preserve controller identity while
                    # avoiding hundreds of separate CLI policy compilations.
                    document['metadata']['name'] = entry['name'] + '-' + str(int(suffix, 16))
                elif entry['kind'] != 'Pod':
                    document['metadata']['name'] = document['metadata']['ownerReferences'][0]['name'] + '-' + suffix
            for mutation in ['namespace', 'owner', 'labels', 'service-account']:
                changed = copy.deepcopy(positive)
                variant_name(changed, mutation)
                if mutation == 'namespace': changed['metadata']['namespace'] = 'unapproved-audit-target'
                if mutation == 'owner': changed['metadata']['ownerReferences'][0]['name'] = 'unapproved-controller'
                if mutation == 'labels': changed['metadata']['labels'][next(iter(entry['labels']))] = 'unapproved'
                if mutation == 'service-account': changed['spec']['serviceAccountName'] = 'unapproved'
                case(changed, {p: 'fail' for p in entry['policies']},
                     separate=entry['kind'] == 'Pod')
            for policy, approval in entry['policies'].items():
                for mutation in ['image', 'sidecar', 'ephemeral', 'repaired']:
                    changed = copy.deepcopy(positive)
                    variant_name(changed, policy + mutation)
                    if mutation == 'image':
                        section = next(s for s in ['containers', 'initContainers'] if approval[s])
                        name = next(iter(approval[section]))
                        next(c for c in changed['spec'][section] if c['name'] == name)['image'] = 'registry.example.invalid/changed:1'
                    elif mutation in ('sidecar', 'ephemeral'):
                        section = 'containers' if mutation == 'sidecar' else 'ephemeralContainers'
                        changed['spec'].setdefault(section, []).append(noncompliant_container(policy, 'unapproved-audit-container'))
                    else:
                        for c in changed['spec'].get('containers', []) + changed['spec'].get('initContainers', []):
                            sc = c.setdefault('securityContext', {})
                            if policy == 'require-run-as-nonroot': sc.update(runAsUser=1000, runAsNonRoot=True)
                            if policy == 'disallow-privilege-escalation': sc.update(allowPrivilegeEscalation=False, privileged=False)
                            if policy == 'disallow-privileged-containers': sc['privileged'] = False
                            if policy == 'require-drop-all-capabilities': sc['capabilities'] = {'drop': ['ALL']}
                    case(changed, {policy: 'pass' if mutation == 'repaired' else 'fail'},
                         separate=entry['kind'] == 'Pod')
                if policy == 'require-drop-all-capabilities':
                    role = next(iter(approval['initContainers']))
                    for mutation in ['extra-capability', 'missing-drop', 'escalation', 'privileged', 'changed-uid', 'moved-to-main', 'duplicate-capabilities', 'missing-escalation-guard', 'reordered']:
                        changed = copy.deepcopy(positive)
                        variant_name(changed, policy + mutation)
                        helper = next(c for c in changed['spec']['initContainers'] if c['name'] == role)
                        sc = helper['securityContext']
                        if mutation == 'extra-capability': sc['capabilities']['add'].append('SYS_ADMIN')
                        if mutation == 'missing-drop': sc['capabilities'].pop('drop')
                        if mutation == 'escalation': sc['allowPrivilegeEscalation'] = True
                        if mutation == 'privileged': sc['privileged'] = True
                        if mutation == 'changed-uid': sc['runAsUser'] = 1000
                        if mutation == 'moved-to-main':
                            changed['spec']['initContainers'].remove(helper)
                            changed['spec']['containers'].append(helper)
                        if mutation == 'duplicate-capabilities':
                            caps = sc['capabilities']['add']
                            sc['capabilities']['add'] = [caps[0]] * max(2, len(caps))
                        if mutation == 'missing-escalation-guard': sc.pop('allowPrivilegeEscalation')
                        if mutation == 'reordered': sc['capabilities']['add'].reverse()
                        case(changed, {policy: 'skip' if mutation == 'reordered' else 'fail'},
                             separate=entry['kind'] == 'Pod')

        def audit_case(name, change, policy, result):
            pod = {'apiVersion': 'v1', 'kind': 'Pod', 'metadata': {'name': name, 'namespace': 'audit-validation'},
                   'spec': {'securityContext': {'runAsNonRoot': True, 'runAsUser': 1000,
                                              'seccompProfile': {'type': 'RuntimeDefault'}},
                            'containers': [{'name': 'app', 'image': 'registry.example.invalid/app:1',
                                            'securityContext': {'allowPrivilegeEscalation': False,
                                                                'capabilities': {'drop': ['ALL']}}}]}}
            change(pod)
            case(pod, {policy: result})
        cap = 'require-drop-all-capabilities'
        seccomp = 'restrict-seccomp-strict'
        audit_case('cap-compliant', lambda p: None, cap, 'pass')
        audit_case('cap-missing', lambda p: p['spec']['containers'][0]['securityContext'].pop('capabilities'), cap, 'fail')
        audit_case('cap-drop-missing', lambda p: p['spec']['containers'][0]['securityContext']['capabilities'].pop('drop'), cap, 'fail')
        audit_case('cap-extra', lambda p: p['spec']['containers'][0]['securityContext']['capabilities'].update(add=['SYS_ADMIN']), cap, 'fail')
        audit_case('cap-bind-service', lambda p: p['spec']['containers'][0]['securityContext']['capabilities'].update(add=['NET_BIND_SERVICE']), cap, 'pass')
        for section in ['initContainers', 'ephemeralContainers']:
            audit_case('cap-' + section.lower(), lambda p, s=section: p['spec'].update({s: [{'name': 'other', 'image': 'registry.example.invalid/app:1', 'securityContext': {}}]}), cap, 'fail')
        audit_case('seccomp-inherit', lambda p: None, seccomp, 'pass')
        audit_case('seccomp-missing', lambda p: p['spec']['securityContext'].pop('seccompProfile'), seccomp, 'fail')
        audit_case('seccomp-unconfined', lambda p: p['spec']['containers'][0]['securityContext'].update(seccompProfile={'type': 'Unconfined'}), seccomp, 'fail')
        audit_case('seccomp-localhost', lambda p: p['spec']['securityContext'].update(seccompProfile={'type': 'Localhost', 'localhostProfile': 'profiles/approved.json'}), seccomp, 'pass')
        for section in ['initContainers', 'ephemeralContainers']:
            audit_case('seccomp-' + section.lower(), lambda p, s=section: p['spec'].update({s: [{'name': 'other', 'image': 'registry.example.invalid/app:1', 'securityContext': {'seccompProfile': {'type': 'Unconfined'}}}]}), seccomp, 'fail')
        (work / 'resources.yaml').write_text(yaml.safe_dump_all(resources, sort_keys=False))
        (work / 'kyverno-test.yaml').write_text(yaml.safe_dump(
            {'apiVersion': 'cli.kyverno.io/v1alpha1', 'kind': 'Test', 'metadata': {'name': 'audit-exceptions'},
             'policies': ['policies.yaml'], 'resources': ['resources.yaml'],
             'exceptions': ['exceptions.yaml'], 'results': results}, sort_keys=False))
        print(f'Testing {count} exact-match/negative/audit expectations with Kyverno 1.19.2', flush=True)
        subprocess.run([args.kyverno, 'test', str(work), '--fail-only', '--remove-color'], check=True)


if __name__ == '__main__':
    main()
