#!/usr/bin/env python3
"""Check rendered pod memory budgets and CPU quotas, including admission defaults."""
import argparse
from pathlib import Path
import yaml


def pod_specs(document):
    kind = document.get('kind')
    if kind == 'Pod':
        yield document.get('spec', {})
    elif kind == 'CronJob':
        yield document.get('spec', {}).get('jobTemplate', {}).get('spec', {}).get('template', {}).get('spec', {})
    elif kind in {'Deployment', 'StatefulSet', 'DaemonSet', 'ReplicaSet', 'ReplicationController', 'Job'}:
        yield document.get('spec', {}).get('template', {}).get('spec', {})
    elif kind == 'ClusterPolicy':
        # GPU Operator creates these pods at runtime, outside Helm output.
        yield {'containers': [
            {'name': name, 'resources': component['resources']}
            for name, component in document.get('spec', {}).items()
            if isinstance(component, dict) and 'resources' in component
        ]}
    elif kind == 'ConfigMap' and 'default-setting.yaml' in (document.get('data') or {}):
        import json
        settings = yaml.safe_load(document['data']['default-setting.yaml']) or {}
        csi = settings.get('system-managed-csi-components-resource-limits')
        if csi:
            yield {'containers': [{'name': name, 'resources': resources}
                                  for name, resources in json.loads(csi).items()]}



def check(documents):
    defaults = {}
    errors = []
    for namespace, doc in documents:
        if doc.get('kind') != 'LimitRange':
            continue
        namespace = doc.get('metadata', {}).get('namespace', namespace)
        for limit in doc.get('spec', {}).get('limits', []):
            if limit.get('type') == 'Container':
                defaults.setdefault(namespace, []).append(limit)
                if limit.get('default', {}).get('cpu') is not None or limit.get('max', {}).get('cpu') is not None:
                    errors.append(f'{namespace}/LimitRange/{doc["metadata"]["name"]}: CPU ceiling configured')
    containers = 0
    for namespace, doc in documents:
        namespace = doc.get('metadata', {}).get('namespace', namespace)
        identity = f'{namespace}/{doc.get("kind")}/{doc.get("metadata", {}).get("name")}'
        for spec in pod_specs(doc):
            for container in spec.get('containers', []) + spec.get('initContainers', []):
                containers += 1
                resources = container.get('resources') or {}
                name = f'{identity}/{container["name"]}'
                if resources.get('limits', {}).get('cpu') is not None:
                    errors.append(f'{name}: CPU limit configured')
                for section, default_key in [('requests', 'defaultRequest'), ('limits', 'default')]:
                    memory = resources.get(section, {}).get('memory')
                    if memory is None:
                        memory = next((entry.get(default_key, {}).get('memory') for entry in defaults.get(namespace, [])
                                       if entry.get(default_key, {}).get('memory') is not None), None)
                    if memory is None or str(memory).strip() in {'', '0', '0Mi', '0Gi'}:
                        errors.append(f'{name}: missing positive memory {section} and namespace fallback')
    return containers, errors


def main():
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rendered', type=Path, required=True)
    args = parser.parse_args()
    inventory = json.loads((args.rendered / 'inventory.json').read_text())
    documents = []
    root = Path(__file__).resolve().parents[2]
    applications = {}
    for path in (root / 'argocd').glob('*.yaml'):
        app = yaml.safe_load(path.read_text())
        if isinstance(app, dict) and app.get('kind') == 'Application':
            applications[app['metadata']['name']] = app
    for name in inventory:
        namespace = applications[name]['spec']['destination']['namespace']
        for doc in yaml.safe_load_all((args.rendered / (name + '.yaml')).read_text()):
            if isinstance(doc, dict):
                documents.append((namespace, doc))
    count, errors = check(documents)
    for error in errors:
        print(error)
    print(f'Container resource policy: {count} containers checked; {len(errors)} errors')
    return bool(errors)


if __name__ == '__main__':
    raise SystemExit(main())
