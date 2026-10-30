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

    def test_unfamiliar_warning_is_sent_to_analyst(self):
        item = self.entry('Warning: unknown database corruption')
        filtered, _, _ = self.report['filter_false_positives']({'noise_candidates': [item]})
        self.assertIn('unknown database corruption', '\n'.join(self.report['build_log_batches'](filtered)))

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

    def test_prompt_pattern_cap_bounds_analysis(self):
        entries = [self.entry(f"distinct error {i}") for i in range(80)]
        batches = self.report['build_log_batches']({'real_fault_candidates': entries})
        self.assertEqual(50, "\n".join(batches).count('sampled_count='))

    def test_history_cap_disables_novelty_claims(self):
        start = datetime(2026, 10, 29, 5, tzinfo=ZoneInfo('Europe/Prague'))
        self.report['kube_json'] = lambda _: {'data': {}}
        counts, text, complete = self.report['pattern_history'](
            {'real_fault_candidates': [self.entry(f'distinct {i}') for i in range(2001)]},
            'report', start, start+timedelta(days=1))
        self.assertEqual(2000, len(counts))
        self.assertFalse(complete)
        self.assertIn('capped', text)
        self.assertNotIn('newly observed:', text)

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
