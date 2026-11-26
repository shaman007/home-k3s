#!/usr/bin/env python3
"""Render reviewed identity/scope/action exceptions into the real Alloy pipeline."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
START = '      // BEGIN generated expected Secret readers\n'
END = '      // END generated expected Secret readers\n'


def equal(field, value):
    """Quote fixed values as Go-template strings, not regular expressions."""
    return f'(eq .{field} {json.dumps(value)})'


def one_of(field, values):
    """Match only an explicit reviewed set."""
    if not values:
        raise ValueError('Empty exception constraint')
    expressions = [equal(field, value) for value in values]
    return expressions[0] if len(expressions) == 1 else '(or ' + ' '.join(expressions) + ')'


def condition(rule):
    """Fail closed on malformed or unexpectedly broad informer exceptions."""
    if not rule['actor'] or '*' in rule['actor']:
        raise ValueError('Exact actor required')
    if not set(rule['verbs']) <= {'get', 'list', 'watch'}:
        raise ValueError('Only read exceptions are supported')
    namespace = rule['namespace']
    if namespace is None and 'get' in rule['verbs']:
        raise ValueError('Cluster-wide GET exception forbidden')
    scope = '(not .target_namespace)' if namespace is None else (
        '.target_namespace' if namespace == '*namespaced*' else equal('target_namespace', namespace))
    clauses = [equal('actor', rule['actor']), scope, one_of('verb', rule['verbs'])]
    for key, field in [('names', 'target_name'), ('source_ips', 'source_ip')]:
        if key in rule:
            clauses.append(one_of(field, rule[key]))
    if 'user_agent' in rule:
        clauses.append(equal('user_agent', rule['user_agent']))
    return '(and ' + ' '.join(clauses) + ')'


def render(rules):
    """Successful direct reads only: denied/failed and impersonated attempts stay visible."""
    lines = '\n'.join('          '+condition(rule) for rule in rules)
    return (START + '      // Source: tools/monitoring/audit_secret_readers.json; do not edit this block.\n'
            '      stage.template {\n        source = "expected_secret_reader"\n'
            '        template = `{{ if and (not .impersonated) (ge (int .code) 200) (lt (int .code) 300) (or\n'
            + lines + '\n        ) }}yes{{ end }}`\n      }\n' + END)


def main():
    """Update only the generated block; preserve unrelated collection behavior."""
    path = ROOT / 'kubernetes-audit/config-map-audit-alloy.yaml'
    config = path.read_text()
    begin = config.index(START)
    end = config.index(END, begin) + len(END)
    rules = json.loads((ROOT / 'tools/monitoring/audit_secret_readers.json').read_text())['rules']
    path.write_text(config[:begin] + render(rules) + config[end:])
    print(f'Rendered {len(rules)} reviewed Secret-read exceptions')


if __name__ == '__main__':
    main()
