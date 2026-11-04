#!/usr/bin/env python3
"""Run only the prepull echo/sleep command, never the share-manager server."""
import json
from pathlib import Path
import subprocess
import time


def run(*args):
    p = subprocess.run(['podman', *args], text=True, capture_output=True, timeout=90)
    assert p.returncode == 0, p.stderr[-2000:]
    return p.stdout.strip()


def main():
    root = Path(__file__).resolve().parents[2]
    entry = next(e for e in json.loads((root/'longhorn/component-security-catalog.json').read_text())['entries'] if e['name'] == 'longhorn-manager')
    assert entry['container'] == 'pre-pull-share-manager-image'
    assert entry['command'] == ['sh', '-c', 'echo share-manager image pulled && sleep infinity']
    image = 'harbor.andreybondarenko.com/dockerhub/longhornio/longhorn-share-manager@sha256:53950f78b7af38b8a943c298cd3020622191a4661a13036f69d83c154cc8690d'
    cid = run('run', '-d', '--network=none', '--user=65534:65534', '--cap-drop=ALL', '--security-opt=no-new-privileges', '--entrypoint=sh', image, *entry['command'][1:])
    try:
        time.sleep(2)
        assert run('inspect', '--format={{.State.Running}}', cid) == 'true'
        assert 'share-manager image pulled' in run('logs', cid)
        status = run('exec', cid, 'cat', '/proc/1/status')
        fields = dict(line.split(':',1) for line in status.splitlines() if ':' in line)
        assert fields['Uid'].split() == ['65534']*4
        assert fields['Gid'].split() == ['65534']*4
        assert all(int(fields[k].strip(),16)==0 for k in ['CapEff','CapPrm','CapBnd'])
        assert fields['NoNewPrivs'].strip()=='1' and fields['Seccomp'].strip()=='2'
        print('PASS: exact deployed image and echo/sleep command, UID/GID 65534, zero capabilities, NNP, default seccomp')
    finally:
        run('rm','-f',cid)


if __name__ == '__main__':
    main()
