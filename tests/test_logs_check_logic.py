from datetime import datetime, timedelta
from pathlib import Path
import json
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo
import yaml

ROOT = Path(__file__).resolve().parents[1]


class LogsCheckLogicTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = yaml.safe_load((ROOT / 'metrics/config-map-logs-check-scripts.yaml').read_text())['data']['logs-check.py']
        cls.code = compile(source, 'logs-check.py', 'exec')

    def setUp(self):
        self.report = {'__name__': 'test'}
        exec(self.code, self.report)

    def entry(self, line, pod='sidekiq-one', ts='2026-10-30T03:00:00+00:00'):
        return dict(namespace='mastodon', container='mastodon', pod=pod, line=line, ts=ts, ts_ns=1)

    def test_mail_arguments_are_removed_and_error_retained(self):
        line = 'INFO context=Job raised exception job={"wrapped" => "ActionMailer::MailDeliveryJob", "arguments" => ["PRIVATE_ARGUMENT"]}: execution expired (Net::OpenTimeout)'
        safe = self.report['safe_log_line'](line)
        self.assertNotIn('PRIVATE_ARGUMENT', safe)
        self.assertIn('ActionMailer::MailDeliveryJob', safe)
        self.assertIn('Net::OpenTimeout', safe)
        self.assertNotIn('PRIVATE_ARGUMENT', self.report['trim_line'](line))

    def test_truncated_job_dump_never_exposes_arguments(self):
        safe = self.report['safe_log_line']('context=Job raised exception job={"args": ["PRIVATE_ARGUMENT"]')
        self.assertNotIn('PRIVATE_ARGUMENT', safe)
        self.assertIn('unavailable', safe)

    def test_retries_across_pods_are_one_prompt_pattern(self):
        entries = [self.entry('Net::OpenTimeout execution expired', pod='one'), self.entry('Net::OpenTimeout execution expired', pod='two')]
        groups = self.report['group_patterns'](entries)
        self.assertEqual(1, len(groups))
        prompt = '\n'.join(self.report['build_log_batches']({'real_fault_candidates': entries}))
        self.assertIn('sampled_count=2', prompt)

    def test_noise_is_not_sent_to_analyst(self):
        item = self.entry('No status changes. Skipping patch')
        item.update(namespace='argocd', container='argocd-application-controller')
        filtered, counts, _ = self.report['filter_false_positives']({'noise_candidates': [item]})
        self.assertEqual({'noise_candidates': 1}, counts)
        self.assertEqual([], self.report['build_log_batches'](filtered))

    def test_event_pod_identity_is_recovered_without_inventing_container(self):
        item = self.entry('name=keycloak-0 kind=Pod reason=Unhealthy type=Warning count=20', pod='')
        item.update(namespace='keycloak', container='')
        filtered, _, _ = self.report['filter_false_positives']({'probe_instability_candidates': [item]})
        event = filtered['probe_instability_candidates'][0]
        self.assertEqual('keycloak-0', event['pod'])
        self.assertEqual('', event['container'])
        self.assertEqual('', item['pod'])

    def test_keycloak_warning_repetitions_group_but_clients_remain_distinct(self):
        def warning(time, client):
            item = self.entry(f"2026-11-03 {time} WARN Client '{client}' Full scope allowed is deprecated")
            item.update(namespace='keycloak', container='keycloak')
            return item
        groups = self.report['group_patterns']([warning('07:30:04,540', 'argocd'),
                                               warning('08:00:04,400', 'argocd'),
                                               warning('08:00:06,303', 'harbor')])
        self.assertEqual([1, 2], sorted(g['count'] for g in groups.values()))

    def test_longhorn_patterns_merge_managers_without_merging_volumes(self):
        def warning(pod, volume):
            item = self.entry(f'Failed to get purge status for engine pvc-{volume}-e-0', pod=pod)
            item.update(namespace='longhorn-system', container='longhorn-manager')
            return item
        first = 'ac9d6cd7-76b1-43c7-a4f5-81e6c597811c'
        second = 'bc9d6cd7-76b1-43c7-a4f5-81e6c597811c'
        entries = [warning('manager-a', first), warning('manager-b', first), warning('manager-b', second)]
        groups = self.report['group_patterns'](entries)
        self.assertEqual([1, 2], sorted(g['count'] for g in groups.values()))
        rendered = self.report['render_observed_evidence']({'platform_issue_candidates': entries}, {}, {}, {})
        self.assertEqual(2, rendered.count('**Platform pattern:'))
        self.assertIn('Categories overlap', rendered)

    def test_warning_evidence_includes_actionable_pattern_not_just_source_count(self):
        item = self.entry("Client 'argocd' Full scope allowed is deprecated")
        item.update(namespace='keycloak', container='keycloak')
        rendered = self.report['render_observed_evidence']({'noise_candidates': [item]}, {}, {}, {})
        self.assertIn('Warning pattern: keycloak/keycloak', rendered)
        self.assertIn('Full scope allowed', rendered)

    def test_unfamiliar_warning_is_sent_to_analyst(self):
        item = self.entry('Warning: unknown database corruption')
        filtered, _, _ = self.report['filter_false_positives']({'noise_candidates': [item]})
        self.assertIn('unknown database corruption', '\n'.join(self.report['build_log_batches'](filtered)))

    def test_successful_argo_resource_result_is_not_a_fault(self):
        item = self.entry(json.dumps(dict(level='info', kind='PolicyException',
                          msg="Adding resource result, status: 'Synced', phase: 'Running', message: 'updated'")))
        item.update(namespace='argocd', container='argocd-application-controller')
        self.assertTrue(self.report['is_false_positive']('real_fault_candidates', item))
        item['line'] = item['line'].replace("'Synced'", "'SyncFailed'")
        self.assertFalse(self.report['is_false_positive']('real_fault_candidates', item))

    def test_helm_invocation_filter_preserves_failures_and_unknown_messages(self):
        item = self.entry('')
        item.update(namespace='argocd', container='argocd-repo-server')
        for level, message, expected in [('info', 'Executing command', True),
                                         ('error', 'Executing command', False),
                                         ('info', 'command failed', False)]:
            item['line'] = json.dumps(dict(level=level, msg=message,
                                          args='[helm template . --api-versions kyverno.io/v2/PolicyException]'))
            self.assertEqual(expected, self.report['is_false_positive']('real_fault_candidates', item))
        for line in ('not JSON', '[]', 'null'):
            item['line'] = line
            self.assertFalse(self.report['is_false_positive']('real_fault_candidates', item))

    def test_kyverno_deprecation_remains_in_warning_analysis(self):
        item = self.entry('INF Warning: kyverno.io/v2 PolicyException is deprecated and will be removed')
        item.update(namespace='kyverno', container='kyverno')
        filtered, _, _ = self.report['filter_false_positives'](
            {'real_fault_candidates': [item], 'noise_candidates': [item]})
        self.assertEqual([], filtered['real_fault_candidates'])
        self.assertEqual([item], filtered['noise_candidates'])
        self.assertIn('deprecated', '\n'.join(self.report['build_log_batches'](filtered)))

    def test_argo_exception_resource_names_do_not_turn_success_into_faults(self):
        cases = [
            ('argocd-notifications-controller', 'Start processing'),
            ('argocd-notifications-controller', 'Processing completed'),
            ('argocd-application-controller', 'Reconciliation completed'),
            ('argocd-repo-server', 'manifest cache hit'),
            ('argocd-repo-server', 'manifest cache hit: kyverno-exceptions'),
        ]
        for container, message in cases:
            with self.subTest(container=container):
                item = dict(self.entry(''), namespace='argocd', container=container)
                for level, expected in [('info', True), ('error', False), ('warning', False)]:
                    item['line'] = json.dumps(dict(level=level, msg=message,
                                                  application='kyverno-exceptions'))
                    self.assertEqual(expected, self.report['is_false_positive']('real_fault_candidates', item))
                item['line'] = json.dumps(dict(level='info', msg='exception while processing',
                                              application='kyverno-exceptions'))
                self.assertFalse(self.report['is_false_positive']('real_fault_candidates', item))

    def test_dawarich_frames_do_not_hide_database_failure(self):
        frame = self.entry("actionpack (8.1.3.1) lib/action_dispatch/middleware/show_exceptions.rb:32:in 'ActionDispatch::ShowExceptions#call'")
        frame.update(namespace='dawarich', container='dawarich')
        failure = dict(frame, line='ActiveRecord::ConnectionNotEstablished (No route to host)')
        filtered, _, _ = self.report['filter_false_positives']({'real_fault_candidates': [frame, failure]})
        self.assertEqual([failure], filtered['real_fault_candidates'])
        self.assertIn('ConnectionNotEstablished', '\n'.join(self.report['build_log_batches'](filtered)))

    def test_evidence_labels_are_candidates_not_confirmed_faults(self):
        rendered = self.report['render_observed_evidence'](
            {'real_fault_candidates': [self.entry('PG::ConnectionBad')]}, {}, {}, {})
        self.assertIn('Fault candidate log lines after filtering', rendered)
        self.assertNotIn('Real fault evidence', rendered)

    def test_daily_collection_visits_all_hours_and_marks_caps(self):
        calls = []
        def query(q, start, end, limit):
            calls.append((start, end))
            return [self.entry('timeout')]*limit if len(calls) == 1 else []
        self.report['loki_query_range'] = query
        entries, coverage = self.report['collect_window']('query', 0, 24*3600*10**9, 2)
        self.assertEqual(24, len(calls))
        self.assertEqual(calls[0][1]+1, calls[1][0])
        self.assertFalse(coverage['ok'])
        self.assertEqual(1, len(coverage['capped_hour_starts']))

    def test_unlimited_collection_paginates_beyond_one_response(self):
        def response(timestamps):
            return {'data': {'result': [{'stream': {'namespace': 'mail'},
                    'values': [[str(ts), 'authentication failure'] for ts in timestamps]}]}}
        responses = iter([response([9, 8]), response([7, 6]), response([5])])
        self.report['http_json'] = lambda _: next(responses)
        with patch.dict('os.environ', {'LOKI_BATCH_LIMIT': '2'}):
            entries, coverage = self.report['collect_window']('query', 0, 10, 0)
        self.assertEqual([9, 8, 7, 6, 5], [e['ts_ns'] for e in entries])
        self.assertTrue(coverage['ok'])
        self.assertEqual([], coverage['capped_hour_starts'])

    def test_all_queries_exclude_checker_logs(self):
        import ast
        source = yaml.safe_load((ROOT / 'metrics/config-map-logs-check-scripts.yaml').read_text())['data']['logs-check.py']
        main = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == 'main')
        queries = next(ast.literal_eval(n.value) for n in main.body if isinstance(n, ast.Assign)
                       and any(isinstance(t, ast.Name) and t.id == 'queries' for t in n.targets))
        for query in queries.values():
            self.assertIn('pod!~"logs-check-.*"', query)
            self.assertIn('container!="logs-check"', query)

    def test_all_patterns_are_batched_for_analysis(self):
        entries = [self.entry(f"distinct error {i}") for i in range(80)]
        batches = self.report['build_log_batches']({'real_fault_candidates': entries})
        self.assertEqual(80, "\n".join(batches).count('sampled_count='))

    def test_fast_batches_keep_strong_final_synthesis(self):
        calls = []
        def analyst(system, prompt, **kwargs):
            calls.append(kwargs.get('model', 'default'))
            return 'Evidence reviewed'
        self.report['call_ollama'] = analyst
        self.report['build_log_batches'] = lambda _: ['first batch', 'second batch']
        preflight = {}
        start = datetime(2026, 11, 1, tzinfo=ZoneInfo('UTC'))
        with patch.dict('os.environ', {'OLLAMA_BATCH_MODEL': 'gemma3:4b', 'OLLAMA_MODEL': 'gpt-oss:20b'}):
            self.report['analyze_logs_with_ollama'](start, start+timedelta(days=1), preflight, '',
                                                  {'real_fault_candidates': [self.entry('SMTP authentication failed')]})
        self.assertEqual(['gemma3:4b', 'gemma3:4b', 'gemma3:4b', 'default'], calls)
        self.assertTrue(preflight['analyst_execution']['ok'])
        self.assertEqual(2, preflight['analyst_execution']['completed_batches'])
        self.assertEqual('gpt-oss:20b', preflight['analyst_execution']['summary_model'])

    def test_empty_batch_does_not_claim_complete_analysis(self):
        self.report['call_ollama'] = lambda *args, **kwargs: ''
        preflight = {}
        start = datetime(2026, 11, 1, tzinfo=ZoneInfo('UTC'))
        with self.assertRaisesRegex(RuntimeError, 'empty summary'):
            self.report['analyze_logs_with_ollama'](start, start+timedelta(days=1), preflight, '',
                                                  {'real_fault_candidates': [self.entry('SMTP authentication failed')]})
        self.assertFalse(preflight['analyst_execution']['ok'])
        self.assertEqual(0, preflight['analyst_execution']['completed_batches'])

    def test_history_keeps_more_than_two_thousand_patterns(self):
        start = datetime(2026, 10, 29, 5, tzinfo=ZoneInfo('Europe/Prague'))
        self.report['kube_json'] = lambda _: {'data': {}}
        counts, text, complete = self.report['pattern_history'](
            {'real_fault_candidates': [self.entry(f'distinct {i}') for i in range(2001)]},
            'report', start, start+timedelta(days=1))
        self.assertEqual(2001, len(counts))
        self.assertTrue(complete)
        self.assertNotIn('capped', text)
        self.assertNotIn('newly observed:', text)

    def history_backend(self):
        import copy
        import urllib.error
        objects = {}
        def api(path, method='GET', payload=None):
            name = path.rsplit('/', 1)[-1]
            if method == 'POST':
                name = payload['metadata']['name']
                if name in objects:
                    raise urllib.error.HTTPError(path, 409, 'exists', None, None)
                obj = copy.deepcopy(payload)
                obj['metadata'].update(uid='uid-'+name, resourceVersion='1')
                objects[name] = obj
            elif method == 'PUT':
                uid = objects[name]['metadata']['uid']
                objects[name] = copy.deepcopy(payload)
                objects[name]['metadata']['uid'] = uid
            elif method == 'DELETE':
                return objects.pop(name)
            elif name not in objects:
                raise urllib.error.HTTPError(path, 404, 'missing', None, None)
            return copy.deepcopy(objects[name])
        self.report['kube_json'] = api
        return objects

    def test_sharded_history_roundtrip_and_two_snapshot_retention(self):
        objects = self.history_backend()
        counts = {f'{n:024x}': n+1 for n in range(35000)}
        def save(day, values):
            self.report['upsert_report']('test-report', 'report', {
                'window_start': f'2026-10-{day:02}T00:00:00+00:00',
                'window_end': f'2026-10-{day+1:02}T00:00:00+00:00',
                'pattern_counts': values, 'pattern_history_complete': True})
            return json.loads(objects['test-report']['data']['report.json'])
        first = save(20, counts)
        self.assertGreater(len(first['pattern_history_storage']['shards']), 1)
        self.assertEqual(counts, self.report['load_pattern_counts'](first))
        for name in first['pattern_history_storage']['shards']:
            self.assertLess(len(objects[name]['data']['patterns.json']), 500000)
            self.assertEqual('test-report', objects[name]['metadata']['ownerReferences'][0]['name'])
        second = save(21, {'second': 7})
        self.assertEqual(first['pattern_history_storage'], second['previous_pattern_history_storage'])
        save(22, {'third': 8})
        self.assertTrue(all(name not in objects for name in first['pattern_history_storage']['shards']))
        self.assertTrue(all(name in objects for name in second['pattern_history_storage']['shards']))
        save(22, {'third': 8})  # Snapshot creation is idempotent.

    def test_missing_or_corrupt_shard_is_not_an_empty_baseline(self):
        objects = self.history_backend()
        start = datetime(2026, 10, 22, tzinfo=ZoneInfo('UTC'))
        self.report['upsert_report']('test-report', '', {
            'window_start': (start-timedelta(days=1)).isoformat(), 'window_end': start.isoformat(),
            'pattern_counts': {'key': 4}, 'pattern_history_complete': True,
            'preflight': {'collection': {'ok': True}}})
        previous = json.loads(objects['test-report']['data']['report.json'])
        shard = previous['pattern_history_storage']['shards'][0]
        objects[shard]['data']['patterns.json'] = '{"key":5}'
        _, text, _ = self.report['compare_pattern_history'](
            {'key': 4}, {'key': ('fault', 'ns', 'container', 'signature')},
            'test-report', start, start+timedelta(days=1))
        self.assertIn('History could not be read', text)
        self.assertNotIn('recurring sampled patterns.', text)
        del objects[shard]
        with self.assertRaises(Exception):
            self.report['load_pattern_counts'](previous)

    def test_incomplete_collection_cannot_be_a_recurrence_baseline(self):
        start = datetime(2026, 10, 22, tzinfo=ZoneInfo('UTC'))
        old = {'window_start': (start-timedelta(days=1)).isoformat(), 'window_end': start.isoformat(),
               'pattern_counts': {'key': 4}, 'pattern_history_complete': True,
               'preflight': {'collection': {'ok': False}}}
        self.report['kube_json'] = lambda _: {'data': {'report.json': json.dumps(old)}}
        _, text, complete = self.report['compare_pattern_history'](
            {'key': 4}, {'key': ('fault', 'ns', 'container', 'signature')},
            'test-report', start, start+timedelta(days=1))
        self.assertTrue(complete)
        self.assertIn('not comparable', text)

    def test_recurrence_includes_patterns_beyond_former_cap(self):
        self.history_backend()
        start = datetime(2026, 10, 22, tzinfo=ZoneInfo('UTC'))
        entries = [self.entry(f'failure signature {n}') for n in range(2501)]
        counts, _ = self.report['count_patterns']({'real_fault_candidates': entries})
        self.report['upsert_report']('test-report', '', {
            'window_start': (start-timedelta(days=1)).isoformat(), 'window_end': start.isoformat(),
            'pattern_counts': counts, 'pattern_history_complete': True,
            'preflight': {'collection': {'ok': True}}})
        current, text, complete = self.report['pattern_history'](
            {'real_fault_candidates': entries + [self.entry('new signature')]},
            'test-report', start, start+timedelta(days=1))
        self.assertEqual(2502, len(current))
        self.assertTrue(complete)
        self.assertIn('1 newly observed sampled patterns; 2501 recurring sampled patterns.', text)

    def test_scheduled_seed_survives_manual_report_and_is_consumed(self):
        objects = self.history_backend()
        name = 'test-report'
        start = datetime(2026, 11, 1, 5, tzinfo=ZoneInfo('UTC'))
        self.report['upsert_report'](name, '', {
            'window_start': (start-timedelta(hours=18)).isoformat(),
            'window_end': (start+timedelta(hours=6)).isoformat(),
            'pattern_counts': {'manual': 1}, 'pattern_history_complete': True,
            'preflight': {'collection': {'ok': True}}})
        manual = json.loads(objects[name]['data']['report.json'])
        seed_ref = self.report['store_pattern_counts']({'seed': 3}, objects[name]['metadata'],
                       (start-timedelta(days=1)).isoformat(), start.isoformat())
        manual['recurrence_baseline'] = {'window_start': (start-timedelta(days=1)).isoformat(),
            'window_end': start.isoformat(), 'pattern_history_storage': seed_ref,
            'pattern_history_complete': True, 'preflight': {'collection': {'ok': True}}}
        self.report['upsert_report'](name, '', manual)
        _, text, _ = self.report['compare_pattern_history'](
            {'seed': 4}, {'seed': ('fault', 'ns', 'container', 'signature')},
            name, start, start+timedelta(days=1))
        self.assertIn('0 newly observed sampled patterns; 1 recurring sampled patterns.', text)
        _, overlapping, _ = self.report['compare_pattern_history'](
            {'seed': 4}, {'seed': ('fault', 'ns', 'container', 'signature')},
            name, start+timedelta(hours=1), start+timedelta(days=1,hours=1))
        self.assertIn('not comparable', overlapping)
        self.report['upsert_report'](name, '', {'window_start': start.isoformat(),
            'window_end': (start+timedelta(days=1)).isoformat(), 'pattern_counts': {'seed': 4},
            'pattern_history_complete': True, 'preflight': {'collection': {'ok': True}}})
        saved = json.loads(objects[name]['data']['report.json'])
        self.assertNotIn('recurrence_baseline', saved)
        self.assertEqual(seed_ref, saved['previous_pattern_history_storage'])
        self.assertTrue(all(n not in objects for n in manual['pattern_history_storage']['shards']))
        self.assertEqual({'seed': 3}, self.report['load_pattern_counts']({'pattern_history_storage': seed_ref}))

    def test_missing_legacy_counts_are_not_an_empty_baseline(self):
        start = datetime(2026, 10, 22, tzinfo=ZoneInfo('UTC'))
        previous = {'window_start': (start-timedelta(days=1)).isoformat(),
                    'window_end': start.isoformat(), 'pattern_history_complete': True,
                    'preflight': {'collection': {'ok': True}}}
        self.report['kube_json'] = lambda _: {'data': {'report.json': json.dumps(previous)}}
        _, text, _ = self.report['compare_pattern_history'](
            {'key': 1}, {'key': ('fault', 'ns', 'container', 'signature')},
            'test-report', start, start+timedelta(days=1))
        self.assertIn('History could not be read', text)
        self.assertNotIn('recurring sampled patterns.', text)

    def test_fallback_does_not_invent_api_failure(self):
        text = self.report['fallback_analysis']({'ollama': {'chat_error': 'invalid response'}}, {'real_fault_candidates': [self.entry('Net::OpenTimeout')]})
        self.assertIn('Net::OpenTimeout', text)
        self.assertNotIn('Kubernetes API connectivity failures', text)
        self.assertNotIn('unreachable', text)

    def test_candidates_are_not_confirmed_high_severity_incidents(self):
        text = self.report['render_authoritative_findings']({'real_fault_candidates': [self.entry('exception')]})
        self.assertNotIn('Real problems found', text)
        self.assertNotIn('| High |', text)
        self.assertIn('Sampled log lines', text)

    def test_clamav_timeout_remains_visible(self):
        item = self.entry('Failed to read response 127.0.0.1:3200 i/o timeout')
        item.update(namespace='clamav', container='exporter')
        self.assertFalse(self.report['is_false_positive']('platform_issue_candidates', item))

    def test_mailer_timeout_remains_visible(self):
        self.assertFalse(self.report['is_false_positive']('real_fault_candidates', self.entry('ActionMailer::MailDeliveryJob Net::OpenTimeout')))

    def test_previous_hour_report_is_not_a_daily_baseline(self):
        start = datetime(2026, 10, 29, 5, tzinfo=ZoneInfo('Europe/Prague'))
        old = {'window_start': (start-timedelta(hours=1)).isoformat(), 'window_end': start.isoformat(), 'pattern_counts': {}}
        self.report['kube_json'] = lambda _: {'data': {'report.json': json.dumps(old)}}
        _, text, _ = self.report['pattern_history']({'real_fault_candidates': [self.entry('timeout')]}, 'report', start, start+timedelta(days=1))
        self.assertIn('not comparable', text)
        self.assertNotIn('newly observed:', text)

    def test_equal_complete_adjacent_window_identifies_recurring(self):
        start = datetime(2026, 10, 29, 5, tzinfo=ZoneInfo('Europe/Prague'))
        entries = {'real_fault_candidates': [self.entry('timeout')]}
        self.report['kube_json'] = lambda _: {'data': {}}
        counts, _, _ = self.report['pattern_history'](entries, 'report', start, start+timedelta(days=1))
        old = {'window_start': (start-timedelta(days=1)).isoformat(), 'window_end': start.isoformat(), 'pattern_counts': counts, 'pattern_history_complete': True, 'preflight': {'collection': {'ok': True}}}
        self.report['kube_json'] = lambda _: {'data': {'report.json': json.dumps(old)}}
        _, text, _ = self.report['pattern_history'](entries, 'report', start, start+timedelta(days=1))
        self.assertIn('recurring:', text)
        self.assertNotIn('newly observed:', text)


if __name__ == '__main__':
    unittest.main()
