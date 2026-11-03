#!/usr/bin/env python3
"""Check storage/mount contracts that Kubernetes schema validation cannot catch."""
import argparse
import json
from pathlib import Path
import yaml


def violations(document):
    if document.get('kind') != 'Deployment':
        return []
    spec = document.get('spec', {}).get('template', {}).get('spec', {})
    containers = {c['name']: c for c in spec.get('containers', [])}
    errors = []
    lapi = containers.get('crowdsec-lapi', {})
    if 'crowdsec-rootless' in lapi.get('image', ''):
        runtime = next((m for m in lapi.get('volumeMounts', [])
                        if m['mountPath'] == '/var/lib/crowdsec/data'), None)
        migration = next((c for c in spec.get('initContainers', [])
                          if c['name'] == 'prepare-rootless-database'), {})
        preparation = next((m for m in migration.get('volumeMounts', [])
                            if m['mountPath'] == '/var/lib/crowdsec/data'), None)
        keys = ('name', 'mountPath', 'subPath', 'subPathExpr')
        if not runtime or not preparation or any(runtime.get(k) != preparation.get(k) for k in keys):
            errors.append('database init and LAPI must mount the exact same volume/subPath')
    agent = containers.get('crowdsec-agent', {})
    if 'crowdsec-rootless' in agent.get('image', ''):
        mounts = agent.get('volumeMounts', [])
        if any(m['mountPath'].startswith('/etc/crowdsec/') for m in mounts):
            parent = next((m for m in mounts if m['mountPath'] == '/etc/crowdsec'), {})
            volume = next((v for v in spec.get('volumes', [])
                           if v['name'] == parent.get('name')), {})
            if (not parent or parent.get('readOnly') or 'emptyDir' not in volume
                    or not spec.get('securityContext', {}).get('fsGroup')):
                errors.append('agent ConfigMap subPaths require an fsGroup-writable emptyDir parent')
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rendered', type=Path, required=True)
    args = parser.parse_args()
    errors = []
    for name in json.loads((args.rendered / 'inventory.json').read_text()):
        for doc in yaml.safe_load_all((args.rendered / (name + '.yaml')).read_text()):
            if isinstance(doc, dict):
                errors.extend(f'{name}/{doc.get("kind")}/{doc.get("metadata", {}).get("name")}: {e}'
                              for e in violations(doc))
    for error in errors:
        print(error)
    print(f'CrowdSec rootless mount contracts: {len(errors)} errors')
    return bool(errors)


if __name__ == '__main__':
    raise SystemExit(main())
