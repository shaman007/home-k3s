#!/usr/bin/env python3
"""Exercise native guard CEL with the pinned Kyverno CLI, never against the cluster."""
import argparse
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import yaml

ROOT=Path(__file__).resolve().parents[2]
s=importlib.util.spec_from_file_location('backfill',ROOT/'tools/security/infra_guard_backfill.py')
b=importlib.util.module_from_spec(s);s.loader.exec_module(b)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--kyverno',default='kyverno');args=parser.parse_args()
    assert '1.19.2' in subprocess.check_output([args.kyverno,'version'],text=True)
    policy=next(d for d in yaml.safe_load_all((ROOT/'infra-guards/resources.yaml').read_text()) if d['kind']=='MutatingAdmissionPolicy')
    policy['apiVersion']='policies.kyverno.io/v1';policy['kind']='MutatingPolicy';policy['spec'].pop('reinvocationPolicy')
    entries=json.loads((ROOT/'infra-guards/catalog.json').read_text())['entries'];count=0
    with tempfile.TemporaryDirectory(prefix='infra-guard-tests-') as tmp:
        tmp=Path(tmp);(tmp/'policy.yaml').write_text(yaml.safe_dump(policy))
        def evaluate(doc):
            (tmp/'resource.yaml').write_text(yaml.safe_dump(doc));out=tmp/'out.yaml'
            if out.exists():out.unlink()
            p=subprocess.run([args.kyverno,'apply',str(tmp/'policy.yaml'),'--resource',str(tmp/'resource.yaml'),'--output',str(out)],capture_output=True,text=True,timeout=30)
            assert p.returncode==0 and 'error: 0' in p.stdout,p.stdout+p.stderr
            documents=[x for x in yaml.safe_load_all(out.read_text()) if x] if out.exists() else []
            assert len(documents)<=1
            return documents[0] if documents else doc
        for e in entries:
            doc=copy.deepcopy(e['fixture']);b.reviewed(doc,e)
            for existing in [False,True]:
                original=copy.deepcopy(doc)
                if existing:
                    for t in e['targets']:
                        original['spec']['template']['spec'][t['section']][t['index']].setdefault('securityContext',{})['readOnlyRootFilesystem']=True
                result=evaluate(original)
                assert result['spec']==b.expected_spec(original,e),e['name']+': wrong mutation'
                assert evaluate(result)==result,e['name']+': not idempotent'
                b.reviewed(result,e);count+=2
            for mutation in ['namespace','name','label','account','image','command','mount','volume','count','privileged']:
                changed=copy.deepcopy(doc);pod=changed['spec']['template']['spec'];target=e['targets'][0];c=pod[target['section']][target['index']]
                if mutation=='namespace':changed['metadata']['namespace']='unreviewed'
                if mutation=='name':changed['metadata']['name']='unreviewed'
                if mutation=='label':changed['spec']['template']['metadata']['labels'][next(iter(e['labels']))]='unreviewed'
                if mutation=='account':pod['serviceAccountName']='unreviewed'
                if mutation=='image':c['image']='registry.invalid/unreviewed:1'
                if mutation=='command':c['command']=['unreviewed']
                if mutation=='mount':c.setdefault('volumeMounts',[]).append({'name':'extra','mountPath':'/unreviewed'})
                if mutation=='volume':pod.setdefault('volumes',[]).append({'name':'extra','emptyDir':{}})
                if mutation=='count':pod['containers'].append({'name':'extra','image':'registry.invalid/extra:1'})
                if mutation=='privileged':c.setdefault('securityContext',{})['privileged']=True
                assert evaluate(changed)==changed,e['name']+': mutated unreviewed '+mutation
                count+=1
            for target in e['targets']:
                for key in target.get('requiredEnv',{}):
                    changed=copy.deepcopy(doc);container=changed['spec']['template']['spec'][target['section']][target['index']]
                    next(v for v in container['env'] if v['name']==key)['value']='unreviewed'
                    assert evaluate(changed)==changed,e['name']+': ignored critical env '+key
                    count+=1
                for key in target.get('requiredFieldRefs',{}):
                    changed=copy.deepcopy(doc);container=changed['spec']['template']['spec'][target['section']][target['index']]
                    next(v for v in container['env'] if v['name']==key)['valueFrom']['fieldRef']['fieldPath']='metadata.name'
                    assert evaluate(changed)==changed;count+=1
            if e['kind']=='DaemonSet':
                changed=copy.deepcopy(doc);changed['spec']['updateStrategy']['rollingUpdate']['maxUnavailable']='100%'
                assert evaluate(changed)==changed;count+=1
    print(str(count)+' mutation/scope/idempotence checks passed')


if __name__=='__main__':main()
