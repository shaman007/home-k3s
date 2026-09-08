from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]


class LonghornReportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = yaml.safe_load((ROOT / 'metrics/config-map-platform-health-report-scripts.yaml').read_text())['data']['platform-health-report.py']
        cls.report = {'__name__': 'test'}
        exec(compile(source, 'report', 'exec'), cls.report)

    def setUp(self):
        self.now = datetime.now(timezone.utc)
        self.cutoff = self.now - timedelta(hours=24)
        self.jobs = [self.job('daily', 'backup', ['protected']), self.job('trim', 'filesystem-trim')]

    def job(self, name, task, groups=None):
        return {'metadata': {'name': name}, 'spec': {'task': task, 'groups': groups or []}}

    def volume(self, name, labels=None):
        return {'metadata': {'name': name, 'labels': labels if labels is not None else {'recurring-job.longhorn.io/daily': 'enabled'}}}

    def backup(self, volume, age=1, state='Completed', target='default'):
        return {'status': {'volumeName': volume, 'backupTargetName': target, 'state': state,
                           'backupCreatedAt': (self.now-timedelta(hours=age)).isoformat(),
                           'lastSyncedAt': self.now.isoformat()}}

    def check_backups(self, volumes, backups):
        return self.report['longhorn_backup_check'](volumes, self.jobs, backups, self.cutoff)

    def test_fresh_backup_cannot_hide_stale_or_missing_volume(self):
        result = self.check_backups([self.volume('fresh'), self.volume('stale'), self.volume('missing')],
                                    [self.backup('fresh'), self.backup('stale', age=168)])
        self.assertFalse(result['passed'])
        self.assertEqual({'stale', 'missing'}, {d['item'] for d in result['review_details']})

    def test_refresh_timestamp_does_not_make_old_backup_fresh(self):
        self.assertFalse(self.check_backups([self.volume('v')], [self.backup('v', age=168)])['passed'])

    def test_group_membership_is_resolved_and_trim_only_volume_is_excluded(self):
        volumes = [self.volume('group', {'recurring-job-group.longhorn.io/protected': 'enabled'}),
                   self.volume('trim', {'recurring-job.longhorn.io/trim': 'enabled'})]
        result = self.check_backups(volumes, [self.backup('group')])
        self.assertTrue(result['passed'])
        self.assertEqual(['group'], [d['item'] for d in result['details']])

    def test_latest_success_wins_over_historical_errors(self):
        self.assertTrue(self.check_backups([self.volume('v')], [self.backup('v', 48, 'Error'), self.backup('v')])['passed'])

    def test_failed_backup_and_wrong_target_do_not_count(self):
        for backup in [self.backup('v', state='Error'), self.backup('v', target='other')]:
            with self.subTest(backup=backup):
                self.assertFalse(self.check_backups([self.volume('v')], [backup])['passed'])

    def test_no_expected_volumes_is_not_healthy(self):
        self.assertFalse(self.check_backups([], [])['passed'])

    def cronjob(self, name, age=1, suspended=False):
        return {'metadata': {'name': name, 'ownerReferences': [{'kind': 'RecurringJob', 'apiVersion': 'longhorn.io/v1beta2', 'name': name}]},
                'spec': {'suspend': suspended}, 'status': {'lastSuccessfulTime': (self.now-timedelta(hours=age)).isoformat()}}

    def test_maintenance_passes_without_any_pod_history(self):
        result = self.report['longhorn_maintenance_check'](self.jobs, [self.cronjob('daily'), self.cronjob('trim')], self.cutoff)
        self.assertTrue(result['passed'])

    def test_each_missing_stale_suspended_job_fails(self):
        for cronjobs in [[self.cronjob('trim')], [self.cronjob('daily', age=48), self.cronjob('trim')],
                         [self.cronjob('daily', suspended=True), self.cronjob('trim')]]:
            result = self.report['longhorn_maintenance_check'](self.jobs, cronjobs, self.cutoff)
            self.assertFalse(result['passed'])
            self.assertEqual(['daily'], [d['item'] for d in result['review_details']])

    def test_report_role_can_read_volume_inventory(self):
        role = yaml.safe_load((ROOT / 'metrics/cluster-role-platform-health-report.yaml').read_text())
        self.assertTrue(any('longhorn.io' in r['apiGroups'] and 'volumes' in r['resources'] and 'list' in r['verbs'] for r in role['rules']))
