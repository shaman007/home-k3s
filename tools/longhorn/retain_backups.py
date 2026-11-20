"""Keep the newest completed backups per target/volume across all job labels."""

from collections import defaultdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import ssl
import time
import urllib.error
from urllib.parse import quote
import urllib.request

PREFIX = '/apis/longhorn.io/v1beta2/namespaces/longhorn-system/backups'
KEEP = 20
MAX_DELETES = 25


def plan(items, now):
    """Validate the entire inventory before permitting any destructive request."""
    groups = defaultdict(list)
    for item in items:
        meta, status = item['metadata'], item.get('status', {})
        if meta.get('deletionTimestamp') or status.get('state') != 'Completed':
            continue
        labels = meta.get('labels', {})
        target, volume = labels.get('backup-target'), labels.get('backup-volume')
        if not target or not volume or status.get('error'):
            raise ValueError('Completed backup lacks unambiguous target/volume or has errors')
        if status.get('volumeName') != volume:
            raise ValueError('Backup volume identity disagrees with its label')
        created = datetime.fromisoformat(status['backupCreatedAt'].replace('Z', '+00:00'))
        if created.tzinfo is None or created > now:
            raise ValueError('Invalid or future backup timestamp')
        if not meta.get('uid') or not meta.get('resourceVersion'):
            raise ValueError('Missing deletion preconditions')
        groups[target, volume].append((created, meta['name'], item))
    if not groups:
        raise ValueError('No completed backup sources; refusing an empty inventory')
    result = []
    for key, backups in sorted(groups.items()):
        ordered = sorted(backups, key=lambda value: (value[0], value[1]), reverse=True)
        result.extend(entry[2] for entry in ordered[KEEP:])
    return result, len(groups)


def run(api, apply=False):
    items, token = [], ''
    while True:
        page = api(PREFIX + '?limit=500&continue=' + quote(token, safe=''))
        items.extend(page['items'])
        token = page.get('metadata', {}).get('continue', '')
        if not token:
            break
    expired, groups = plan(items, datetime.now(timezone.utc))
    pending = sum(bool(item['metadata'].get('deletionTimestamp')) for item in items)
    print(json.dumps({'sources': groups, 'completed_inventory': len(items),
                      'keep': KEEP, 'expired': len(expired), 'apply': apply}), flush=True)
    if apply and pending:
        print(f'Waiting for {pending} existing remote deletions; no new requests', flush=True)
        return
    for item in expired[:MAX_DELETES] if apply else expired:
        meta = item['metadata']
        print(('Deleting ' if apply else 'Would delete ') + meta['name'], flush=True)
        if apply:
            path = PREFIX + '/' + quote(meta['name'], safe='')
            api(path, {
                'apiVersion': 'v1', 'kind': 'DeleteOptions',
                'preconditions': {'uid': meta['uid'], 'resourceVersion': meta['resourceVersion']}})
            deadline = time.monotonic() + 60
            while api(path) is not None:
                if time.monotonic() >= deadline:
                    raise TimeoutError('Remote deletion still pending; refusing to grow the queue')
                time.sleep(2)


def main():
    sa = Path('/var/run/secrets/kubernetes.io/serviceaccount')
    context = ssl.create_default_context(cafile=str(sa / 'ca.crt'))
    host = 'https://' + os.environ['KUBERNETES_SERVICE_HOST'] + ':' + os.environ['KUBERNETES_SERVICE_PORT']

    def api(path, delete=None):
        headers = {'Authorization': 'Bearer ' + (sa / 'token').read_text().strip()}
        if delete is not None:
            headers['Content-Type'] = 'application/json'
        request = urllib.request.Request(host + path, headers=headers,
            data=json.dumps(delete).encode() if delete is not None else None,
            method='DELETE' if delete is not None else 'GET')
        try:
            with urllib.request.urlopen(request, context=context, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if error.code == 404 and delete is None and '?' not in path:
                return None
            raise

    run(api, os.environ.get('RETENTION_APPLY') == 'true')


if __name__ == '__main__':
    main()
