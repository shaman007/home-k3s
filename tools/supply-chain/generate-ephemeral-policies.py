#!/usr/bin/env python3
"""Generate admission-only subresource policies without background list/watch RBAC."""
import argparse
import copy
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / 'kyverno/policy-verify-ephemeral.yaml'


def generate():
    result = []
    for name in ['own-ghcr', 'own-harbor', 'upstream']:
        for base in yaml.safe_load_all((ROOT / f'kyverno/policy-verify-{name}.yaml').read_text()):
            policy = copy.deepcopy(base)
            policy['metadata']['name'] += '-ephemeral'
            spec = policy['spec']
            spec['evaluation'] = {'admission': {'enabled': True}, 'background': {'enabled': False}}
            spec['autogen'] = {'podControllers': {'controllers': []}}
            for rule in spec['matchConstraints']['resourceRules']:
                rule['resources'] = ['pods/ephemeralcontainers']
                rule['operations'] = ['UPDATE']
            result.append(policy)
    return yaml.safe_dump_all(result, sort_keys=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    payload = generate()
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text() != payload:
            raise SystemExit('Ephemeral-container signature policies need regeneration')
    else:
        OUTPUT.write_text(payload)
