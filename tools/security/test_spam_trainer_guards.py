#!/usr/bin/env python3
"""Run the real trainer on disposable mail; a local curl stub never contacts Rspamd."""
import tempfile
from pathlib import Path

import yaml
from probe_commands import run_command

ROOT = Path(__file__).resolve().parents[2]


def main():
    """Verify Dovecot user switching, learning success and failure retention safely."""
    manifest = yaml.safe_load((ROOT / 'mail/cron-job-rspamd-spam-trainer.yaml').read_text())
    container = manifest['spec']['jobTemplate']['spec']['template']['spec']['containers'][0]
    config = yaml.safe_load((ROOT / 'mail/config-map-rspamd-spam-trainer.yaml').read_text())['data']
    with tempfile.TemporaryDirectory(prefix='spam-trainer-guards-') as directory:
        work = Path(directory)
        (work / 'dovecot.conf').write_text(config['dovecot.conf'])
        (work / 'train-spam.sh').write_text(config['train-spam.sh'])
        # Stub only the remote learn response, retaining real master/auth/doveadm/mbox work.
        (work / 'curl').write_text('#!/bin/sh\ncat /tmp/message.eml > /tmp/learned.eml\nexit "${LEARN_EXIT:-0}"\n')
        (work / 'curl').chmod(0o755)
        for result in (0, 22):
            script = '''set -eu
mkdir -p /var/mail/boxes/spam
chown -R 1000:1000 /var/mail
cat > /var/mail/spam <<'MAIL'
From fixture@example.invalid Tue Nov 17 10:00:00 2026
From: fixture@example.invalid
To: spam@example.invalid
Subject: disposable capability fixture
Message-ID: <capability-fixture@example.invalid>

Synthetic spam fixture.

MAIL
chown 1000:1000 /var/mail/spam
set +e
/bin/sh /fixture/train-spam.sh
result=$?
set -e
test "$result" = "$LEARN_EXIT"
grep -q 'Synthetic spam fixture' /tmp/learned.eml
dovecot
trap 'dovecot stop >/dev/null 2>&1 || true' EXIT
doveadm search -u spam mailbox INBOX all > /tmp/remaining
if [ "$LEARN_EXIT" = 0 ]; then test ! -s /tmp/remaining; else test -s /tmp/remaining; fi
'''
            cidfile = work / ('container-' + str(result))
            args = ['podman', 'run', '--rm', '--cidfile=' + str(cidfile), '--network=none', '--user=0:0',
                    '--cap-drop=ALL', '--security-opt=no-new-privileges',
                    '--read-only', '--read-only-tmpfs=false']
            args += ['--cap-add=' + cap for cap in container['securityContext']['capabilities']['add']]
            for mount in ('/run/dovecot', '/var/lib/dovecot', '/tmp', '/var/mail'):
                args += ['--tmpfs', mount + ':rw,mode=0777']
            args += ['-v', str(work) + ':/fixture:ro,Z', '-v',
                     str(work / 'dovecot.conf') + ':/etc/dovecot/dovecot.conf:ro,Z',
                     '-v', str(work / 'curl') + ':/usr/local/bin/curl:ro,Z',
                     '-e', 'LEARN_EXIT=' + str(result), '--entrypoint=/bin/sh',
                     container['image'], '-ec', script]
            try:
                completed = run_command(args, capture_output=True, text=True, timeout=90, check=False)
                if completed.returncode:
                    raise AssertionError(completed.stdout[-3000:] + completed.stderr[-3000:])
            finally:
                if cidfile.exists():
                    cid = cidfile.read_text().strip()
                    if cid:
                        run_command(['podman', 'rm', '-f', cid], capture_output=True,
                                    text=True, timeout=30, check=False)
    print('PASS: real Dovecot trainer learns/expunges fixture on success and retains it on failed learning; no production data or network')


if __name__ == '__main__':
    main()
