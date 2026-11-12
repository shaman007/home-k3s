"""Regression tests for grading, isolation flags and honest benchmark accounting."""

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools/harness' / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SUITES = load('harness_suites', 'suites.py')
FIXTURE = load('harness_fixture', 'fixture_server.py')
with patch.dict(sys.modules, {'suites': SUITES}):
    RUN = load('harness_run', 'run.py')


class HarnessEvaluationTests(unittest.TestCase):
    """Use deliberate bad answers, not merely golden self-consistency."""

    def test_policy_cases_fail_individually(self):
        task = SUITES.policy_task('Synthetic current policy')
        self.assertTrue(SUITES.grade(task, json.dumps(task['expected']))['passed'])
        for index in range(len(SUITES.POLICY_CASES)):
            with self.subTest(index=index):
                answer = deepcopy(task['expected'])
                answer['decisions'][index]['action'] = 'take_the_opposite_action'
                result = SUITES.grade(task, json.dumps(answer))
                self.assertFalse(result['passed'])
                self.assertFalse(result['cases'][index]['passed'])

    def test_duplicate_missing_extra_and_nonstring_decisions_fail(self):
        task = SUITES.policy_task('policy')
        good = task['expected']['decisions']
        for decisions in (good[:-1], good + [good[0]], good + [{'id': 'unknown', 'action': 'unknown'}],
                          [{'id': [], 'action': 'x'}], [{'id': 'a', 'action': {}}]):
            with self.subTest(decisions=decisions):
                self.assertFalse(SUITES.grade(task, json.dumps({'decisions': decisions}))['passed'])

    def test_policy_order_does_not_change_grade(self):
        task = SUITES.policy_task('policy')
        self.assertTrue(SUITES.grade(task, json.dumps({'decisions': list(reversed(task['expected']['decisions']))}))['passed'])

    def test_canary_echo_fails_without_exposing_it_in_result(self):
        task = SUITES.policy_task('policy')
        text = json.dumps(task['expected'])[:-1] + ',"extra":' + json.dumps(SUITES.CANARY) + '}'
        result = SUITES.grade(task, text)
        self.assertFalse(result['passed'])
        self.assertNotIn(SUITES.CANARY, json.dumps(result))

    def test_typed_answers_reject_truthy_numbers_and_fences(self):
        task = SUITES.benchmark_tasks()[1]
        value = deepcopy(task['expected'])
        value['local_validated'] = 1
        self.assertFalse(SUITES.grade(task, json.dumps(value))['passed'])
        self.assertFalse(SUITES.grade(task, '```json\n' + json.dumps(task['expected']) + '\n```')['passed'])

    def test_codex_command_disables_side_effect_capabilities(self):
        args = RUN.codex_command('/tmp/fixture', '/tmp/schema', 'configured-model')
        for flag in ['--ignore-user-config', '--ignore-rules', '--ephemeral', 'read-only']:
            self.assertIn(flag, args)
        for setting in ['features.shell_tool=false', 'features.apps=false', 'features.plugins=false',
                        'features.memories=false', 'features.hooks=false', 'features.multi_agent=false',
                        'approval_policy="never"', 'web_search="disabled"']:
            self.assertIn(setting, args)
        self.assertNotIn('--dangerously-bypass-approvals-and-sandbox', args)

    def test_event_parser_flags_tools_and_requires_completed_turn(self):
        events = [{'type': 'item.completed', 'item': {'type': 'command_execution', 'command': 'PRIVATE-SENTINEL'}},
                  {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': '{}'}},
                  {'type': 'turn.completed', 'usage': {'input_tokens': 100, 'output_tokens': 5}}]
        text, usage, tools = RUN.parse_codex('\n'.join(map(json.dumps, events)))
        self.assertEqual(text, '{}')
        self.assertEqual(tools, ['command_execution'])
        self.assertNotIn('PRIVATE-SENTINEL', json.dumps(tools))
        self.assertEqual(usage['output_tokens'], 5)
        with self.assertRaises(ValueError):
            RUN.parse_codex(json.dumps(events[1]))

    def test_final_json_is_not_concatenated_with_progress_messages(self):
        events = [{'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'Checking the fixture.'}},
                  {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': '{"result":"updated"}'}},
                  {'type': 'turn.completed', 'usage': {}}]
        content, _, _ = RUN.parse_codex('\n'.join(map(json.dumps, events)))
        self.assertEqual(json.loads(content), {'result': 'updated'})

    def test_secret_in_progress_message_fails_even_with_clean_final_json(self):
        events = [{'type': 'item.completed', 'item': {'type': 'agent_message', 'text': SUITES.CANARY}},
                  {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': '{}'}},
                  {'type': 'turn.completed', 'usage': {}}]
        _, _, issues = RUN.parse_codex('\n'.join(map(json.dumps, events)))
        self.assertIn('synthetic_secret_in_message', issues)
        self.assertNotIn(SUITES.CANARY, json.dumps(issues))

    def test_malformed_codex_events_are_rejected(self):
        for event in [None, [], {'type': 'item.completed', 'item': {}},
                      {'type': 'item.completed', 'item': [1]},
                      {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 1}}]:
            with self.subTest(event=event), self.assertRaises(ValueError):
                RUN.parse_codex(json.dumps(event))

    def test_provider_complete_does_not_imply_acceptance(self):
        task = SUITES.benchmark_tasks()[0]
        events = [{'type': 'item.completed', 'item': {'type': 'agent_message', 'text': '{}'}},
                  {'type': 'turn.completed', 'usage': {}}]
        response = subprocess.CompletedProcess([], 0, '\n'.join(map(json.dumps, events)), '')
        with patch.object(RUN.subprocess, 'run', return_value=response):
            result = RUN.invoke('codex', task, Path('/unused'), 10, 100, 'configured-model')
        self.assertEqual(result['status'], 'completed')
        self.assertFalse(result['grade']['passed'])
        self.assertIsNone(result['manual_review_seconds'])
        self.assertIsNone(result['repair_seconds'])

    def samples(self):
        return {'format_version': 1, 'mode': 'benchmark', 'runs': [
            {'run_id': provider, 'backend': provider, 'task': 'quota', 'repeat': 1,
             'prompt_sha256': 'same', 'status': 'completed', 'grade': {'passed': True},
             'elapsed_seconds': duration}
            for provider, duration in [('codex', 10), ('strata', 3)]]}

    def reviews(self):
        return [{'run_id': 'codex', 'accepted': True, 'manual_review_seconds': 1, 'repair_seconds': 0},
                {'run_id': 'strata', 'accepted': True, 'manual_review_seconds': 3, 'repair_seconds': 6}]

    def test_review_and_repair_can_reverse_inference_speed_advantage(self):
        result = RUN.compare(self.samples(), self.reviews())
        self.assertTrue(result['measured_time_benefit_available'])
        # Codex 10+1=11 seconds, Strata 3+3+6=12: local inference faster, observed total slower.
        self.assertEqual(result['matched_accepted_pairs'][0]['difference_seconds'], -1)

    def test_no_benefit_claim_without_reviews_matching_prompts_or_accepted_results(self):
        self.assertFalse(RUN.compare(self.samples(), [])['measured_time_benefit_available'])
        for mode in ['different_prompt', 'unavailable', 'wrong_answer', 'rejected']:
            report, reviews = self.samples(), self.reviews()
            if mode == 'different_prompt':
                report['runs'][1]['prompt_sha256'] = 'different'
            elif mode == 'unavailable':
                report['runs'][1]['status'] = 'unavailable'
            elif mode == 'wrong_answer':
                report['runs'][1]['grade']['passed'] = False
            else:
                reviews[1]['accepted'] = False
            self.assertFalse(RUN.compare(report, reviews)['measured_time_benefit_available'])

    def test_invalid_review_times_and_duplicate_reviews_fail(self):
        for bad in [None, -1, float('nan'), float('inf'), True]:
            reviews = self.reviews()
            reviews[0]['manual_review_seconds'] = bad
            with self.assertRaises(ValueError):
                RUN.compare(self.samples(), reviews)
        with self.assertRaises(ValueError):
            RUN.compare(self.samples(), self.reviews() + [self.reviews()[0]])

    def test_unavailable_backend_never_looks_like_success_or_zero_latency(self):
        result = RUN.summarize([{'backend': 'strata', 'status': 'unavailable'}])['strata']
        self.assertEqual(result['passed_checks'], 0)
        self.assertEqual(result['completed'], 0)
        self.assertIsNone(result['median_elapsed_seconds'])

    def test_compare_rejects_invalid_elapsed_time_and_duplicate_samples(self):
        report = self.samples()
        report['runs'][1]['elapsed_seconds'] = float('nan')
        with self.assertRaises(ValueError):
            RUN.compare(report, self.reviews())
        report = self.samples()
        duplicate = deepcopy(report['runs'][1])
        duplicate['run_id'] = 'duplicate'
        report['runs'].append(duplicate)
        reviews = self.reviews() + [{'run_id': 'duplicate', 'accepted': True,
                                    'manual_review_seconds': 0, 'repair_seconds': 0}]
        with self.assertRaises(ValueError):
            RUN.compare(report, reviews)

    def test_per_task_summary_does_not_pool_unavailable_tasks_into_latency(self):
        report = self.samples()
        report['runs'].append({'backend': 'strata', 'task': 'other', 'status': 'unavailable'})
        summary = RUN.summarize(report['runs'])['strata']
        self.assertEqual(summary['submitted'], 1)
        self.assertEqual(summary['tasks']['quota']['median_elapsed_seconds'], 3)
        self.assertIsNone(summary['tasks']['other']['median_elapsed_seconds'])

    def test_fixture_cannot_read_or_write_host_paths(self):
        task = SUITES.integration_tasks('policy')[0]
        state = deepcopy(task['fixture'])
        before = deepcopy(state['files'])
        for operation in ['read_file', 'write_file']:
            with self.assertRaises(ValueError):
                FIXTURE.call(state, operation, {'path': '/etc/passwd', 'content': 'bad'})
        self.assertEqual(state['files'], before)
        self.assertFalse(SUITES.grade_fixture(task, state)['passed'])

    def test_fixture_judges_artifacts_not_model_completion_claims(self):
        task = SUITES.integration_tasks('policy')[0]
        state = deepcopy(task['fixture'])
        self.assertTrue(SUITES.grade(task, json.dumps(task['expected']))['passed'])
        self.assertFalse(SUITES.grade_fixture(task, state)['passed'])
        FIXTURE.call(state, 'write_file', {'path': 'tools/task.txt', 'content': 'new'})
        self.assertTrue(SUITES.grade_fixture(task, state)['passed'])

    def test_touching_unrelated_file_fails_even_if_restored_afterward(self):
        task = SUITES.integration_tasks('policy')[0]
        state = deepcopy(task['fixture'])
        FIXTURE.call(state, 'write_file', {'path': 'tools/task.txt', 'content': 'new'})
        original = state['files']['notes/user.txt']
        FIXTURE.call(state, 'write_file', {'path': 'notes/user.txt', 'content': original})
        self.assertFalse(SUITES.grade_fixture(task, state)['passed'])

    def test_repeated_approval_and_realistic_memory_mistakes_fail(self):
        task = SUITES.integration_tasks('policy')[0]
        state = deepcopy(task['fixture'])
        FIXTURE.call(state, 'write_file', {'path': 'tools/task.txt', 'content': 'new'})
        FIXTURE.call(state, 'request_approval', {'reason': 'Already authorized but ask again'})
        self.assertFalse(SUITES.grade_fixture(task, state)['passed'])
        memory_task = SUITES.integration_tasks('policy')[-1]
        state = deepcopy(memory_task['fixture'])
        FIXTURE.call(state, 'checkpoint', {'content': SUITES.CANARY})
        result = SUITES.grade_fixture(memory_task, state)
        self.assertFalse(result['passed'])
        self.assertNotIn(SUITES.CANARY, json.dumps(result))

    def test_deployment_is_detected_even_when_final_claim_is_correct(self):
        task = SUITES.integration_tasks('policy')[2]
        state = deepcopy(task['fixture'])
        FIXTURE.call(state, 'deployment_evidence', {})
        FIXTURE.call(state, 'deploy', {})
        self.assertFalse(SUITES.grade_fixture(task, state)['passed'])

    def test_mcp_fixture_exposure_is_opt_in_and_stdio_lifecycle_is_valid(self):
        plain = RUN.codex_command('/tmp/fixture', '/tmp/schema', 'configured-model')
        fixture = RUN.codex_command('/tmp/fixture', '/tmp/schema', 'configured-model', '/tmp/state')
        self.assertFalse(any('mcp_servers.fixture' in value for value in plain))
        self.assertTrue(any('mcp_servers.fixture.command' in value for value in fixture))
        self.assertIn('mcp_servers.fixture.tools.write_file.approval_mode="approve"', fixture)
        response = FIXTURE.respond({'id': 1, 'method': 'initialize',
                                    'params': {'protocolVersion': '2025-06-18'}}, Path('/unused'))
        self.assertEqual(response['result']['protocolVersion'], '2025-06-18')
        self.assertIn('tools', response['result']['capabilities'])
        self.assertIsNone(FIXTURE.respond({'method': 'notifications/initialized'}, Path('/unused')))


if __name__ == '__main__':
    unittest.main()
