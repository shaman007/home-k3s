from pathlib import Path
import fnmatch
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]


class TrimCoverageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        documents = list(yaml.safe_load_all((ROOT / 'longhorn/trim-coverage-guard.yaml').read_text()))
        cls.guard = {'__name__': 'test'}
        exec(next(d for d in documents if d['kind'] == 'ConfigMap')['data']['guard.py'], cls.guard)
        cls.report = {'__name__': 'test'}
        exec(yaml.safe_load((ROOT / 'metrics/config-map-platform-health-report-scripts.yaml').read_text())['data']['platform-health-report.py'], cls.report)

    def setUp(self):
        self.job = {'metadata': {'name': 'trim-daily-a'}, 'spec': {'task': 'filesystem-trim', 'groups': ['trim']}}
        self.volume = {'metadata': {'name': 'pv', 'resourceVersion': '1', 'labels': {'backup': 'enabled'}}}
        self.pvc = {'metadata': {'name': 'data', 'namespace': 'app', 'resourceVersion': '2'}, 'spec': {'storageClassName': 'longhorn', 'volumeName': 'pv'}}

    def check(self, jobs=None, volumes=None, pvcs=None):
        return self.report['pvc_trim_coverage_check'](
            [self.pvc] if pvcs is None else pvcs, [self.volume] if volumes is None else volumes,
            [self.job] if jobs is None else jobs)

    def test_missing_assignment_volume_or_job_fails(self):
        self.assertFalse(self.check()['passed'])
        self.assertFalse(self.check(volumes=[])['passed'])
        self.volume['metadata']['labels']['recurring-job.longhorn.io/trim-daily-a'] = 'enabled'
        self.assertTrue(self.check()['passed'])
        self.assertFalse(self.check(jobs=[])['passed'])
        self.job['metadata']['deletionTimestamp'] = 'now'
        self.assertFalse(self.check()['passed'])

    def test_group_and_disabled_labels(self):
        labels = self.volume['metadata']['labels']
        labels['recurring-job-group.longhorn.io/trim'] = 'enabled'
        self.assertTrue(self.check()['passed'])
        labels['recurring-job-group.longhorn.io/trim'] = 'disabled'
        self.assertFalse(self.check()['passed'])

    def test_empty_inventory_and_unhandled_storage_fail(self):
        self.assertFalse(self.check(pvcs=[])['passed'])
        local = {'metadata': {'name': 'plex-lib'}, 'spec': {'storageClassName': 'local-path'}}
        self.volume['metadata']['labels']['recurring-job.longhorn.io/trim-daily-a'] = 'enabled'
        result = self.check(pvcs=[self.pvc, local])
        self.assertFalse(result['passed'])
        self.assertEqual(['plex-lib'], [d['item'] for d in result['review_details']])
        self.assertIn('explicit review required', result['review_details'][0]['message'])

    def test_guard_repairs_source_first_and_preserves_backup_labels(self):
        self.volume['status'] = {'kubernetesStatus': {'namespace': 'app', 'pvcName': 'data'}}
        self.pvc['metadata']['labels'] = {'recurring-job.longhorn.io/source': 'enabled'}
        writes = []
        def api(path, patch=None):
            if patch is not None:
                writes.append((path, patch))
                return {}
            if path.endswith('recurringjobs'):
                return {'items': [self.job]}
            if path.endswith('volumes'):
                return {'items': [self.volume]}
            return self.pvc
        self.guard['reconcile'](api)
        self.assertEqual(2, len(writes))
        self.assertIn('persistentvolumeclaims', writes[0][0])
        self.assertEqual({'recurring-job.longhorn.io/trim-daily-a': 'enabled'}, writes[1][1]['metadata']['labels'])
        self.assertEqual('1', writes[1][1]['metadata']['resourceVersion'])
        self.assertEqual({'backup': 'enabled'}, self.volume['metadata']['labels'])

    def test_guard_preserves_existing_schedule_and_refuses_missing_fallback(self):
        self.volume['metadata']['labels']['recurring-job-group.longhorn.io/trim'] = 'enabled'
        def api(path, patch=None):
            self.assertIsNone(patch)
            return {'items': [self.job] if path.endswith('recurringjobs') else [self.volume]}
        self.guard['reconcile'](api)
        with self.assertRaises(RuntimeError):
            self.guard['reconcile'](lambda path: {'items': []})

    def test_gitops_includes_guard_and_default_job(self):
        app = yaml.safe_load((ROOT / 'argocd/application-longhorn-custom.yaml').read_text())
        patterns = app['spec']['source']['directory']['include'].strip('{}').split(',')
        for name in ['trim-coverage-guard.yaml', 'recurring-jobs-proposed.yaml']:
            self.assertTrue(any(fnmatch.fnmatch(name, p) for p in patterns))
        jobs = list(yaml.safe_load_all((ROOT / 'longhorn/recurring-jobs-proposed.yaml').read_text()))
        self.assertTrue(any(j['metadata']['name'] == 'trim-daily-a' and j['spec']['task'] == 'filesystem-trim' for j in jobs))
        app = yaml.safe_load((ROOT / 'argocd/application-longhorn.yaml').read_text())
        values = yaml.safe_load(app['spec']['sources'][0]['helm']['values'])
        self.assertTrue(values['persistence']['recurringJobSelector']['enable'])
        self.assertIn('trim-daily-a', values['persistence']['recurringJobSelector']['jobList'])

    def test_source_repair_preserves_hourly_volume_cadence(self):
        self.job['metadata']['name'] = 'trim-hourly'
        self.volume['metadata']['labels']['recurring-job.longhorn.io/trim-hourly'] = 'enabled'
        self.pvc['metadata']['labels'] = {'recurring-job.longhorn.io/source': 'enabled'}
        writes = []
        def api(path, patch=None):
            if patch:
                writes.append(patch)
            return self.pvc
        self.volume['status'] = {'kubernetesStatus': {'namespace': 'app', 'pvcName': 'data'}}
        self.guard['repair_volume'](api, self.volume, [self.job])
        self.assertEqual(1, len(writes))
        self.assertEqual({'recurring-job.longhorn.io/trim-hourly': 'enabled'}, writes[0]['metadata']['labels'])

    def test_volume_repair_uses_source_cadence(self):
        self.job['metadata']['name'] = 'trim-hourly'
        self.pvc['metadata']['labels'] = {'recurring-job.longhorn.io/source': 'enabled',
                                         'recurring-job.longhorn.io/trim-hourly': 'enabled'}
        self.volume['status'] = {'kubernetesStatus': {'namespace': 'app', 'pvcName': 'data'}}
        writes = []
        def api(path, patch=None):
            if patch:
                writes.append((path, patch))
            return self.pvc
        self.guard['repair_volume'](api, self.volume, [self.job])
        self.assertEqual(1, len(writes))
        self.assertIn('/volumes/', writes[0][0])
        self.assertEqual({'recurring-job.longhorn.io/trim-hourly': 'enabled'}, writes[0][1]['metadata']['labels'])

    def test_one_conflict_does_not_starve_later_volumes_and_run_fails(self):
        failed = {'metadata': {'name': 'broken', 'resourceVersion': '3'}}
        writes = []
        def api(path, patch=None):
            if path.endswith('/recurringjobs'):
                return {'items': [self.job]}
            if path.endswith('/volumes'):
                return {'items': [failed, self.volume]}
            if path.endswith('/broken'):
                raise RuntimeError('conflict')
            writes.append(path)
        with self.assertRaisesRegex(RuntimeError, '1 volume'):
            self.guard['reconcile'](api)
        self.assertEqual([self.guard['PREFIX'] + 'volumes/pv'], writes)

    def test_deleting_volumes_and_rebound_pvc_sources_are_not_patched(self):
        self.volume['metadata']['deletionTimestamp'] = 'now'
        self.guard['repair_volume'](lambda *args: self.fail('deleting volume touched'), self.volume, [self.job])
        del self.volume['metadata']['deletionTimestamp']
        self.volume['metadata']['labels']['recurring-job.longhorn.io/trim-daily-a'] = 'enabled'
        self.pvc['metadata']['labels'] = {'recurring-job.longhorn.io/source': 'enabled'}
        self.pvc['spec']['volumeName'] = 'replacement'
        self.volume['status'] = {'kubernetesStatus': {'namespace': 'app', 'pvcName': 'data'}}
        def api(path, patch=None):
            self.assertIsNone(patch)
            return self.pvc
        self.guard['repair_volume'](api, self.volume, [self.job])

    def test_guard_monitor_detects_missing_suspended_stale_and_deleted_definitions(self):
        from datetime import timedelta
        now = self.report['utc_now']()
        jobs = [{'metadata': {'name': name}, 'spec': {'task': 'filesystem-trim'}}
                for name in self.report['EXPECTED_LONGHORN_TRIM_JOBS']]
        cron = {'metadata': {'name': 'trim-coverage-guard'}, 'spec': {},
                'status': {'lastSuccessfulTime': now.isoformat()}}
        check = self.report['longhorn_trim_guard_check']
        self.assertTrue(check([cron], jobs)['passed'])
        self.assertFalse(check([], jobs)['passed'])
        self.assertFalse(check([cron], jobs[:-1])['passed'])
        cron['spec']['suspend'] = True
        self.assertFalse(check([cron], jobs)['passed'])
        cron['spec']['suspend'] = False
        cron['status']['lastSuccessfulTime'] = (now - timedelta(hours=2)).isoformat()
        self.assertFalse(check([cron], jobs)['passed'])

    def test_monitored_trim_definitions_match_gitops(self):
        jobs = list(yaml.safe_load_all((ROOT / 'longhorn/recurring-jobs-proposed.yaml').read_text()))
        expected = {j['metadata']['name'] for j in jobs if j['spec']['task'] == 'filesystem-trim'}
        self.assertEqual(expected, self.report['EXPECTED_LONGHORN_TRIM_JOBS'])

    def test_guard_permissions_and_schedule_remain_narrow(self):
        docs = list(yaml.safe_load_all((ROOT / 'longhorn/trim-coverage-guard.yaml').read_text()))
        role = next(d for d in docs if d['kind'] == 'Role')
        self.assertEqual('longhorn-system', role['metadata']['namespace'])
        permissions = {r['resources'][0]: set(r['verbs']) for r in role['rules']}
        self.assertEqual({'volumes': {'get', 'list', 'patch'}, 'recurringjobs': {'get', 'list'}}, permissions)
        cluster = next(d for d in docs if d['kind'] == 'ClusterRole')
        self.assertEqual([{'apiGroups': [''], 'resources': ['persistentvolumeclaims'], 'verbs': ['get', 'patch']}], cluster['rules'])
        cron = next(d for d in docs if d['kind'] == 'CronJob')
        self.assertEqual('*/15 * * * *', cron['spec']['schedule'])
        self.assertEqual('Forbid', cron['spec']['concurrencyPolicy'])
        pod = cron['spec']['jobTemplate']['spec']['template']['spec']
        self.assertEqual('trim-coverage-guard', pod['serviceAccountName'])
        self.assertTrue(pod['securityContext']['runAsNonRoot'])
        self.assertTrue(pod['containers'][0]['securityContext']['readOnlyRootFilesystem'])

    def test_approved_plex_exception_is_visible_and_not_counted_as_trimmed(self):
        local = {'metadata': {'namespace': 'plex', 'name': 'plex-lib'},
                 'spec': {'storageClassName': 'local-path', 'volumeName': 'local-storage'}}
        self.volume['metadata']['labels']['recurring-job.longhorn.io/trim-daily-a'] = 'enabled'
        result = self.check(pvcs=[self.pvc, local])
        self.assertTrue(result['passed'])
        self.assertIn('1/1 PVC(s)', result['summary'])
        self.assertIn('1 explicitly approved unsupported', result['summary'])
        exception = next(d for d in result['details'] if d['item'] == 'plex-lib')
        self.assertEqual('pvc_trim_unsupported', exception['value_name'])
        self.assertIn('Approved exception', exception['message'])

    def test_plex_exception_cannot_hide_changed_binding_storage_or_other_pvc(self):
        for namespace, name, storage, volume, mode in [
            ('other', 'plex-lib', 'local-path', 'local-storage', 'Filesystem'),
            ('immich', 'immich-library-hdd', 'local-path', 'replacement', 'Filesystem'),
            ('plex', 'plex-lib', 'local-path', 'new-disk', 'Filesystem'),
            ('plex', 'plex-lib', 'longhorn', 'local-storage', 'Filesystem'),
            ('plex', 'plex-lib', 'local-path', 'local-storage', 'Block'),
        ]:
            with self.subTest(namespace=namespace, name=name, storage=storage, volume=volume, mode=mode):
                pvc = {'metadata': {'namespace': namespace, 'name': name},
                       'spec': {'storageClassName': storage, 'volumeName': volume, 'volumeMode': mode}}
                result = self.check(pvcs=[pvc])
                self.assertFalse(result['passed'])
                self.assertEqual([name], [d['item'] for d in result['review_details']])

    def test_both_approved_hdd_exceptions_are_visible_and_scoped(self):
        pvcs = [
            {'metadata': {'namespace': 'plex', 'name': 'plex-lib'},
             'spec': {'storageClassName': 'local-path', 'volumeName': 'local-storage'}},
            {'metadata': {'namespace': 'immich', 'name': 'immich-library-hdd'},
             'spec': {'storageClassName': 'local-path', 'volumeName': 'immich-library-hdd'}},
        ]
        self.volume['metadata']['labels']['recurring-job.longhorn.io/trim-daily-a'] = 'enabled'
        result = self.check(pvcs=[self.pvc] + pvcs)
        self.assertTrue(result['passed'])
        self.assertIn('1/1 PVC(s)', result['summary'])
        self.assertIn('2 explicitly approved unsupported', result['summary'])
        self.assertEqual(2, sum(d['value_name'] == 'pvc_trim_unsupported' for d in result['details']))
        self.assertEqual({('plex', 'plex-lib'), ('immich', 'immich-library-hdd')},
                         set(self.report['PVC_TRIM_UNSUPPORTED']))

    def test_batch_pvc_attachment_window_and_source_assignment(self):
        window = yaml.safe_load((ROOT / 'ooni/cron-job-ooniprobe-trim-window.yaml').read_text())
        check = self.report['pvc_trim_attachment_check']
        self.assertTrue(check([window])['passed'])
        self.assertFalse(check([])['passed'])
        import copy
        for fault in ['suspend', 'schedule', 'timeZone', 'claim']:
            broken = copy.deepcopy(window)
            if fault == 'suspend': broken['spec']['suspend'] = True
            elif fault == 'schedule': broken['spec']['schedule'] = '0 1 * * *'
            elif fault == 'timeZone': broken['spec']['timeZone'] = 'Europe/Prague'
            else: broken['spec']['jobTemplate']['spec']['template']['spec']['volumes'][0]['persistentVolumeClaim']['claimName'] = 'other'
            self.assertFalse(check([broken])['passed'])
        pod = window['spec']['jobTemplate']['spec']['template']['spec']
        self.assertFalse(pod['automountServiceAccountToken'])
        self.assertIn('time.sleep(900)', pod['containers'][0]['command'][-1])
        self.assertTrue(pod['securityContext']['runAsNonRoot'])
        pvc = yaml.safe_load((ROOT / 'ooni/persistent-volume-claim-ooniprobe.yaml').read_text())
        self.assertEqual('enabled', pvc['metadata']['labels']['recurring-job.longhorn.io/trim-daily-a'])
        jobs = list(yaml.safe_load_all((ROOT / 'longhorn/recurring-jobs-proposed.yaml').read_text()))
        daily = next(j for j in jobs if j['metadata']['name'] == 'trim-daily-a')
        self.assertEqual('5 0 * * *', daily['spec']['cron'])
