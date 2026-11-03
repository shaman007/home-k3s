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


if __name__=='__main__':unittest.main()
