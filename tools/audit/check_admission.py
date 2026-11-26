"""Evaluate shipped audit CEL with the installed Kyverno CLI, entirely offline.

Usage: python3 tools/audit/check_admission.py /path/to/kyverno
The audit expression becomes a test validation; production remains audit-only.
"""
import copy
import pathlib
import subprocess  # nosec B404
import sys
import tempfile

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]


def main(binary):
    policies = {
        p['metadata']['name']: p for p in yaml.safe_load_all(
            (ROOT / 'kubernetes-audit/admission-audit-annotations.yaml').read_text()
        ) if p['kind'] == 'ValidatingAdmissionPolicy'
    }
    pod = {'apiVersion': 'v1', 'kind': 'Pod', 'metadata': {'name': 'fixture', 'namespace': 'default'},
           'spec': {'containers': [{'name': 'app', 'image': 'fixture'}]}}
    role = {'apiVersion': 'rbac.authorization.k8s.io/v1', 'kind': 'ClusterRole',
            'metadata': {'name': 'fixture'}, 'rules': [{'apiGroups': [''], 'resources': ['pods'], 'verbs': ['get']}]}
    cases = [('normal-pod', 'homelab-audit-pods', pod, '')]
    for field in ('containers', 'initContainers', 'ephemeralContainers'):
        obj = copy.deepcopy(pod)
        obj['spec'][field] = [{'name': 'privileged', 'image': 'fixture', 'securityContext': {'privileged': True}}]
        cases.append((field, 'homelab-audit-pods', obj, 'privileged'))
    false = copy.deepcopy(pod)
    false['spec']['containers'][0]['securityContext'] = {'privileged': False}
    cases.append(('explicit-unprivileged', 'homelab-audit-pods', false, ''))
    cases.append(('read-only-role', 'homelab-audit-roles', role, ''))
    for field, value in [('verbs', '*'), ('verbs', 'bind'), ('verbs', 'escalate'), ('verbs', 'impersonate'), ('resources', '*'), ('apiGroups', '*')]:
        obj = copy.deepcopy(role)
        obj['rules'][0][field] = [value]
        cases.append((field + '-' + value, 'homelab-audit-roles', obj, 'wildcard-or-escalation'))
    empty = copy.deepcopy(role)
    empty.pop('rules')
    cases.append(('empty-role', 'homelab-audit-roles', empty, ''))
    for kind in ('RoleBinding', 'ClusterRoleBinding'):
        obj = {'apiVersion': 'rbac.authorization.k8s.io/v1', 'kind': kind,
               'metadata': {'name': 'fixture', 'namespace': 'default'},
               'roleRef': {'apiGroup': 'rbac.authorization.k8s.io', 'kind': 'ClusterRole', 'name': 'custom-role'},
               'subjects': [{'kind': 'ServiceAccount', 'name': 'fixture', 'namespace': 'default'}]}
        cases.append((kind, 'homelab-audit-bindings', obj, 'ClusterRole:custom-role'))
    with tempfile.TemporaryDirectory() as directory:
        directory = pathlib.Path(directory)
        for name, key, resource, expected in cases:
            policy = copy.deepcopy(policies[key])
            expression = policy['spec'].pop('auditAnnotations')[0]['valueExpression']
            policy['spec']['validations'] = [{'expression': f'({expression}) == {expected!r}'}]
            path = directory / 'policy.yaml'
            path.write_text(yaml.safe_dump(policy))
            resource_path = directory / 'resource.yaml'
            resource_path.write_text(yaml.safe_dump(resource))
            result = subprocess.run([binary, 'apply', str(path), '--resource', str(resource_path)],
                                    capture_output=True, text=True, check=False)
            if result.returncode or 'pass: 1, fail: 0, warn: 0, error: 0, skip: 0' not in result.stdout:
                raise RuntimeError(f'{name}: {result.stdout}\n{result.stderr}')
        print(f'PASS: {len(cases)} audit-annotation CEL cases')


if __name__ == '__main__':
    main(sys.argv[1])
