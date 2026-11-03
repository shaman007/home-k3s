#!/usr/bin/env python3
"""Generate narrowly matched CEL exceptions from a reviewed, explicit catalog."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import yaml

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / 'kyverno/exception-catalog.json'
OUTPUT = ROOT / 'kyverno/policy-exceptions-verified.yaml'
POLICIES = {'require-run-as-nonroot': 'root',
            'disallow-privilege-escalation': 'escalation',
            'disallow-privileged-containers': 'privileged',
            'require-drop-all-capabilities': 'capabilities'}


def literal(value):
    return json.dumps(value, sort_keys=True)


def owner(kind, name, uid=None):
    terms = [f'o.kind == {literal(kind)}', f'o.name == {name}',
             'o.?controller.orValue(false) == true']
    if uid:
        terms.append(f'o.uid == {literal(uid)}')
    return 'object.metadata.?ownerReferences.orValue([]).exists(o, ' + ' && '.join(terms) + ')'


def identity(entry):
    kind, name = entry['kind'], entry['name']
    direct = f'(object.kind == {literal(kind)} && object.metadata.name == {literal(name)})'
    if kind == 'Pod':
        ref = entry['owner']
        return direct + ' && ' + owner(ref['kind'], literal(ref['name']), ref['uid'])
    if kind == 'Deployment':
        label = 'object.metadata.?labels.orValue({})'
        has_hash = f'"pod-template-hash" in {label} && {label}["pod-template-hash"].matches("^[a-z0-9]{{1,10}}$")'
        rs_name = f'{literal(name + "-")} + {label}["pod-template-hash"]'
        rs = f'(object.kind == "ReplicaSet" && {has_hash} && object.metadata.name == {rs_name} && {owner("Deployment", literal(name))})'
        pod = f'(object.kind == "Pod" && {has_hash} && {owner("ReplicaSet", rs_name)} && object.metadata.name.startsWith({rs_name} + "-"))'
        return f'({direct} || {rs} || {pod})'
    if kind in ('StatefulSet', 'DaemonSet'):
        pattern = '^' + re.escape(name) + ('-[0-9]+$' if kind == 'StatefulSet' else '-[a-z0-9]+$')
        pod = f'(object.kind == "Pod" && object.metadata.name.matches({literal(pattern)}) && {owner(kind, literal(name))})'
        return f'({direct} || {pod})'
    if kind == 'CronJob':
        pattern = '^' + re.escape(name) + '-[0-9]{8,12}$'
        job = f'(object.kind == "Job" && object.metadata.name.matches({literal(pattern)}) && {owner("CronJob", literal(name))})'
        pod = ('(object.kind == "Pod" && object.metadata.?ownerReferences.orValue([]).exists(o, '
               f'o.kind == "Job" && o.?controller.orValue(false) == true && o.name.matches({literal(pattern)}) '
               '&& object.metadata.name.startsWith(o.name + "-")))')
        return f'({direct} || {job} || {pod})'
    raise ValueError(f'Unsupported workload kind: {kind}')


def compliant(policy):
    if policy == 'require-run-as-nonroot':
        return 'c.?securityContext.?runAsNonRoot.orValue(p.spec.?securityContext.?runAsNonRoot.orValue(false)) == true'
    if policy == 'disallow-privilege-escalation':
        return 'c.?securityContext.?allowPrivilegeEscalation.orValue(true) == false'
    if policy == 'disallow-privileged-containers':
        return 'c.?securityContext.?privileged.orValue(false) == false'
    if policy == 'require-drop-all-capabilities':
        return ('"ALL" in c.?securityContext.?capabilities.?drop.orValue([]) && '
                'c.?securityContext.?capabilities.?add.orValue([]).all(cap, cap == "NET_BIND_SERVICE")')
    raise ValueError(policy)


def approved(policy, allowed):
    clauses = []
    for name, rule in sorted(allowed.items()):
        assert rule['image'] and '*' not in rule['image']
        fields = [f'c.name == {literal(name)}', f'c.image == {literal(rule["image"])}']
        if policy == 'require-run-as-nonroot':
            fields.append('c.?securityContext.?runAsUser.orValue(p.spec.?securityContext.?runAsUser.orValue(0)) == 0')
        if policy == 'require-drop-all-capabilities':
            assert set(rule) == {'image', 'capabilities'}
            caps = rule['capabilities']
            assert isinstance(caps, list)
            assert caps and len(caps) == len(set(caps))
            assert set(caps) <= {'CHOWN', 'DAC_OVERRIDE', 'DAC_READ_SEARCH', 'FOWNER'}
            actual = 'c.?securityContext.?capabilities.?add.orValue([])'
            fields.extend([
                'c.?securityContext.?privileged.orValue(false) == false',
                'c.?securityContext.?allowPrivilegeEscalation.orValue(true) == false',
                'c.?securityContext.?runAsUser.orValue(p.spec.?securityContext.?runAsUser.orValue(-1)) == 0',
                'c.?securityContext.?capabilities.?drop.orValue([]) == ["ALL"]',
                f'{actual}.size() == {len(caps)}',
                f'{actual}.all(cap, cap in {literal(caps)})',
                f'{literal(caps)}.all(cap, cap in {actual})'])
        if rule.get('requirePrivileged'):
            fields.append('c.?securityContext.?privileged.orValue(false) == true')
        clauses.append('(' + ' && '.join(fields) + ')')
    return '(' + ' || '.join(clauses) + ')' if clauses else 'false'


def expression(entry, policy):
    config = entry['policies'][policy]
    if policy == 'require-drop-all-capabilities':
        # Only the previously reviewed root permission-init roles may receive
        # capability exceptions; never approve a main or ephemeral container.
        assert config.get('initContainers') and not config.get('containers') and not config.get('ephemeralContainers')
        root_roles = entry['policies']['require-run-as-nonroot'].get('initContainers', {})
        for name, rule in config['initContainers'].items():
            assert name in root_roles and root_roles[name]['image'] == rule['image']
    ok = compliant(policy)
    terms = []
    actual = []
    for section in ['containers', 'initContainers', 'ephemeralContainers']:
        allow = approved(policy, config.get(section, {}))
        collection = f'p.spec.?{section}.orValue([])'
        terms.append(f'{collection}.all(c, ({ok}) || {allow})')
        if allow != 'false':
            actual.append(f'{collection}.exists(c, !({ok}) && {allow})')
    assert actual
    terms.append('(' + ' || '.join(actual) + ')')
    account = entry['serviceAccount']
    terms.insert(0, f'p.spec.?serviceAccountName.orValue("default") == {literal(account)}')
    for key, value in sorted(entry['labels'].items()):
        terms.insert(0, f'has(p.metadata.labels) && {literal(key)} in p.metadata.labels && p.metadata.labels[{literal(key)}] == {literal(value)}')
    normalized = '(object.kind == "Pod" ? object : object.kind == "CronJob" ? object.spec.jobTemplate.spec.template : object.spec.template)'
    return (f'object.metadata.namespace == {literal(entry["namespace"])} &&\n'
            f'{identity(entry)} &&\n'
            f'[{normalized}].exists(p,\n  ' + ' &&\n  '.join(terms) + '\n)')


def exception_name(entry, policy):
    name = f'verified-{POLICIES[policy]}-{entry["namespace"]}-{entry["name"]}'
    if len(name) > 63:
        name = name[:54].rstrip('-') + '-' + hashlib.sha256(name.encode()).hexdigest()[:8]
    return name


def generate(catalog):
    assert catalog['exceptionNamespace'] == 'kyverno'
    names = set()
    for entry in catalog['entries']:
        assert entry['namespace'] not in ('kyverno', 'kube-system', 'crowdsec', 'lenka')
        assert entry['labels'] and entry['reason'] and entry['evidence']
        for policy in sorted(entry['policies']):
            assert policy in POLICIES
            cap_properties = {}
            if policy == 'require-drop-all-capabilities':
                cap_properties['approved-init-capabilities'] = literal({name: rule['capabilities'] for name, rule in entry['policies'][policy]['initContainers'].items()})
            name = exception_name(entry, policy)
            assert name not in names
            names.add(name)
            yield {'apiVersion': 'policies.kyverno.io/v1', 'kind': 'PolicyException',
                   'metadata': {'name': name, 'namespace': catalog['exceptionNamespace']},
                   'spec': {'policyRefs': [{'name': policy, 'kind': 'ValidatingPolicy'}],
                            'expiresAt': catalog['expiresAt'], 'reportResult': 'skip',
                            'properties': {'reason': entry['reason'], 'evidence': entry['evidence'],
                                           'reviewed-on': catalog['reviewedOn'],
                                           'review-trigger': 'image/chart/startup or ownership change', **cap_properties},
                            'matchConditions': [{'name': 'exact-workload-and-approved-deviations',
                                                 'expression': expression(entry, policy)}]}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    text = '# Generated by tools/kyverno/generate-exceptions.py; edit the reviewed catalog.\n'
    text += yaml.safe_dump_all(list(generate(json.loads(CATALOG.read_text()))), sort_keys=False, width=120)
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text() != text:
            raise SystemExit('Generated Kyverno exceptions are stale')
        print('Generated exception catalog is current')
    else:
        OUTPUT.write_text(text)


if __name__ == '__main__':
    main()
