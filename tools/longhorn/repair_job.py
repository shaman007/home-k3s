#!/usr/bin/env python3
"""Run a one-off trim repair; shorten retention only after verified success."""

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.security.probe_commands import CommandTimeout, run_command, user_executable

NAMESPACE = 'longhorn-system'
SUCCESS_TTL = 60
DIAGNOSTIC_TTL = 86400
CRONJOBS = ('trim-daily-a', 'trim-daily-b', 'trim-daily-c')


def job_manifest(cronjob, name):
    """Copy workload configuration without CronJob/Argo ownership metadata."""
    template = cronjob['spec']['jobTemplate']
    labels = deepcopy(template.get('metadata', {}).get('labels', {}))
    labels.pop('app.kubernetes.io/instance', None)
    labels['homelab.andreybondarenko.com/one-off-repair'] = 'true'
    spec = deepcopy(template['spec'])
    spec['ttlSecondsAfterFinished'] = DIAGNOSTIC_TTL
    return {
        'apiVersion': 'batch/v1', 'kind': 'Job',
        'metadata': {'name': name, 'namespace': NAMESPACE, 'labels': labels},
        'spec': spec,
    }


def terminal_state(job):
    """Only terminal conditions authorize shortening retention."""
    conditions = job.get('status', {}).get('conditions', [])
    if any(c['type'] == 'Failed' and c['status'] == 'True' for c in conditions):
        return 'failed'
    if any(c['type'] == 'Complete' and c['status'] == 'True' for c in conditions):
        return 'complete'
    return None


def retain_success(kubectl, name, uid, timeout, *, sleep=time.sleep,
                   clock=time.monotonic):
    """Wait boundedly; preserve diagnostics on failure, timeout or interruption."""
    deadline = clock() + timeout
    while clock() < deadline:
        job = kubectl('get', 'job', name, '-o', 'json')
        metadata = job['metadata']
        if metadata['uid'] != uid:
            raise RuntimeError('Job was replaced; refusing to modify its TTL')
        state = terminal_state(job)
        if state == 'failed':
            raise RuntimeError('Repair failed; keeping the diagnostic TTL of 24 hours')
        if state == 'complete':
            patch = [
                {'op': 'test', 'path': '/metadata/uid', 'value': uid},
                {'op': 'test', 'path': '/metadata/resourceVersion',
                 'value': metadata['resourceVersion']},
                {'op': 'add', 'path': '/spec/ttlSecondsAfterFinished',
                 'value': SUCCESS_TTL},
            ]
            kubectl('patch', 'job', name, '--type=json', '-p', json.dumps(patch))
            return
        sleep(min(5, max(0, deadline - clock())))
    raise RuntimeError('Repair wait timed out; keeping the diagnostic TTL of 24 hours')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('cronjob', choices=CRONJOBS)
    parser.add_argument('--context', default='admin@home-k8s')
    parser.add_argument('--timeout', type=int, default=3600,
                        help='Seconds to wait for completion (default: 3600)')
    parser.add_argument('--execute', action='store_true',
                        help='Create the Job and wait; otherwise print a plan only')
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        parser.error('--timeout must be positive')
    name = args.cronjob + '-repair-' + datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')
    if not args.execute:
        print(json.dumps({'context': args.context, 'namespace': NAMESPACE,
                          'cronjob': args.cronjob, 'job': name,
                          'success_ttl_seconds': SUCCESS_TTL,
                          'diagnostic_ttl_seconds': DIAGNOSTIC_TTL,
                          'execute': False}, indent=2))
        return 0
    executable = user_executable('kubectl')

    def kubectl(verb, *arguments, body=None):
        result = run_command(
            [executable, verb, '--context', args.context, '-n', NAMESPACE,
             '--request-timeout=15s', *arguments], timeout=30,
            capture_output=True, text=True, input=body,
        )
        if result.returncode:
            raise RuntimeError(f'kubectl {verb} failed; inspect {NAMESPACE}/{name}')
        return json.loads(result.stdout) if result.stdout.strip().startswith('{') else None

    try:
        cronjob = kubectl('get', 'cronjob', args.cronjob, '-o', 'json')
        created = kubectl('create', '-f', '-', '-o', 'json',
                          body=json.dumps(job_manifest(cronjob, name)))
        print(f'Created {NAMESPACE}/{name}; waiting for Complete', flush=True)
        retain_success(kubectl, name, created['metadata']['uid'], args.timeout)
        print(f'{name}: Complete; TTL reduced to {SUCCESS_TTL}s from completion time')
        return 0
    except CommandTimeout:
        print(f'Kubernetes request timed out; inspect {NAMESPACE}/{name}; diagnostic TTL retained',
              file=sys.stderr)
        return 1
    except (RuntimeError, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('Interrupted; Job retains its diagnostic TTL of 24 hours', file=sys.stderr)
        return 130


if __name__ == '__main__':
    sys.exit(main())
