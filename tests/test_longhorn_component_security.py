import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import yaml

ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('backfill',ROOT/'tools/longhorn/backfill-component-security.py');b=importlib.util.module_from_spec(s);s.loader.exec_module(b)


class ComponentSecurityTests(unittest.TestCase):
    def setUp(self):
        self.catalog=json.loads((ROOT/'longhorn/component-security-catalog.json').read_text())
        self.entries=self.catalog['entries']
        self.policy,self.binding=yaml.safe_load_all((ROOT/'longhorn/policy-component-security.yaml').read_text())
        self.bundle=list(yaml.safe_load_all((ROOT/'longhorn/component-security-backfill.yaml').read_text()))

    def healthy(self, entry):
        doc=copy.deepcopy(entry['fixture']);doc['metadata'].update(generation=1,resourceVersion='123')
        if doc['kind']=='Deployment':
            n=doc['spec'].get('replicas',1);doc['status']={'observedGeneration':1,'updatedReplicas':n,'replicas':n,'readyReplicas':n,'availableReplicas':n}
        else:doc['status']={'observedGeneration':1,'desiredNumberScheduled':3,'updatedNumberScheduled':3,'numberReady':3,'numberAvailable':3}
        return doc

    def test_exact_scope_and_namespace_rbac(self):
        self.assertEqual({e['name'] for e in self.entries},{'csi-attacher','csi-provisioner','csi-resizer','csi-snapshotter','longhorn-ui','longhorn-csi-plugin','longhorn-global-manager'})
        rules=next(d for d in self.bundle if d['kind']=='Role')['rules']
        for rule in rules:
            self.assertEqual(rule['verbs'],['get','patch']);self.assertEqual(rule['apiGroups'],['apps'])
            expected=[e['name'] for e in self.entries if ('deployments' if e['kind']=='Deployment' else 'daemonsets') in rule['resources']]
            self.assertEqual(rule['resourceNames'],expected)
        self.assertEqual(self.policy['spec']['failurePolicy'],'Ignore')
        self.assertEqual(self.binding['spec']['matchResources']['namespaceSelector']['matchLabels'],{'kubernetes.io/metadata.name':'longhorn-system'})
        annotation=yaml.safe_load((ROOT/'argocd/application-longhorn.yaml').read_text())['metadata']['annotations']['argocd.argoproj.io/compare-options']
        self.assertEqual(annotation,'ServerSideDiff=true,IncludeMutationWebhook=true')

    def test_only_selected_container_changes(self):
        for entry in self.entries:
            doc=copy.deepcopy(entry['fixture']);b.reviewed(doc,entry)
            spec=b.expected_spec(doc,entry)
            old=doc['spec']['template']['spec']['containers']
            for i,c in enumerate(spec['template']['spec']['containers']):
                if i!=entry['index']:self.assertEqual(c,old[i])
            restored=copy.deepcopy(spec)
            if 'securityContext' in old[entry['index']]:restored['template']['spec']['containers'][entry['index']]['securityContext']=old[entry['index']]['securityContext']
            else:restored['template']['spec']['containers'][entry['index']].pop('securityContext')
            self.assertEqual(restored,doc['spec'])
            sc=spec['template']['spec']['containers'][entry['index']]['securityContext']
            self.assertEqual(sc['runAsUser'],{'longhorn-ui':499,'longhorn-global-manager':1000}.get(entry['name'],0))
            self.assertEqual(sc['runAsNonRoot'],entry['name'] in ['longhorn-ui','longhorn-global-manager'])

    def test_rollout_readiness_requires_updated_generation_and_all_replicas(self):
        for entry in self.entries:
            doc=self.healthy(entry);self.assertTrue(b.ready(doc))
            doc['metadata']['generation']=2;self.assertFalse(b.ready(doc))
            doc=self.healthy(entry)
            doc['status']['availableReplicas' if entry['kind']=='Deployment' else 'numberAvailable']=0
            self.assertFalse(b.ready(doc))

    def test_failed_preflight_writes_nothing(self):
        entries=self.entries[:2];calls=[];outer=self
        class Response:
            def __init__(self,doc):self.doc=doc
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self):return json.dumps(self.doc).encode()
        class Opener:
            def open(self,req,**kwargs):
                calls.append((req.method,req.full_url))
                entry=next(e for e in entries if '/'+e['name'] in req.full_url)
                doc=outer.healthy(entry)
                if req.method=='PATCH' and entry==entries[0]:doc['spec']=b.expected_spec(doc,entry)
                return Response(doc)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'catalog.json').write_text(json.dumps({'entries':entries}));(root/'token').write_text('synthetic-test-only')
            with patch.object(b.ssl,'create_default_context'),patch.object(b.urllib.request,'build_opener',return_value=Opener()),patch.dict(b.os.environ,{'KUBERNETES_SERVICE_HOST':'mock.invalid','KUBERNETES_SERVICE_PORT':'443'}),patch.object(b.time,'sleep'):
                with self.assertRaisesRegex(AssertionError,'absent admission mutation'):b.main(root,root)
        self.assertTrue(all('dryRun=All' in url for method,url in calls if method=='PATCH'))

    def test_failed_rollout_does_not_patch_later_targets(self):
        entries=self.entries[:2];live=[];outer=self
        class Response:
            def __init__(self,doc):self.doc=doc
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self):return json.dumps(self.doc).encode()
        class Opener:
            def open(self,req,**kwargs):
                entry=next(e for e in entries if '/'+e['name'] in req.full_url)
                doc=outer.healthy(entry)
                if req.method=='PATCH':
                    doc['spec']=b.expected_spec(doc,entry)
                    if 'dryRun=All' not in req.full_url:live.append(entry['name'])
                if entry['name'] in live:
                    doc['spec']=b.expected_spec(doc,entry);doc['metadata']['generation']=2
                return Response(doc)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'catalog.json').write_text(json.dumps({'entries':entries}));(root/'token').write_text('synthetic-test-only')
            with patch.object(b.ssl,'create_default_context'),patch.object(b.urllib.request,'build_opener',return_value=Opener()),patch.dict(b.os.environ,{'KUBERNETES_SERVICE_HOST':'mock.invalid','KUBERNETES_SERVICE_PORT':'443'}),patch.object(b.time,'sleep'),patch.object(b.time,'monotonic',side_effect=[0,301]):
                with self.assertRaisesRegex(RuntimeError,'later targets were not changed'):b.main(root,root)
        self.assertEqual(live,[entries[0]['name']])

    def test_backfill_only_patches_metadata_with_concurrency_guard(self):
        patch=b.annotation_patch(self.healthy(self.entries[0]))
        self.assertEqual(patch[0],{'op':'test','path':'/metadata/resourceVersion','value':'123'})
        self.assertTrue(all(p['path'].startswith('/metadata/') for p in patch))
        data=next(d['data'] for d in self.bundle if d['kind']=='ConfigMap')
        self.assertEqual(data['backfill.py'],(ROOT/'tools/longhorn/backfill-component-security.py').read_text())
        self.assertEqual(json.loads(data['catalog.json']),self.catalog)


if __name__=='__main__':unittest.main()
