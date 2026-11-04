import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('exceptions',ROOT/'tools/kyverno/generate-exceptions.py')
gen=importlib.util.module_from_spec(s);s.loader.exec_module(gen)
CAP='require-drop-all-capabilities'


class CapabilityExceptionScopeTests(unittest.TestCase):
    def setUp(self):
        catalog=json.loads((ROOT/'kyverno/exception-catalog.json').read_text())
        self.catalog={**catalog,'entries':[copy.deepcopy(next(e for e in catalog['entries'] if CAP in e['policies']))]}
        self.entry=self.catalog['entries'][0]
        self.config=self.entry['policies'][CAP]
        self.role=next(iter(self.config['initContainers']))
        self.rule=self.config['initContainers'][self.role]

    def reject(self):
        with self.assertRaises(AssertionError):list(gen.generate(self.catalog))

    def test_never_approve_a_main_container(self):
        self.config['containers'][self.role]=copy.deepcopy(self.rule)
        self.reject()

    def test_never_approve_an_ephemeral_container(self):
        self.config['ephemeralContainers']={self.role:copy.deepcopy(self.rule)}
        self.reject()

    def test_never_approve_sysadmin(self):
        self.rule['capabilities'].append('SYS_ADMIN')
        self.reject()

    def test_never_approve_a_new_image_without_root_role_review(self):
        self.rule['image']='registry.invalid/replaced:1'
        self.reject()

    def test_never_approve_duplicate_or_empty_capabilities(self):
        for capabilities in [[],['CHOWN','CHOWN']]:
            with self.subTest(capabilities=capabilities):
                self.rule['capabilities']=capabilities
                self.reject()

    def test_never_approve_privileged_requirement_on_permission_cap_exception(self):
        self.rule['requirePrivileged']=True
        self.reject()


class ApplicationCapabilityExceptionScopeTests(unittest.TestCase):
    def setUp(self):
        catalog=json.loads((ROOT/'kyverno/exception-catalog.json').read_text())
        self.entries=[copy.deepcopy(e) for e in catalog['entries'] if e.get('evidence')=='docs/capability-exception-review.md']
        self.catalog={**catalog,'entries':self.entries}

    def test_six_reviewed_workloads_generate(self):
        self.assertEqual(len(self.entries),6)
        self.assertEqual(sum(e['spec']['policyRefs'][0]['name']==CAP for e in gen.generate(self.catalog)),6)

    def test_reject_changed_application_contracts(self):
        for original in self.entries:
            for mutation in ['capability','uid','escalation','role','workload','image','kind']:
                with self.subTest(workload=original['name'],mutation=mutation):
                    entry=copy.deepcopy(original)
                    role,rule=next(iter(entry['policies'][CAP]['containers'].items()))
                    if mutation=='capability': rule['capabilities'].append('SYS_ADMIN')
                    if mutation=='uid': rule['runAsUser']+=1
                    if mutation=='escalation': rule['allowPrivilegeEscalation']=not rule['allowPrivilegeEscalation']
                    if mutation=='role': entry['policies'][CAP]['containers']['unapproved']=entry['policies'][CAP]['containers'].pop(role)
                    if mutation=='workload': entry['name']='unapproved'
                    if mutation=='image': rule['image']='registry.invalid/unreviewed:1'
                    if mutation=='kind': entry['kind']='DaemonSet'
                    with self.assertRaises((AssertionError,KeyError)):
                        list(gen.generate({**self.catalog,'entries':[entry]}))


class PrivilegedRuntimeExceptionTests(unittest.TestCase):
    def setUp(self):
        self.catalog=json.loads((ROOT/'kyverno/exception-catalog.json').read_text())
        self.entries=[e for e in self.catalog['entries'] if e['evidence']=='docs/privileged-runtime-audit-review.md']

    def test_eight_reviewed_workloads(self):
        self.assertEqual(len(self.entries),8)
        list(gen.generate({**self.catalog,'entries':self.entries}))

    def test_cannot_excuse_an_unreviewed_privileged_role(self):
        for original in self.entries:
            for mutation in ['approval','image','capabilities','seccomp','runtime-privileged']:
                with self.subTest(workload=original['name'],mutation=mutation):
                    e=copy.deepcopy(original)
                    section=next(s for s,rules in e['policies'][CAP].items() if rules)
                    name,rule=next(iter(e['policies'][CAP][section].items()))
                    if mutation=='approval':e['policies'].pop('disallow-privileged-containers')
                    if mutation=='image':rule['image']='registry.invalid/new:1'
                    if mutation=='capabilities':rule['capabilityDeclaration']={'add':['NET_ADMIN']}
                    if mutation=='seccomp':rule['seccompDeclaration']={'type':'Unconfined'}
                    if mutation=='runtime-privileged':
                        next(c for c in e['snapshot'][section] if c['name']==name)['securityContext']['privileged']=False
                    with self.assertRaises(AssertionError):list(gen.generate({**self.catalog,'entries':[e]}))


class CompanionGuardContractTests(unittest.TestCase):
    def setUp(self):
        self.catalog=json.loads((ROOT/'kyverno/exception-catalog.json').read_text())
        self.entries=[e for e in self.catalog['entries'] if e.get('requiredGuards')]

    def test_reviewed_scope_and_role_counts(self):
        self.assertEqual(len(self.entries),52)
        self.assertEqual(sum(len(v) for e in self.entries for v in e['requiredGuards'].values()),70)
        list(gen.generate({**self.catalog,'entries':self.entries}))

    def test_reject_unapproved_roles_and_unknown_guard_fields(self):
        for mutation in ['role','field']:
            e=copy.deepcopy(self.entries[0])
            section=next(iter(e['requiredGuards']))
            role=next(iter(e['requiredGuards'][section]))
            if mutation=='role':e['requiredGuards'][section]['unapproved']=e['requiredGuards'][section].pop(role)
            else:e['requiredGuards'][section][role]['unreviewedField']=True
            with self.assertRaises(AssertionError):list(gen.generate({**self.catalog,'entries':[e]}))


if __name__=='__main__':unittest.main()
