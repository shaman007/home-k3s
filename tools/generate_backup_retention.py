"""Render the two count-based backup retention consumers from tracked scripts."""
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]


def cron(namespace, name, image, command, config, schedule, token=False):
    container = {
        'name': 'retention', 'image': image, 'command': command,
        'env': [{'name': 'RETENTION_APPLY', 'value': 'true'},
                {'name': 'PYTHONDONTWRITEBYTECODE', 'value': '1'}],
        'resources': {'requests': {'cpu': '10m', 'memory': '64Mi'},
                      'limits': {'memory': '256Mi'}},
        'securityContext': {'allowPrivilegeEscalation': False,
                            'readOnlyRootFilesystem': True, 'capabilities': {'drop': ['ALL']}},
        'volumeMounts': [{'name': 'config', 'mountPath': '/config', 'readOnly': True},
                         {'name': 'tmp', 'mountPath': '/tmp'}]}
    pod = {'automountServiceAccountToken': token, 'restartPolicy': 'Never',
           'securityContext': {'runAsNonRoot': True, 'runAsUser': 1000,
                               'runAsGroup': 1000, 'fsGroup': 1000,
                               'seccompProfile': {'type': 'RuntimeDefault'}},
           'containers': [container],
           'volumes': [{'name': 'config', 'configMap': {'name': name}},
                       {'name': 'tmp', 'emptyDir': {'sizeLimit': '32Mi'}}]}
    if token:
        pod['serviceAccountName'] = name
    else:
        container['envFrom'] = [{'secretRef': {'name': 'talos-backup-config'}}]
        container['env'].extend([{'name': 'AWS_REGION', 'value': 'us-east-1'},
                                 {'name': 'HOME', 'value': '/tmp'}])
    return [
        {'apiVersion': 'v1', 'kind': 'ConfigMap',
         'metadata': {'name': name, 'namespace': namespace}, 'data': config},
        {'apiVersion': 'batch/v1', 'kind': 'CronJob',
         'metadata': {'name': name, 'namespace': namespace},
         'spec': {'schedule': schedule, 'timeZone': 'Etc/UTC', 'concurrencyPolicy': 'Forbid',
                  'startingDeadlineSeconds': 600, 'successfulJobsHistoryLimit': 1,
                  'failedJobsHistoryLimit': 2, 'jobTemplate': {'spec': {'backoffLimit': 0,
                  'activeDeadlineSeconds': 900, 'template': {
                      'metadata': {'labels': {'app': name if token else 'talos-backup'}},
                      'spec': pod}}}}}]


def documents():
    namespace, name = 'longhorn-system', 'backup-retention'
    rbac = [
        {'apiVersion': 'v1', 'kind': 'ServiceAccount',
         'metadata': {'name': name, 'namespace': namespace}},
        {'apiVersion': 'rbac.authorization.k8s.io/v1', 'kind': 'Role',
         'metadata': {'name': name, 'namespace': namespace}, 'rules': [
             {'apiGroups': ['longhorn.io'], 'resources': ['backups'], 'verbs': ['get', 'list', 'delete']}]},
        {'apiVersion': 'rbac.authorization.k8s.io/v1', 'kind': 'RoleBinding',
         'metadata': {'name': name, 'namespace': namespace},
         'roleRef': {'apiGroup': 'rbac.authorization.k8s.io', 'kind': 'Role', 'name': name},
         'subjects': [{'kind': 'ServiceAccount', 'name': name, 'namespace': namespace}]}]
    longhorn = rbac + cron(namespace, name,
        'harbor.andreybondarenko.com/dockerhub/library/python:3.15-alpine',
        ['python3', '/config/retention.py'],
        {'retention.py': (ROOT / 'tools/longhorn/retain_backups.py').read_text()}, '*/15 * * * *', True)
    talos = cron('talos-backup', 'talos-backup-retention',
        'harbor.andreybondarenko.com/dockerhub/amazon/aws-cli@sha256:4a1a668837d5f97ced202e03827da1bc0b48cda946be89909cd7a02023f62921',
        ['/bin/bash', '/config/retention.sh'],
        {'retention.sh': (ROOT / 'tools/talos_retain_backups.sh').read_text()}, '*/15 * * * *')
    return {'longhorn/backup-retention.yaml': longhorn,
            'talos-backup/backup-retention.yaml': talos}


if __name__ == '__main__':
    for path, docs in documents().items():
        (ROOT / path).write_text(yaml.safe_dump_all(docs, sort_keys=False, width=110))
