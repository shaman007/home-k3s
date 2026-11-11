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
    if not (isinstance(image, str) and image and not any(c.isspace() for c in image)):
        raise AssertionError
    image = image.split('@', 1)[0]
    slash = image.rfind('/')
    if not (slash > 0):
        raise AssertionError('Reviewed images require an explicit registry/repository')
    colon = image.rfind(':')
    return image[:colon] if colon > slash else image


def image_expression(image):
    repository = image_repository(image)
    pattern = '^' + re.escape(repository) + r'(?::[A-Za-z0-9_][A-Za-z0-9_.-]{0,127})?(?:@sha256:[a-fA-F0-9]{64})?$'
    return f'c.image.matches({literal(pattern)})'


def approved(policy, allowed):
    clauses = []
    for name, rule in sorted(allowed.items()):
        if not (rule['image'] and '*' not in rule['image']):
            raise AssertionError
        fields = [f'c.name == {literal(name)}', image_expression(rule['image'])]
        if policy == 'require-run-as-nonroot':
            fields.append('c.?securityContext.?runAsUser.orValue(p.spec.?securityContext.?runAsUser.orValue(0)) == 0')
        if policy == 'require-drop-all-capabilities' and not rule.get('requirePrivileged'):
            if not (set(rule) in ({'image', 'capabilities'}, {'image', 'capabilities', 'runAsUser', 'allowPrivilegeEscalation'})):
                raise AssertionError
            caps = rule['capabilities']
            if not (isinstance(caps, list)):
                raise AssertionError
            if not (caps and len(caps) == len(set(caps))):
                raise AssertionError
            if 'runAsUser' not in rule:
                if not (set(caps) <= {'CHOWN', 'DAC_OVERRIDE', 'DAC_READ_SEARCH', 'FOWNER'}):
                    raise AssertionError
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
            if not (set(rule) == {'image', 'requirePrivileged', 'capabilityDeclaration', 'seccompDeclaration'}):
                raise AssertionError
            if not (rule['requirePrivileged'] is True):
                raise AssertionError
            fields.extend([
                f'c.?securityContext.?capabilities.orValue({{}}) == {literal(rule["capabilityDeclaration"])}',
                f'c.?securityContext.?seccompProfile.orValue({{}}) == {literal(rule["seccompDeclaration"])}'])
        if rule.get('requireHardened'):
            if not (policy == 'require-run-as-nonroot'):
                raise AssertionError
            if not (set(rule) == {'image', 'requireHardened'}):
                raise AssertionError
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
        if not (field in {'privileged', 'allowPrivilegeEscalation', 'readOnlyRootFilesystem',
                         'runAsNonRoot', 'runAsUser', 'runAsGroup', 'seccompProfile', 'capabilities'}):
            raise AssertionError
        actual = f'{variable}.?securityContext.?{field}'
        if field == 'capabilities':
            if not (set(value) <= {'add', 'drop'}):
                raise AssertionError
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
        if not (set(entry['policies']) == {'require-run-as-nonroot', 'require-drop-all-capabilities'}):
            raise AssertionError
        if not (entry['serviceAccount'] == 'metallb-speaker'):
            raise AssertionError
        if not (entry['requiredGuards'] == {'containers': {'speaker': SPEAKER_GUARDS}}):
            raise AssertionError
        for reviewed in entry['policies'].values():
            if not (set(reviewed.get('containers', {})) == {'speaker'}):
                raise AssertionError
            if not (not reviewed.get('initContainers') and not reviewed.get('ephemeralContainers')):
                raise AssertionError
            if not (image_repository(reviewed['containers']['speaker']['image']) == 'quay.io/metallb/speaker'):
                raise AssertionError
    if policy in ('require-drop-all-capabilities', 'restrict-seccomp-strict'):
        for section, rules in config.items():
            for name, rule in rules.items():
                if not rule.get('requirePrivileged'):
                    if not (policy != 'restrict-seccomp-strict'):
                        raise AssertionError
                    continue
                if not ('disallow-privileged-containers' in entry['policies']):
                    raise AssertionError
                reviewed = entry['policies']['disallow-privileged-containers'].get(section, {})
                if not (name in reviewed and reviewed[name]['image'] == rule['image']):
                    raise AssertionError
                snapshot = next(c for c in entry['snapshot'][section] if c['name'] == name)
                sc = snapshot['securityContext']
                if not (sc['privileged'] is True and snapshot['image'] == rule['image']):
                    raise AssertionError
                if not (rule['capabilityDeclaration'] == sc.get('capabilities', {})):
                    raise AssertionError
                if not (rule['seccompDeclaration'] == sc.get('seccompProfile', {})):
                    raise AssertionError
    if policy == 'require-drop-all-capabilities':
        if not (not config.get('ephemeralContainers')):
            raise AssertionError
        if not (config.get('initContainers') or config.get('containers')):
            raise AssertionError
        for name, rule in config.get('initContainers', {}).items():
            if rule.get('requirePrivileged'):
                continue
            root_roles = entry['policies']['require-run-as-nonroot'].get('initContainers', {})
            if not (name in root_roles and root_roles[name]['image'] == rule['image']):
                raise AssertionError
            if not (set(rule) == {'image', 'capabilities'}):
                raise AssertionError
        for name, rule in config.get('containers', {}).items():
            if rule.get('requirePrivileged'):
                continue
            if is_speaker(entry):
                if not (name == 'speaker'):
                    raise AssertionError
                if not (set(rule) == {'image', 'capabilities', 'runAsUser', 'allowPrivilegeEscalation'}):
                    raise AssertionError
                if not (rule['capabilities'] == ['NET_RAW'] and rule['runAsUser'] == 0):
                    raise AssertionError
                if not (rule['allowPrivilegeEscalation'] is False):
                    raise AssertionError
                continue
            if not (entry['kind'] == 'Deployment'):
                raise AssertionError
            key = (entry['namespace'], entry['name'], name)
            if not (key in APPLICATION_CAPABILITIES):
                raise AssertionError
            caps, uid, escalation = APPLICATION_CAPABILITIES[key]
            if not (set(rule) == {'image', 'capabilities', 'runAsUser', 'allowPrivilegeEscalation'}):
                raise AssertionError
            if not (set(rule['capabilities']) == caps):
                raise AssertionError
            if not (rule['runAsUser'] == uid and rule['allowPrivilegeEscalation'] is escalation):
                raise AssertionError
            review_policy = 'disallow-privilege-escalation' if escalation else 'require-run-as-nonroot'
            reviewed = entry['policies'][review_policy]['containers']
            if not (name in reviewed and reviewed[name]['image'] == rule['image']):
                raise AssertionError
    ok = compliant(policy)
    terms = []
    actual = []
    for section in ['containers', 'initContainers', 'ephemeralContainers']:
        allow = approved(policy, config.get(section, {}))
        collection = f'p.spec.?{section}.orValue([])'
        terms.append(f'{collection}.all(c, ({ok}) || {allow})')
        if allow != 'false':
            actual.append(f'{collection}.exists(c, !({ok}) && {allow})')
    if not (actual):
        raise AssertionError
    terms.append('(' + ' || '.join(actual) + ')')
    for section, roles in entry.get('requiredGuards', {}).items():
        if not (section in ('containers', 'initContainers')):
            raise AssertionError
        for name, guards in roles.items():
            companion = entry.get('reviewedCompanions', {}).get(section, {}).get(name)
            if not (any(name in config.get(section, {}) for config in entry['policies'].values()) or companion):
                raise AssertionError
            if not (guards):
                raise AssertionError
            conditions = guard_terms('c', guards)
            if companion:
                # This only constrains an already compliant companion; it never
                # grants an exception role or bypasses any policy's compliant().
                if not (set(companion) == {'image'}):
                    raise AssertionError
                snapshot = next(c for c in entry['snapshot'][section] if c['name'] == name)
                if not (snapshot['image'] == companion['image']):
                    raise AssertionError
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
    if not (catalog['exceptionNamespace'] == 'kyverno'):
        raise AssertionError
    names = set()
    for entry in catalog['entries']:
        if not (entry['namespace'] not in ('kyverno', 'kube-system', 'crowdsec', 'lenka')):
            raise AssertionError
        if not (entry['labels'] and entry['reason'] and entry['evidence']):
            raise AssertionError
        for policy in sorted(entry['policies']):
            if not (policy in POLICIES):
                raise AssertionError
            cap_properties = {}
            if policy == 'require-drop-all-capabilities':
                for section, key in [('initContainers', 'approved-init-capabilities'), ('containers', 'approved-main-capabilities')]:
                    rules = entry['policies'][policy].get(section, {})
                    if rules:
                        cap_properties[key] = literal({name: rule.get('capabilities', 'existing reviewed privileged mode') for name, rule in rules.items()})
            name = exception_name(entry, policy)
            if not (name not in names):
                raise AssertionError
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
