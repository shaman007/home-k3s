#!/usr/bin/env python3
"""Generate the reviewed native component mutation and guarded rollout hook."""
import argparse
import importlib.util
import json
from pathlib import Path
import yaml
ROOT = Path(__file__).resolve().parents[2]
s = importlib.util.spec_from_file_location('backfill', ROOT/'tools/longhorn/backfill-component-security.py')
b = importlib.util.module_from_spec(s); s.loader.exec_module(b)


class Dumper(yaml.SafeDumper): pass
Dumper.add_representer(str, lambda d,v:d.represent_scalar('tag:yaml.org,2002:str',v,style='|' if '\n' in v else None))


def generate(catalog):
    entries = catalog['entries']; branches = []
    for e in entries:
        c = f'p.containers[{e["index"]}]'
        parts = [f'object.kind == {json.dumps(e["kind"])}', f'object.metadata.name == {json.dumps(e["name"])}',
                 f'object.spec.template.metadata.?labels.orValue({{}})["app"] == {json.dumps(e["name"])}',
                 f'p.?serviceAccountName.orValue("default") == {json.dumps(e["serviceAccount"])}',
                 f'p.containers.size() == {e["count"]}', 'p.?initContainers.orValue([]).size() == 0',
                 f'{c}.name == {json.dumps(e["container"])}', f'{c}.image == {json.dumps(e["image"])}',
                 f'{c}.?args.orValue([]) == {json.dumps(e["args"])}', f'{c}.?command.orValue([]) == {json.dumps(e["command"])}']
        if e['kind'] == 'DaemonSet':
            for index in [0,2]:
                companion = e['fixture']['spec']['template']['spec']['containers'][index]
                parts += [f'p.containers[{index}].name == {json.dumps(companion["name"])}',
                          f'p.containers[{index}].image == {json.dumps(companion["image"])}',
                          f'p.containers[{index}].?securityContext.?privileged.orValue(false) == true']
        branches.append('('+' &&\n '.join(parts)+')')
    expression = '[object.spec.template.spec].exists(p,\n'+' ||\n'.join(branches)+'\n)'
    path = '"/spec/template/spec/containers/" + string(variables.index) + "/securityContext"'
    mutation = f'(!has(object.spec.template.spec.containers[variables.index].securityContext) ? [JSONPatch{{op: "add", path: {path}, value: {{}}}}] : []) + [\n'
    for key,value in b.security(entries[0]).items():
        val = ('variables.uid' if key=='runAsUser' else 'variables.gid' if key=='runAsGroup' else 'variables.nonroot' if key=='runAsNonRoot' else json.dumps(value))
        mutation += f'JSONPatch{{op: "add", path: {path} + "/{key}", value: {val}}},\n'
    mutation = mutation.rstrip(',\n')+'\n]'
    rules = [{'apiGroups':['apps'],'apiVersions':['v1'],'operations':['CREATE','UPDATE'],'resources':[resource],
              'resourceNames':[e['name'] for e in entries if e['kind']==kind]} for kind,resource in [('Deployment','deployments'),('DaemonSet','daemonsets')]]
    name = 'longhorn-component-security'
    policy = {'apiVersion':'admissionregistration.k8s.io/v1','kind':'MutatingAdmissionPolicy','metadata':{'name':name,'annotations':{'argocd.argoproj.io/sync-wave':'-2'}},'spec':{
        'failurePolicy':'Ignore','reinvocationPolicy':'IfNeeded','matchConstraints':{'resourceRules':rules},
        'matchConditions':[{'name':'namespace','expression':'request.namespace == "longhorn-system"'},{'name':'reviewed-contract','expression':expression}],
        'variables':[{'name':'index','expression':'object.kind == "DaemonSet" ? 1 : 0'},
                     {'name':'nonroot','expression':'object.metadata.name == "longhorn-ui"'},
                     {'name':'uid','expression':'variables.nonroot ? 499 : 0'}, {'name':'gid','expression':'variables.nonroot ? 486 : 0'}],
        'mutations':[{'patchType':'JSONPatch','jsonPatch':{'expression':mutation}}]}}
    binding = {'apiVersion':'admissionregistration.k8s.io/v1','kind':'MutatingAdmissionPolicyBinding','metadata':{'name':name,'annotations':{'argocd.argoproj.io/sync-wave':'-1'}},'spec':{'policyName':name,'matchResources':{'namespaceSelector':{'matchLabels':{'kubernetes.io/metadata.name':'longhorn-system'}}}}}
    meta = lambda:{'name':'component-security-backfill','namespace':'longhorn-system','annotations':{'argocd.argoproj.io/sync-wave':'-1'}}
    sa = {'apiVersion':'v1','kind':'ServiceAccount','metadata':meta()}
    role = {'apiVersion':'rbac.authorization.k8s.io/v1','kind':'Role','metadata':meta(),'rules':[{**r,'verbs':['get','patch']} for r in rules]}
    for r in role['rules']: r.pop('operations'); r.pop('apiVersions')
    rb = {'apiVersion':'rbac.authorization.k8s.io/v1','kind':'RoleBinding','metadata':meta(),'roleRef':{'apiGroup':'rbac.authorization.k8s.io','kind':'Role','name':'component-security-backfill'},'subjects':[{'kind':'ServiceAccount','name':'component-security-backfill','namespace':'longhorn-system'}]}
    cm = {'apiVersion':'v1','kind':'ConfigMap','metadata':meta(),'data':{'catalog.json':json.dumps(catalog),'backfill.py':(ROOT/'tools/longhorn/backfill-component-security.py').read_text()}}
    job = {'apiVersion':'batch/v1','kind':'Job','metadata':{'generateName':'component-security-backfill-','namespace':'longhorn-system','annotations':{'argocd.argoproj.io/hook':'PostSync','argocd.argoproj.io/hook-delete-policy':'HookSucceeded'}},'spec':{'backoffLimit':0,'activeDeadlineSeconds':2100,'template':{'metadata':{'labels':{'app':'component-security-backfill'}},'spec':{'serviceAccountName':'component-security-backfill','restartPolicy':'Never','securityContext':{'runAsNonRoot':True,'runAsUser':1000,'runAsGroup':1000,'seccompProfile':{'type':'RuntimeDefault'}},'containers':[{'name':'backfill','image':'harbor.andreybondarenko.com/dockerhub/library/python:3.15-alpine','command':['python3','/config/backfill.py'],'env':[{'name':'PYTHONDONTWRITEBYTECODE','value':'1'}],'securityContext':{'allowPrivilegeEscalation':False,'readOnlyRootFilesystem':True,'capabilities':{'drop':['ALL']}},'resources':{'requests':{'cpu':'10m','memory':'32Mi'},'limits':{'memory':'128Mi'}},'volumeMounts':[{'name':'config','mountPath':'/config','readOnly':True}]}],'volumes':[{'name':'config','configMap':{'name':'component-security-backfill'}}]}}}}
    return {'longhorn/policy-component-security.yaml':[policy,binding],'longhorn/component-security-backfill.yaml':[sa,role,rb,cm,job]}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
    catalog=json.loads((ROOT/'longhorn/component-security-catalog.json').read_text())
    for filename,docs in generate(catalog).items():
        text='# Generated by tools/longhorn/generate-component-security.py.\n'+yaml.dump_all(docs,Dumper=Dumper,sort_keys=False,width=110)
        path=ROOT/filename
        if args.check:
            assert path.read_text()==text, filename+' is stale'
        else:path.write_text(text)
    print('Component security manifests are current')


if __name__=='__main__':main()
