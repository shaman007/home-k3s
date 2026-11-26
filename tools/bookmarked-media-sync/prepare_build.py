#!/usr/bin/env python3
"""Render an inert, signed build request using the existing Podman builder."""
import argparse
import base64
import copy
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile

import yaml

ROOT = Path(__file__).resolve().parents[2]


def render(source):
    """Package only the reviewed image and build script, never registry credentials."""
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode='w') as target:
        for name in ['build.sh', 'bookmarked-media-sync/Dockerfile']:
            data = (source / name).read_bytes()
            entry = tarfile.TarInfo(name)
            entry.size = len(data)
            entry.mode = 0o755 if name == 'build.sh' else 0o644
            target.addfile(entry, io.BytesIO(data))
    payload = gzip.compress(archive.getvalue(), mtime=0)
    digest = hashlib.sha256(payload).hexdigest()
    name = 'bookmarked-media-build-' + digest[:16]
    base = yaml.safe_load((ROOT / 'image-builder/cron-job-podman-builder.yaml').read_text())
    spec = copy.deepcopy(base['spec']['jobTemplate']['spec'])
    spec.update(backoffLimit=0, activeDeadlineSeconds=1800)
    pod = spec['template']['spec']
    pod['initContainers'][0] = {
        'name':'unpack-source',
        'image':'harbor.andreybondarenko.com/dockerhub/library/busybox:1.38.0-musl',
        'command':['sh','-ec', 'mkdir -p /workspace/Dockerfiles; printf %s ' + base64.b64encode(payload).decode() + ' | base64 -d | tar -xz -C /workspace/Dockerfiles'],
        'volumeMounts':[{'name':'workspace','mountPath':'/workspace'}],
        'resources':{'requests':{'cpu':'10m','memory':'32Mi'},'limits':{'memory':'128Mi'}},
        'securityContext':{'runAsUser':0,'allowPrivilegeEscalation':False,
                           'readOnlyRootFilesystem':True,'capabilities':{'drop':['ALL']},
                           'seccompProfile':{'type':'RuntimeDefault'}},
    }
    for init in pod['initContainers']:
        if init['name'] == 'copy-cosign':
            init['resources']['limits']['memory'] = '256Mi'
    build = pod['containers'][0]
    build['env'].append({'name':'TAG','value':'src-' + digest[:16]})
    build['args'][0] = build['args'][0].replace('exec ./build.sh', 'exec ./build.sh bookmarked-media-sync')
    return {'apiVersion':'batch/v1','kind':'Job','metadata':{'name':name,'namespace':'image-builder',
            'annotations':{'source-sha256':digest}},'spec':spec}



def main():
    """Write a reviewable request without creating or publishing anything."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT.parent / 'Dockerfiles')
    args = parser.parse_args()
    print(json.dumps(render(args.source), indent=2))


if __name__ == '__main__':
    main()
