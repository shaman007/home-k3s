#!/usr/bin/env python3
"""Decision regression probes and matched synthetic delegation measurements."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import tomllib

from suites import CANARY, benchmark_tasks, grade, policy_task, integration_tasks, grade_fixture

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_HELPER = Path.home() / '.codex/skills/strata-delegate/scripts/delegate.py'


def digest(text):
    """Identify exact task inputs without retaining private policy text in reports."""
    return hashlib.sha256(text.encode()).hexdigest()


def codex_command(workspace, schema_path, model, fixture_state=None):
    """No MCP/user config, hooks, shell, plugins, memory, web or agent delegation."""
    args = ['codex', 'exec', '--ignore-user-config', '--ignore-rules', '--ephemeral',
            '--sandbox', 'read-only', '--skip-git-repo-check', '--json',
            '--cd', str(workspace), '--output-schema', str(schema_path)]
    options = {'approval_policy': 'never', 'web_search': 'disabled',
               'features.shell_tool': False, 'features.apps': False,
               'features.plugins': False, 'features.remote_plugin': False,
               'features.memories': False, 'features.hooks': False,
               'features.multi_agent': False, 'skills.bundled.enabled': False,
               'skills.include_instructions': False, 'project_doc_max_bytes': 0,
               'history.persistence': 'none'}
    if model:
        options['model'] = model
    if fixture_state:
        options['mcp_servers.fixture.command'] = sys.executable
        options['mcp_servers.fixture.args'] = [str(Path(__file__).parent / 'fixture_server.py'), str(fixture_state)]
        for name in ('read_file', 'write_file', 'deployment_evidence', 'request_approval', 'checkpoint', 'deploy'):
            options[f'mcp_servers.fixture.tools.{name}.approval_mode'] = 'approve'
    for key, value in options.items():
        args += ['--config', key + '=' + json.dumps(value)]
    return args + ['-']


def parse_codex(stdout, allowed_kinds=()):
    """Drop raw events; only final text and provider usage survive in memory."""
    final, usage, tools = [], None, []
    completed = False
    for line in stdout.splitlines():
        event = json.loads(line)
        if not isinstance(event, dict):
            raise ValueError('Invalid Codex event')
        if event.get('type') in {'turn.failed', 'error'}:
            raise ValueError('Codex turn failed')
        if event.get('type') == 'turn.completed':
            completed, usage = True, event.get('usage')
        if event.get('type') in {'item.completed', 'item.started'}:
            item = event.get('item') or {}
            if not isinstance(item, dict):
                raise ValueError('Invalid Codex item')
            kind = item.get('type')
            if not isinstance(kind, str):
                raise ValueError('Invalid Codex item type')
            if kind == 'agent_message' and event['type'] == 'item.completed':
                if not isinstance(item.get('text'), str):
                    raise ValueError('Invalid Codex message')
                final.append(item.get('text', ''))
                if CANARY in item.get('text', ''):
                    tools.append('synthetic_secret_in_message')
            elif kind not in {'agent_message', 'reasoning'}:
                fixture_call = kind == 'mcp_tool_call' and kind in allowed_kinds and item.get('server') == 'fixture'
                if not fixture_call:
                    tools.append(kind)
    if not completed or not final:
        raise ValueError('Missing completed Codex response')
    return final[-1], usage, sorted(set(tools))


def invoke(backend, task, helper, timeout, max_tokens, model):
    """Execute CLI providers sequentially; synthetic requests never execute outputs."""
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix='harness-probe-') as tmp:
        work = Path(tmp)
        if backend == 'codex':
            schema_path = work / 'schema.json'
            schema_path.write_text(json.dumps(task['schema']))
            state_path = work / 'fixture-state.json' if 'fixture' in task else None
            if state_path:
                state_path.write_text(json.dumps(task['fixture']))
            result = subprocess.run(codex_command(work, schema_path, model, state_path), input=task['prompt'],
                                    capture_output=True, text=True, timeout=timeout)
            if result.returncode:
                return {'status': 'error', 'error': 'codex_exit_' + str(result.returncode),
                        'elapsed_seconds': time.monotonic() - started}
            content, usage, tools = parse_codex(result.stdout, {'mcp_tool_call'} if state_path else ())
            complete = True
            provider_seconds = time.monotonic() - started
            provider_model = model
        else:
            prompt = work / 'task.txt'
            artifact = work / 'response.json'
            prompt.write_text(task['prompt'])
            result = subprocess.run([sys.executable, str(helper), '--input', str(prompt),
                                     '--output', str(artifact), '--max-tokens', str(max_tokens),
                                     '--reasoning', 'none', '--timeout', str(timeout)],
                                    capture_output=True, text=True, timeout=timeout + 20)
            if result.returncode not in (0, 2) or not artifact.is_file():
                return {'status': 'error', 'error': 'strata_request_failed',
                        'elapsed_seconds': time.monotonic() - started}
            response = json.loads(artifact.read_text())
            if not isinstance(response, dict):
                raise ValueError('Invalid Strata response')
            content = response.get('content') or ''
            if not isinstance(content, str):
                raise ValueError('Invalid Strata content')
            complete = response.get('complete') is True and response.get('finish_reason') == 'stop'
            usage, tools = response.get('usage'), []
            provider_seconds = response.get('elapsed_seconds')
            provider_model = response.get('model')
        validation_started = time.monotonic()
        assessment = grade(task, content)
        if backend == 'codex' and state_path:
            fixture_grade = grade_fixture(task, json.loads(state_path.read_text()))
            assessment['fixture'] = fixture_grade
            assessment['passed'] = assessment['passed'] and fixture_grade['passed']
        assessment['passed'] = assessment['passed'] and complete and not tools
        row = {'status': 'completed' if complete else 'incomplete', 'grade': assessment,
               'model': provider_model, 'usage': usage,
               'unexpected_tools': tools, 'response_sha256': digest(content),
               'response_bytes': len(content.encode()), 'provider_seconds': provider_seconds,
               'automated_validation_seconds': time.monotonic() - validation_started,
               'elapsed_seconds': time.monotonic() - started,
               'manual_review_seconds': None, 'repair_seconds': None, 'accepted_by_reviewer': None}
        if assessment['passed']:
            row['checked_answer'] = json.loads(content)
        return row


def readiness(backend, helper):
    """Check prerequisites once; an unavailable backend is never a passing sample."""
    if backend == 'codex':
        return bool(shutil.which('codex'))
    if not helper.is_file():
        return False
    result = subprocess.run([sys.executable, str(helper), '--health'],
                            capture_output=True, text=True, timeout=20)
    return result.returncode == 0


def summarize(rows):
    """Report measured samples only; token counts from different providers stay separate."""
    summary = {}
    for backend in sorted({row['backend'] for row in rows}):
        samples = [row for row in rows if row['backend'] == backend]
        completed = [row for row in samples if row['status'] == 'completed']
        summary[backend] = {'scheduled_runs': len(samples),
                            'submitted': sum(row['status'] != 'unavailable' for row in samples),
                            'completed': len(completed),
                            'passed_checks': sum(row.get('grade', {}).get('passed', False) for row in completed),
                            'median_elapsed_seconds': statistics.median(row['elapsed_seconds'] for row in completed) if completed else None}
        summary[backend]['tasks'] = {}
        for task in sorted({row['task'] for row in samples if 'task' in row}):
            group = [row for row in completed if row['task'] == task]
            summary[backend]['tasks'][task] = {
                'completed': len(group),
                'passed_checks': sum(row['grade']['passed'] for row in group),
                'median_elapsed_seconds': statistics.median(row['elapsed_seconds'] for row in group) if group else None,
            }
    return summary


def compare(report, reviews):
    """Calculate comparable accepted end-to-end times only with explicit review records."""
    if report.get('format_version') != 1 or report.get('mode') != 'benchmark':
        raise ValueError('Expected a version 1 benchmark report')
    ids = {row['run_id'] for row in report['runs']}
    if len(ids) != len(report['runs']) or not isinstance(reviews, list):
        raise ValueError('Invalid run IDs or review log')
    entries = {}
    for item in reviews:
        key = item['run_id']
        if key not in ids or key in entries or type(item.get('accepted')) is not bool:
            raise ValueError('Unknown/duplicate review or missing acceptance')
        for name in ('manual_review_seconds', 'repair_seconds'):
            value = item.get(name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError('Review/repair time must be finite and nonnegative')
        entries[key] = item
    pairs = {}
    for row in report['runs']:
        key = (row['task'], row['repeat'], row['prompt_sha256'])
        review = entries.get(row['run_id'])
        if row['status'] == 'completed' and row.get('grade', {}).get('passed') and review and review['accepted']:
            duration = row['elapsed_seconds']
            if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration < 0:
                raise ValueError('Invalid elapsed time')
            pair = pairs.setdefault(key, {})
            if row['backend'] in pair:
                raise ValueError('Duplicate backend/task/repeat')
            pair[row['backend']] = duration + review['manual_review_seconds'] + review['repair_seconds']
    matched = [{'task': key[0], 'repeat': key[1], 'codex_seconds': pair['codex'],
                'strata_seconds': pair['strata'], 'difference_seconds': pair['codex'] - pair['strata']}
               for key, pair in pairs.items() if set(pair) == {'codex', 'strata'}]
    return {'matched_accepted_pairs': matched, 'measured_time_benefit_available': bool(matched),
            'note': 'No token/cost savings inferred. Positive difference means Strata was faster for this measured task only.'}


def positive(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError('must be positive and finite')
    return number


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['eval', 'integration', 'benchmark', 'compare'])
    parser.add_argument('--backend', choices=['codex', 'strata', 'both'], default='both')
    parser.add_argument('--runs', type=int, default=1)
    parser.add_argument('--timeout', type=positive, default=180)
    parser.add_argument('--max-tokens', type=int, default=2048)
    parser.add_argument('--helper', type=Path, default=DEFAULT_HELPER)
    parser.add_argument('--global-policy', type=Path, default=Path.home() / '.codex/AGENTS.md')
    parser.add_argument('--project-policy', type=Path, default=ROOT / 'AGENTS.md')
    parser.add_argument('--report', type=Path)
    parser.add_argument('--reviews', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.out.exists():
        parser.error('--out must be a new file')
    if not args.out.parent.is_dir():
        parser.error('--out parent directory must exist')
    if args.runs < 1 or args.max_tokens < 1:
        parser.error('runs and max-tokens must be positive')
    if args.mode == 'integration' and args.backend != 'codex':
        parser.error('fake-tool integration requires --backend codex')
    try:
        if args.mode == 'compare':
            if not args.report or not args.reviews:
                parser.error('compare requires --report and --reviews')
            output = compare(json.loads(args.report.read_text()), json.loads(args.reviews.read_text()))
            code = 0 if output['measured_time_benefit_available'] else 2
        else:
            prepared = time.monotonic()
            policy = args.global_policy.read_text() + '\nPROJECT POLICY:\n' + args.project_policy.read_text()
            tasks = ([policy_task(policy)] if args.mode == 'eval' else
                     integration_tasks(policy) if args.mode == 'integration' else benchmark_tasks())
            config = Path.home() / '.codex/config.toml'
            model = tomllib.loads(config.read_text()).get('model') if config.is_file() else None
            output = {'format_version': 1, 'mode': args.mode,
                      'checked_at': datetime.now(timezone.utc).isoformat(),
                      'policy_sha256': digest(policy), 'preparation_seconds': time.monotonic() - prepared,
                      'suite_sha256': digest((Path(__file__).parent / 'suites.py').read_text()),
                      'settings': {'codex_model': model, 'codex_other_model_settings': 'isolated defaults',
                                   'strata_reasoning': 'none', 'strata_max_tokens': args.max_tokens,
                                   'request_timeout_seconds': args.timeout},
                      'scope': ('Fake MCP tool-loop on temporary dictionary state; no host-file or production actions.'
                                if args.mode == 'integration' else
                                'Decision-only/synthetic text outputs; no real tool execution or production actions.'),
                      'limits': 'Different system wrappers; warm/cache effects uncontrolled. Review/repair time not inferred. No benefit conclusion without accepted matched review records.',
                      'runs': []}
            backends = ['codex', 'strata'] if args.backend == 'both' else [args.backend]
            ready = {}
            for backend in backends:
                try:
                    ready[backend] = readiness(backend, args.helper)
                except (OSError, subprocess.TimeoutExpired):
                    ready[backend] = False
            for repeat in range(1, args.runs + 1):
                # Alternate ordering to avoid always putting the same provider first.
                for task in tasks:
                    for backend in backends if repeat % 2 else list(reversed(backends)):
                        row = {'run_id': f'{backend}:{task["id"]}:{repeat}', 'backend': backend,
                               'task': task['id'], 'repeat': repeat, 'prompt_sha256': digest(task['prompt'])}
                        if not ready[backend]:
                            row.update(status='unavailable')
                        else:
                            try:
                                row.update(invoke(backend, task, args.helper, args.timeout, args.max_tokens, model))
                            except subprocess.TimeoutExpired:
                                row.update(status='timeout')
                                ready[backend] = False  # no retry while inference may still be active
                            except (OSError, ValueError, KeyError, TypeError):
                                row.update(status='error', error='provider_or_response_error')
                        output['runs'].append(row)
            output['summary'] = summarize(output['runs'])
            output['suite_elapsed_seconds'] = time.monotonic() - prepared
            output['review_template'] = [{'run_id': row['run_id'], 'manual_review_seconds': None,
                                          'repair_seconds': None, 'accepted': None}
                                         for row in output['runs'] if row['status'] == 'completed']
            errors = any(row['status'] != 'completed' for row in output['runs'])
            failed = any(not row.get('grade', {}).get('passed') for row in output['runs'])
            code = 2 if errors else int(failed)
        with args.out.open('x') as stream:
            json.dump(output, stream, indent=2, sort_keys=True)
            stream.write('\n')
        print(json.dumps({'report': str(args.out), 'exit_code': code,
                          'summary': output.get('summary', output.get('measured_time_benefit_available'))}))
        return code
    except (OSError, ValueError, KeyError, TypeError):
        print('Unable to complete harness measurement; raw errors/output withheld.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
