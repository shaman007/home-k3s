"""Check workload identity, image scope, and guards for reviewed capability exceptions."""

import copy
import importlib.util
import json
from pathlib import Path
import unittest
import re

ROOT = Path(__file__).resolve().parents[1]
s = importlib.util.spec_from_file_location(
    "exceptions", ROOT / "tools/kyverno/generate_exceptions.py"
)
gen = importlib.util.module_from_spec(s)
s.loader.exec_module(gen)
CAP = "require-drop-all-capabilities"


class CapabilityExceptionScopeTests(unittest.TestCase):
    """Reject capability exceptions outside the reviewed helper-container contract."""

    def setUp(self):
        catalog = json.loads((ROOT / "kyverno/exception-catalog.json").read_text())
        self.catalog = {
            **catalog,
            "entries": [copy.deepcopy(next(e for e in catalog["entries"] if CAP in e["policies"]))],
        }
        self.entry = self.catalog["entries"][0]
        self.config = self.entry["policies"][CAP]
        self.role = next(iter(self.config["initContainers"]))
        self.rule = self.config["initContainers"][self.role]

    def reject(self):
        """Require an invalid capability contract to fail review."""
        with self.assertRaises(AssertionError):
            list(gen.generate(self.catalog))

    def test_never_approve_a_main_container(self):
        """Reject capability exceptions for main containers."""
        self.config["containers"][self.role] = copy.deepcopy(self.rule)
        self.reject()

    def test_never_approve_an_ephemeral_container(self):
        """Reject capability exceptions for ephemeral containers."""
        self.config["ephemeralContainers"] = {self.role: copy.deepcopy(self.rule)}
        self.reject()

    def test_never_approve_sysadmin(self):
        """Reject SYS_ADMIN even on an otherwise reviewed init container."""
        self.rule["capabilities"].append("SYS_ADMIN")
        self.reject()

    def test_never_approve_a_new_image_without_root_role_review(self):
        """Require renewed root-role review when an init-container image changes."""
        self.rule["image"] = "registry.invalid/replaced:1"
        self.reject()

    def test_never_approve_duplicate_or_empty_capabilities(self):
        """Reject empty capability lists and duplicate capability grants."""
        for capabilities in [[], ["CHOWN", "CHOWN"]]:
            with self.subTest(capabilities=capabilities):
                self.rule["capabilities"] = capabilities
                self.reject()

    def test_never_approve_privileged_requirement_on_permission_cap_exception(self):
        """Reject privileged mode on a permission-only capability exception."""
        self.rule["requirePrivileged"] = True
        self.reject()


class ApplicationCapabilityExceptionScopeTests(unittest.TestCase):
    """Restrict application capability exceptions to reviewed workload identities."""

    def setUp(self):
        catalog = json.loads((ROOT / "kyverno/exception-catalog.json").read_text())
        self.entries = [
            copy.deepcopy(e)
            for e in catalog["entries"]
            if e.get("evidence") == "docs/capability-exception-review.md"
        ]
        self.catalog = {**catalog, "entries": self.entries}

    def test_six_reviewed_workloads_generate(self):
        """Generate capability exceptions for exactly the six reviewed applications."""
        self.assertEqual(len(self.entries), 6)
        self.assertEqual(
            sum(e["spec"]["policyRefs"][0]["name"] == CAP for e in gen.generate(self.catalog)), 6
        )

    def test_reject_changed_application_contracts(self):
        """Reject application exceptions after a reviewed security contract changes."""
        for original in self.entries:
            for mutation in [
                "capability",
                "uid",
                "escalation",
                "role",
                "workload",
                "image",
                "kind",
            ]:
                with self.subTest(workload=original["name"], mutation=mutation):
                    entry = copy.deepcopy(original)
                    role, rule = next(iter(entry["policies"][CAP]["containers"].items()))
                    if mutation == "capability":
                        rule["capabilities"].append("SYS_ADMIN")
                    if mutation == "uid":
                        rule["runAsUser"] += 1
                    if mutation == "escalation":
                        rule["allowPrivilegeEscalation"] = not rule["allowPrivilegeEscalation"]
                    if mutation == "role":
                        entry["policies"][CAP]["containers"]["unapproved"] = entry["policies"][CAP][
                            "containers"
                        ].pop(role)
                    if mutation == "workload":
                        entry["name"] = "unapproved"
                    if mutation == "image":
                        rule["image"] = "registry.invalid/unreviewed:1"
                    if mutation == "kind":
                        entry["kind"] = "DaemonSet"
                    with self.assertRaises((AssertionError, KeyError)):
                        list(gen.generate({**self.catalog, "entries": [entry]}))


class PrivilegedRuntimeExceptionTests(unittest.TestCase):
    """Reject privileged runtime exceptions for unreviewed workload roles."""

    def setUp(self):
        self.catalog = json.loads((ROOT / "kyverno/exception-catalog.json").read_text())
        self.entries = [
            e
            for e in self.catalog["entries"]
            if e["evidence"] == "docs/privileged-runtime-audit-review.md"
        ]

    def test_eight_reviewed_workloads(self):
        """Generate privileged-runtime exceptions for exactly eight reviewed workloads."""
        self.assertEqual(len(self.entries), 8)
        list(gen.generate({**self.catalog, "entries": self.entries}))

    def test_cannot_excuse_an_unreviewed_privileged_role(self):
        """Reject privileged-role exceptions after approval or runtime constraints change."""
        for original in self.entries:
            for mutation in ["approval", "image", "capabilities", "seccomp", "runtime-privileged"]:
                with self.subTest(workload=original["name"], mutation=mutation):
                    e = copy.deepcopy(original)
                    section = next(s for s, rules in e["policies"][CAP].items() if rules)
                    name, rule = next(iter(e["policies"][CAP][section].items()))
                    if mutation == "approval":
                        e["policies"].pop("disallow-privileged-containers")
                    if mutation == "image":
                        rule["image"] = "registry.invalid/new:1"
                    if mutation == "capabilities":
                        rule["capabilityDeclaration"] = {"add": ["NET_ADMIN"]}
                    if mutation == "seccomp":
                        rule["seccompDeclaration"] = {"type": "Unconfined"}
                    if mutation == "runtime-privileged":
                        next(c for c in e["snapshot"][section] if c["name"] == name)[
                            "securityContext"
                        ]["privileged"] = False
                    with self.assertRaises(AssertionError):
                        list(gen.generate({**self.catalog, "entries": [e]}))


class CompanionGuardContractTests(unittest.TestCase):
    """Require reviewed companion roles and recognized security guard fields."""

    def setUp(self):
        self.catalog = json.loads((ROOT / "kyverno/exception-catalog.json").read_text())
        self.entries = [e for e in self.catalog["entries"] if e.get("requiredGuards")]

    def test_reviewed_scope_and_role_counts(self):
        """Verify reviewed scope and role counts."""
        self.assertEqual(len(self.entries), 53)
        self.assertEqual(
            sum(len(v) for e in self.entries for v in e["requiredGuards"].values()), 73
        )
        list(gen.generate({**self.catalog, "entries": self.entries}))

    def test_reject_unapproved_roles_and_unknown_guard_fields(self):
        """Reject unapproved companion roles and unknown security guard fields."""
        for mutation in ["role", "field"]:
            e = copy.deepcopy(self.entries[0])
            section = next(iter(e["requiredGuards"]))
            role = next(iter(e["requiredGuards"][section]))
            if mutation == "role":
                e["requiredGuards"][section]["unapproved"] = e["requiredGuards"][section].pop(role)
            else:
                e["requiredGuards"][section][role]["unreviewedField"] = True
            with self.assertRaises(AssertionError):
                list(gen.generate({**self.catalog, "entries": [e]}))

    def test_reviewed_gpu_companions_are_constraints_not_exception_roles(self):
        """Keep reviewed GPU companion constraints outside the exception-role inventory."""
        entries = [e for e in self.entries if e.get("reviewedCompanions")]
        self.assertEqual(len(entries), 2)
        for e in entries:
            helper = "config-manager-init"
            self.assertTrue(e["requiredGuards"]["initContainers"][helper]["runAsNonRoot"])
            self.assertEqual(
                e["requiredGuards"]["initContainers"][helper]["capabilities"], {"drop": ["ALL"]}
            )
            self.assertFalse(
                e["requiredGuards"]["initContainers"][helper]["allowPrivilegeEscalation"]
            )
            for policy in e["policies"].values():
                self.assertNotIn(helper, policy.get("initContainers", {}))
            bad = copy.deepcopy(e)
            bad["reviewedCompanions"]["initContainers"][helper]["image"] = (
                "registry.invalid/unapproved:1"
            )
            with self.assertRaises(AssertionError):
                list(gen.generate({**self.catalog, "entries": [bad]}))


class ImageRepositoryScopeTests(unittest.TestCase):
    """Distinguish reviewed image repositories from substituted or implicit references."""

    def test_tags_and_digests_do_not_change_repository(self):
        """Verify tags and digests do not change repository."""
        repository = "registry.example:5000/team/app"
        for suffix in ["", ":v1", "@sha256:" + "a" * 64, ":v2@sha256:" + "b" * 64]:
            self.assertEqual(gen.image_repository(repository + suffix), repository)

    def test_matcher_rejects_repository_substitution(self):
        """Verify matcher rejects repository substitution."""

        expression = gen.image_expression("registry.example:5000/team/app:v1")
        pattern = json.loads(expression[len("c.image.matches(") : -1])
        for image in [
            "registry.example:5000/team/app:v2",
            "registry.example:5000/team/app@sha256:" + "a" * 64,
        ]:
            self.assertIsNotNone(re.fullmatch(pattern, image))
        for image in [
            "registryXexample:5000/team/app:v2",
            "registry.example:5001/team/app:v2",
            "registry.example:5000/team/app-evil:v2",
            "registry.example:5000/team/app/evil:v2",
        ]:
            self.assertIsNone(re.fullmatch(pattern, image))

    def test_implicit_registry_is_not_a_reviewed_reference(self):
        """Verify implicit registry is not a reviewed reference."""
        with self.assertRaises(AssertionError):
            gen.image_repository("busybox:v1")


if __name__ == "__main__":
    unittest.main()


class SpeakerRootCapabilityExceptionTests(unittest.TestCase):
    """Limit the speaker exception to the reviewed root and raw-network contract."""

    def test_only_exact_reviewed_root_raw_l2_contract_generates(self):
        """Limit speaker exceptions to the exact reviewed root and raw-network L2 contract."""
        catalog = json.loads((ROOT / "kyverno/exception-catalog.json").read_text())
        original = next(e for e in catalog["entries"] if e["name"] == "metallb-speaker")
        list(gen.generate({**catalog, "entries": [original]}))
        for mutation in [
            "kind",
            "namespace",
            "name",
            "account",
            "image",
            "capability",
            "uid",
            "escalation",
            "guard",
            "policy",
        ]:
            e = copy.deepcopy(original)
            rule = e["policies"][CAP]["containers"]["speaker"]
            if mutation == "kind":
                e["kind"] = "Deployment"
            if mutation == "namespace":
                e["namespace"] = "other"
            if mutation == "name":
                e["name"] = "other"
            if mutation == "account":
                e["serviceAccount"] = "other"
            if mutation == "image":
                rule["image"] = "registry.invalid/speaker:1"
            if mutation == "capability":
                rule["capabilities"].append("NET_ADMIN")
            if mutation == "uid":
                rule["runAsUser"] = 1000
            if mutation == "escalation":
                rule["allowPrivilegeEscalation"] = True
            if mutation == "guard":
                e["requiredGuards"]["containers"]["speaker"].pop("readOnlyRootFilesystem")
            if mutation == "policy":
                e["policies"].pop(CAP)
            with self.subTest(mutation=mutation), self.assertRaises((AssertionError, KeyError)):
                list(gen.generate({**catalog, "entries": [e]}))
