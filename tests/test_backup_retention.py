"""Exercise count retention, failure safety, pagination and generated consumers."""
from datetime import datetime, timedelta, timezone
import importlib.util
import json
import os
from pathlib import Path
import subprocess  # nosec B404
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]


def module(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


r = module(ROOT / 'tools/longhorn/retain_backups.py')
g = module(ROOT / 'tools/generate_backup_retention.py')
NOW = datetime.now(timezone.utc)


def backup(index, volume='one', target='default', job='daily'):
    return {'metadata': {'name': f'b-{volume}-{target}-{index:03}', 'uid': str(index),
                         'resourceVersion': '10', 'labels': {
                             'backup-volume': volume, 'backup-target': target}},
            'spec': {'labels': {'RecurringJob': job}},
            'status': {'state': 'Completed', 'volumeName': volume,
                       'backupCreatedAt': (NOW - timedelta(hours=index)).isoformat()}}


class BackupRetentionTests(unittest.TestCase):
    def test_combines_jobs_and_manual_copies_and_isolates_sources(self):
        items = [backup(i, job=['daily', 'monthly', 'manual'][i % 3]) for i in range(40)]
        items += [backup(i, volume='two') for i in range(4)]
        items += [backup(i, target='other') for i in range(20)]
        expired, sources = r.plan(items, NOW)
        self.assertEqual(sources, 3)
        self.assertEqual({b['metadata']['name'] for b in expired},
                         {f'b-one-default-{i:03}' for i in range(20, 40)})

    def test_incomplete_and_deleting_copies_do_not_displace_successful_ones(self):
        items = [backup(i) for i in range(20)]
        pending = backup(21); pending['status']['state'] = 'InProgress'
        deleting = backup(22); deleting['metadata']['deletionTimestamp'] = NOW.isoformat()
        self.assertEqual(r.plan(items + [pending, deleting], NOW)[0], [])

    def test_bad_identity_timestamp_or_error_aborts_entire_inventory(self):
        for edit in ('identity', 'date', 'future', 'error', 'precondition'):
            with self.subTest(edit=edit):
                b = backup(30)
                if edit == 'identity': b['status']['volumeName'] = 'wrong'
                if edit == 'date': b['status']['backupCreatedAt'] = 'bad'
                if edit == 'future': b['status']['backupCreatedAt'] = (NOW + timedelta(days=1)).isoformat()
                if edit == 'error': b['status']['error'] = 'failed'
                if edit == 'precondition': del b['metadata']['uid']
                with self.assertRaises(ValueError):
                    r.plan([backup(i) for i in range(25)] + [b], NOW)

    def test_pagination_and_uid_resource_version_guarded_delete(self):
        calls = []
        def api(path, delete=None):
            calls.append((path, delete))
            if delete:
                self.assertEqual(delete['preconditions'], {'uid': '20', 'resourceVersion': '10'})
                return {}
            if path.endswith('/b-one-default-020'):
                return None
            if 'continue=next' in path:
                return {'items': [backup(20)], 'metadata': {}}
            return {'items': [backup(i) for i in range(20)], 'metadata': {'continue': 'next'}}
        r.run(api, True)
        self.assertEqual(len(calls), 4)

    def test_existing_pending_remote_deletions_block_more_requests(self):
        items = [backup(i) for i in range(30)]
        items[-1]['metadata']['deletionTimestamp'] = NOW.isoformat()
        calls = []
        def api(path, delete=None):
            calls.append(delete)
            return {'items': items, 'metadata': {}}
        r.run(api, True)
        self.assertEqual(calls, [None])

    def test_generated_manifests_and_native_backup_retention_match(self):
        for path, documents in g.documents().items():
            self.assertEqual(list(yaml.safe_load_all((ROOT / path).read_text())), documents)
        jobs = list(yaml.safe_load_all((ROOT / 'longhorn/recurring-jobs-proposed.yaml').read_text()))
        self.assertEqual(sum(j['spec']['task'] == 'backup' for j in jobs), 8)
        for job in jobs:
            if job['spec']['task'] == 'backup': self.assertEqual(job['spec']['retain'], 20)
            if job['spec']['task'] == 'filesystem-trim': self.assertEqual(job['spec']['retain'], 0)

    def run_talos(self, apply=True, bad=False, list_fail=False):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            rows = []
            for i in range(35):
                date = NOW + timedelta(hours=1) if bad and i == 34 else NOW - timedelta(minutes=i)
                rows.append(f'{date.isoformat()}\thome-k8s/test-{i:03}.snap.zst.age\t"etag{i}"\t100')
            (p / 'rows').write_text('\n'.join(reversed(rows)) + '\n')
            (p / 'aws').write_text('#!/bin/bash\nset -eu\ncase "$*" in\n'
                '*list-objects-v2*) cat "$FIXTURE/rows"; exit "${LIST_FAIL:-0}";;\n'
                '*) echo "$*" >> "$FIXTURE/calls";;\nesac\n')
            (p / 'aws').chmod(0o700)
            env = dict(os.environ, PATH=tmp + ':' + os.environ['PATH'], FIXTURE=tmp,
                       RETENTION_APPLY=str(apply).lower(), LIST_FAIL='1' if list_fail else '0')
            result = subprocess.run(['bash', str(ROOT / 'tools/talos_retain_backups.sh')],
                                    env=env, capture_output=True, text=True, check=False)
            calls = (p / 'calls').read_text() if (p / 'calls').exists() else ''
            return result, calls

    def test_talos_preserves_twenty_newest_and_uses_conditional_deletion(self):
        result, calls = self.run_talos()
        self.assertEqual(result.returncode, 0, result.stderr)
        deleted = [line for line in calls.splitlines() if 'delete-object' in line]
        self.assertEqual(len(deleted), 15)
        self.assertTrue(all('--if-match' in line for line in deleted))
        for i in range(20, 35): self.assertIn(f'test-{i:03}.snap.zst.age', calls)
        self.assertNotIn('delete-bucket-lifecycle', calls)

    def test_talos_dry_run_future_and_partial_listing_never_delete(self):
        for kwargs in ({'apply': False}, {'bad': True}, {'list_fail': True}):
            result, calls = self.run_talos(**kwargs)
            self.assertEqual(calls, '')
            if kwargs.get('apply') is not False: self.assertNotEqual(result.returncode, 0)


if __name__ == '__main__':
    unittest.main()
