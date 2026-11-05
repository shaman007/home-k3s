#!/usr/bin/env python3
"""Write a reviewable, unsubmitted one-off Podman build Job with its exact source."""
import base64
import gzip
import hashlib
import io
from pathlib import Path
import tarfile
import yaml

root = Path(__file__).resolve().parent
buffer = io.BytesIO()
with tarfile.open(fileobj=buffer, mode='w') as archive:
    for name in ['Dockerfile', 'go.mod', 'go.sum', 'main.go']:
        payload = (root / name).read_bytes()
        entry = tarfile.TarInfo(name)
        entry.size = len(payload)
        entry.mode = 0o644
        archive.addfile(entry, io.BytesIO(payload))
source = gzip.compress(buffer.getvalue(), mtime=0)
source_hash = hashlib.sha256(source).hexdigest()
name = 'godaddy-webhook-build-' + source_hash[:12]
image = 'harbor.andreybondarenko.com/library/godaddy-webhook:' + source_hash[:12]
config = {'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':name,'namespace':'image-builder'},'binaryData':{'source.tar.gz':base64.b64encode(source).decode()}}
container = {
 'name':'build', 'image':'quay.io/podman/stable:v5.8.9',
 'workingDir':'/workspace', 'command':['/bin/bash','-ec'],
 'args':['''set -Eeuo pipefail
 tar -xzf /source/source.tar.gz -C /workspace
 printf '%s' "$HARBOR_PASSWORD" | podman login harbor.andreybondarenko.com --username "$HARBOR_USERNAME" --password-stdin
 unset HARBOR_PASSWORD
 podman build --pull=always -t "$IMAGE" .
 podman push --digestfile=/tmp/image.digest "$IMAGE"
 cat /tmp/image.digest
'''],
 'securityContext':{'privileged':True},
 'env':[
  {'name':'HARBOR_USERNAME','valueFrom':{'secretKeyRef':{'name':'podman-builder-harbor','key':'username'}}},
  {'name':'HARBOR_PASSWORD','valueFrom':{'secretKeyRef':{'name':'podman-builder-harbor','key':'password'}}},
  {'name':'IMAGE','value':image}, {'name':'STORAGE_DRIVER','value':'overlay'}],
 'resources':{'requests':{'cpu':'500m','memory':'1Gi'},'limits':{'memory':'4Gi'}},
 'volumeMounts':[{'name':'source','mountPath':'/source','readOnly':True},{'name':'workspace','mountPath':'/workspace'},{'name':'storage','mountPath':'/var/lib/containers'}]}
job = {'apiVersion':'batch/v1','kind':'Job','metadata':{'name':name,'namespace':'image-builder'},'spec':{
 'backoffLimit':0,'activeDeadlineSeconds':1800,'ttlSecondsAfterFinished':86400,
 'template':{'metadata':{'labels':{'app.kubernetes.io/name':'podman-builder','app.kubernetes.io/instance':'podman-builder'}},'spec':{
 'automountServiceAccountToken':False,'restartPolicy':'Never','nodeSelector':{'kubernetes.io/arch':'amd64'},
 'containers':[container], 'volumes':[{'name':'source','configMap':{'name':name}},{'name':'workspace','emptyDir':{'sizeLimit':'2Gi'}},{'name':'storage','emptyDir':{'sizeLimit':'10Gi'}}]}}}}
output=Path('/tmp')/(name+'.yaml')
output.write_text(yaml.safe_dump_all([config,job],sort_keys=False,explicit_start=True))
print('Build manifest:',output)
print('Source archive SHA256:',source_hash)
print('Target image:',image)
print('No Job was submitted')
