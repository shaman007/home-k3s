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
            'require-drop-all-capabilities': 'capabilities',
            'restrict-seccomp-strict': 'seccomp'}


# Reviewed application roles only; permission-init exceptions retain their smaller
# allowlist. No SYS_ADMIN, privileged containers or arbitrary main roles.
APPLICATION_CAPABILITIES = {
    ('backup-rsync', 'backup-rsync', 'sshd'): ({'CHOWN', 'DAC_OVERRIDE', 'FOWNER', 'SETGID', 'SETUID', 'SYS_CHROOT', 'NET_BIND_SERVICE'}, 0, False),
    ('mail', 'postfix', 'postfix-mail'): ({'CHOWN', 'DAC_OVERRIDE', 'FOWNER', 'FSETID', 'KILL', 'SETGID', 'SETUID', 'NET_BIND_SERVICE'}, 0, False),
    ('mail', 'dovecot', 'dovecot-mail'): ({'CHOWN', 'DAC_OVERRIDE', 'FOWNER', 'FSETID', 'KILL', 'SETGID', 'SETUID', 'NET_BIND_SERVICE', 'SYS_CHROOT'}, 0, False),
    ('plex', 'plex', 'plex'): ({'CHOWN', 'DAC_OVERRIDE', 'FOWNER', 'FSETID', 'KILL', 'SETGID', 'SETUID'}, 0, False),
    ('nextcloud', 'collabora-collabora-online', 'collabora-online'): ({'CHOWN', 'FOWNER', 'SYS_CHROOT'}, 1001, True),
    ('ripe-atlas', 'ripe-atlas', 'ripe-atlas'): ({'CHOWN', 'DAC_OVERRIDE', 'FOWNER', 'FSETID', 'KILL', 'SETUID', 'SETGID', 'SETPCAP', 'NET_RAW'}, 0, True),
}


SPEAKER_GUARDS = {
    'privileged': False, 'allowPrivilegeEscalation': False,
    'readOnlyRootFilesystem': True, 'runAsNonRoot': False,
    'runAsUser': 0, 'runAsGroup': 0,
    'seccompProfile': {'type': 'RuntimeDefault'},
    'capabilities': {'drop': ['ALL'], 'add': ['NET_RAW']}}


def is_speaker(entry):
    return (entry['kind'], entry['namespace'], entry['name']) == ('DaemonSet', 'metallb-system', 'metallb-speaker')


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
    if policy == 'restrict-seccomp-strict':
        return 'c.?securityContext.?seccompProfile.?type.orValue(p.spec.?securityContext.?seccompProfile.?type.orValue("")) in ["RuntimeDefault", "Localhost"]'
    raise ValueError(policy)


def image_repository(image):
    """Remove a tag/digest while preserving an explicit registry and port."""
    assert isinstance(image, str) and image and not any(c.isspace() for c in image)
    image = image.split('@', 1)[0]
    slash = image.rfind('/')
    assert slash > 0, 'Reviewed images require an explicit registry/repository'
    colon = image.rfind(':')
    return image[:colon] if colon > slash else image


def image_expression(image):
    repository = image_repository(image)
    pattern = '^' + re.escape(repository) + r'(?::[A-Za-z0-9_][A-Za-z0-9_.-]{0,127})?(?:@sha256:[a-fA-F0-9]{64})?$'
    return f'c.image.matches({literal(pattern)})'


def approved(policy, allowed):
    clauses = []
    for name, rule in sorted(allowed.items()):
        assert rule['image'] and '*' not in rule['image']
        fields = [f'c.name == {literal(name)}', image_expression(rule['image'])]
        if policy == 'require-run-as-nonroot':
            fields.append('c.?securityContext.?runAsUser.orValue(p.spec.?securityContext.?runAsUser.orValue(0)) == 0')
        if policy == 'require-drop-all-capabilities' and not rule.get('requirePrivileged'):
            assert set(rule) in ({'image', 'capabilities'}, {'image', 'capabilities', 'runAsUser', 'allowPrivilegeEscalation'})
            caps = rule['capabilities']
            assert isinstance(caps, list)
            assert caps and len(caps) == len(set(caps))
            if 'runAsUser' not in rule:
                assert set(caps) <= {'CHOWN', 'DAC_OVERRIDE', 'DAC_READ_SEARCH', 'FOWNER'}
            actual = 'c.?securityContext.?capabilities.?add.orValue([])'
            fields.extend([
                'c.?securityContext.?privileged.orValue(false) == false',
                (f'has(c.securityContext) && has(c.securityContext.allowPrivilegeEscalation) && c.securityContext.allowPrivilegeEscalation == {literal(rule["allowPrivilegeEscalation"])}' if 'runAsUser' in rule else 'c.?securityContext.?allowPrivilegeEscalation.orValue(true) == false'),
                f'c.?securityContext.?runAsUser.orValue(p.spec.?securityContext.?runAsUser.orValue({0 if "runAsUser" in rule else -1})) == {rule.get("runAsUser", 0)}',
                'c.?securityContext.?capabilities.?drop.orValue([]) == ["ALL"]',
                f'{actual}.size() == {len(caps)}',
                f'{actual}.all(cap, cap in {literal(caps)})',
                f'{literal(caps)}.all(cap, cap in {actual})'])
        if policy in ('require-drop-all-capabilities', 'restrict-seccomp-strict') and rule.get('requirePrivileged'):
            assert set(rule) == {'image', 'requirePrivileged', 'capabilityDeclaration', 'seccompDeclaration'}
            assert rule['requirePrivileged'] is True
            fields.extend([
                f'c.?securityContext.?capabilities.orValue({{}}) == {literal(rule["capabilityDeclaration"])}',
                f'c.?securityContext.?seccompProfile.orValue({{}}) == {literal(rule["seccompDeclaration"])}'])
        if rule.get('requireHardened'):
            assert policy == 'require-run-as-nonroot'
            assert set(rule) == {'image', 'requireHardened'}
            fields.extend([
                'c.?securityContext.?runAsUser.orValue(-1) == 0',
                'c.?securityContext.?runAsGroup.orValue(-1) == 0',
                'c.?securityContext.?privileged.orValue(false) == false',
                'c.?securityContext.?allowPrivilegeEscalation.orValue(true) == false',
                'c.?securityContext.?capabilities.?drop.orValue([]) == ["ALL"]',
                'c.?securityContext.?capabilities.?add.orValue([]).size() == 0',
                'c.?securityContext.?seccompProfile.?type.orValue("") == "RuntimeDefault"'])
        if rule.get('requirePrivileged'):
            fields.append('c.?securityContext.?privileged.orValue(false) == true')
        clauses.append('(' + ' && '.join(fields) + ')')
    return '(' + ' || '.join(clauses) + ')' if clauses else 'false'


def guard_terms(variable, expected):
    """Pin reviewed guards; capability set order is immaterial."""
    terms = []
    for field, value in sorted(expected.items()):
        assert field in {'privileged', 'allowPrivilegeEscalation', 'readOnlyRootFilesystem',
                         'runAsNonRoot', 'runAsUser', 'runAsGroup', 'seccompProfile', 'capabilities'}
        actual = f'{variable}.?securityContext.?{field}'
        if field == 'capabilities':
            assert set(value) <= {'add', 'drop'}
            for operation in ['add', 'drop']:
                caps = value.get(operation, [])
                current = f'{actual}.?{operation}.orValue([])'
                terms += [f'{current}.size() == {len(caps)}',
                          f'{current}.all(cap, cap in {literal(caps)})',
                          f'{literal(caps)}.all(cap, cap in {current})']
        else:
            default = 'false' if field == 'privileged' else 'null'
            if variable == 'c' and field in {'runAsNonRoot', 'runAsUser', 'runAsGroup', 'seccompProfile'}:
                default = f'p.spec.?securityContext.?{field}.orValue(null)'
            terms.append(f'{actual}.orValue({default}) == {literal(value)}')
    return terms


def expression(entry, policy):
    config = entry['policies'][policy]
    if is_speaker(entry):
        assert set(entry['policies']) == {'require-run-as-nonroot', 'require-drop-all-capabilities'}
        assert entry['serviceAccount'] == 'metallb-speaker'
        assert entry['requiredGuards'] == {'containers': {'speaker': SPEAKER_GUARDS}}
        for reviewed in entry['policies'].values():
            assert set(reviewed.get('containers', {})) == {'speaker'}
            assert not reviewed.get('initContainers') and not reviewed.get('ephemeralContainers')
            assert image_repository(reviewed['containers']['speaker']['image']) == 'quay.io/metallb/speaker'
    if policy in ('require-drop-all-capabilities', 'restrict-seccomp-strict'):
        for section, rules in config.items():
            for name, rule in rules.items():
                if not rule.get('requirePrivileged'):
                    assert policy != 'restrict-seccomp-strict'
                    continue
                assert 'disallow-privileged-containers' in entry['policies']
                reviewed = entry['policies']['disallow-privileged-containers'].get(section, {})
                assert name in reviewed and reviewed[name]['image'] == rule['image']
                snapshot = next(c for c in entry['snapshot'][section] if c['name'] == name)
                sc = snapshot['securityContext']
                assert sc['privileged'] is True and snapshot['image'] == rule['image']
                assert rule['capabilityDeclaration'] == sc.get('capabilities', {})
                assert rule['seccompDeclaration'] == sc.get('seccompProfile', {})
    if policy == 'require-drop-all-capabilities':
        assert not config.get('ephemeralContainers')
        assert config.get('initContainers') or config.get('containers')
        for name, rule in config.get('initContainers', {}).items():
            if rule.get('requirePrivileged'):
                continue
            root_roles = entry['policies']['require-run-as-nonroot'].get('initContainers', {})
            assert name in root_roles and root_roles[name]['image'] == rule['image']
            assert set(rule) == {'image', 'capabilities'}
        for name, rule in config.get('containers', {}).items():
            if rule.get('requirePrivileged'):
                continue
            if is_speaker(entry):
                assert name == 'speaker'
                assert set(rule) == {'image', 'capabilities', 'runAsUser', 'allowPrivilegeEscalation'}
                assert rule['capabilities'] == ['NET_RAW'] and rule['runAsUser'] == 0
                assert rule['allowPrivilegeEscalation'] is False
                continue
            assert entry['kind'] == 'Deployment'
            key = (entry['namespace'], entry['name'], name)
            assert key in APPLICATION_CAPABILITIES
            caps, uid, escalation = APPLICATION_CAPABILITIES[key]
            assert set(rule) == {'image', 'capabilities', 'runAsUser', 'allowPrivilegeEscalation'}
            assert set(rule['capabilities']) == caps
            assert rule['runAsUser'] == uid and rule['allowPrivilegeEscalation'] is escalation
            review_policy = 'disallow-privilege-escalation' if escalation else 'require-run-as-nonroot'
            reviewed = entry['policies'][review_policy]['containers']
            assert name in reviewed and reviewed[name]['image'] == rule['image']
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
    for section, roles in entry.get('requiredGuards', {}).items():
        assert section in ('containers', 'initContainers')
        for name, guards in roles.items():
            companion = entry.get('reviewedCompanions', {}).get(section, {}).get(name)
            assert any(name in config.get(section, {}) for config in entry['policies'].values()) or companion
            assert guards
            conditions = guard_terms('c', guards)
            if companion:
                # This only constrains an already compliant companion; it never
                # grants an exception role or bypasses any policy's compliant().
                assert set(companion) == {'image'}
                snapshot = next(c for c in entry['snapshot'][section] if c['name'] == name)
                assert snapshot['image'] == companion['image']
                conditions.append(image_expression(companion['image']))
            terms.append(f'p.spec.?{section}.orValue([]).exists(c, c.name == {literal(name)} && ' +
                         ' && '.join(conditions) + ')')
    terms.extend(guard_terms('p.spec', entry.get('requiredPodGuards', {})))
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
                for section, key in [('initContainers', 'approved-init-capabilities'), ('containers', 'approved-main-capabilities')]:
                    rules = entry['policies'][policy].get(section, {})
                    if rules:
                        cap_properties[key] = literal({name: rule.get('capabilities', 'existing reviewed privileged mode') for name, rule in rules.items()})
            name = exception_name(entry, policy)
            assert name not in names
            names.add(name)
            yield {'apiVersion': 'policies.kyverno.io/v1', 'kind': 'PolicyException',
                   'metadata': {'name': name, 'namespace': catalog['exceptionNamespace']},
                   'spec': {'policyRefs': [{'name': policy, 'kind': 'ValidatingPolicy'}],
                            'expiresAt': catalog['expiresAt'], 'reportResult': 'skip',
                            'properties': {'reason': entry['reason'], 'evidence': entry['evidence'],
                                           'reviewed-on': entry.get('reviewedOn', catalog['reviewedOn']),
                                           'review-trigger': 'repository/guard/startup/chart or ownership change',
                                           'image-scope': 'exact registry/repository; tags and sha256 digests may change', **cap_properties},
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
