"""Keep negative CLI resources noncompliant with their target policy."""

import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
import tempfile
import copy
import json
from collections import Counter

import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "audit_cases", ROOT / "tools/kyverno/test_audit_policies.py"
)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class AuditFixtureTests(unittest.TestCase):
    """Preserve policy assertions and applicable exceptions across generated test shards."""

    def test_nonroot_repair_clears_pod_root_declaration(self):
        """A repaired speaker must satisfy pod and container nonroot requirements."""
        resource = {
            "spec": {
                "securityContext": {
                    "runAsNonRoot": False,
                    "runAsUser": 0,
                    "seccompProfile": {"type": "RuntimeDefault"},
                },
                "containers": [
                    {"name": "speaker", "securityContext": {"runAsNonRoot": False, "runAsUser": 0}}
                ],
            }
        }
        audit.repair_containers(resource, "require-run-as-nonroot")
        for context in (
            resource["spec"]["securityContext"],
            resource["spec"]["containers"][0]["securityContext"],
        ):
            self.assertTrue(context["runAsNonRoot"])
            self.assertEqual(context["runAsUser"], 1000)
        self.assertEqual(
            resource["spec"]["securityContext"]["seccompProfile"], {"type": "RuntimeDefault"}
        )

    def test_admission_normalization_does_not_touch_other_workloads(self):
        """Verify admission normalization does not touch other workloads."""

        for kind, namespace, name in [
            ("Deployment", "longhorn-system", "longhorn-manager"),
            ("DaemonSet", "other", "longhorn-manager"),
            ("DaemonSet", "longhorn-system", "other"),
        ]:
            resource = {"kind": kind, "metadata": {"namespace": namespace, "name": name}}
            with (
                self.subTest(kind=kind, namespace=namespace, name=name),
                patch.object(audit.subprocess, "run") as run,
            ):
                result = audit.admitted_longhorn_manager(resource, "unused")
                self.assertEqual(result, resource)
                self.assertIsNot(result, resource)
                run.assert_not_called()

    def check_fixture_exceptions(self, file, test, exceptions):
        """Require every applicable exception, including other namespaces, in the fixture."""
        loaded = list(yaml.safe_load_all((file.parent / test["exceptions"][0]).read_text()))
        expected = exceptions[:2] if test["results"][0]["policy"] == "first" else exceptions[2:]
        self.assertEqual(loaded, expected)

    def shard_expectations(self, folder, count, exceptions):
        """Read all shard assertions while enforcing exception scope and resource identity."""
        seen = Counter()
        self.assertEqual(
            list(yaml.safe_load_all((folder / "exceptions.yaml").read_text())), exceptions
        )
        self.assertEqual(len(list(folder.glob("case-*"))), 1)
        actual = 0
        for file in folder.rglob("kyverno-test.yaml"):
            test = yaml.safe_load(file.read_text())
            self.assertLessEqual(len(test["metadata"]["name"]), 63)
            resources = list(yaml.safe_load_all((file.parent / test["resources"][0]).read_text()))
            for ref in test["results"]:
                matches = [d for d in resources if d["metadata"]["name"] == ref["resources"][0]]
                self.assertEqual(len(matches), 1)
                seen[json.dumps([matches[0], ref["policy"], ref["result"]], sort_keys=True)] += 1
                actual += 1
        self.assertEqual(actual, count)
        return seen

    def test_policy_partition_preserves_assertions_and_exception_scope(self):
        """Verify policy partition preserves assertions and exception scope."""

        policies = [
            {"kind": "ValidatingPolicy", "metadata": {"name": name}} for name in ["first", "second"]
        ]

        def exception(name, policy, namespace):
            return {
                "metadata": {"name": name, "namespace": namespace},
                "spec": {"policyRefs": [{"kind": "ValidatingPolicy", "name": policy}]},
            }

        exceptions = [
            exception("local", "first", "one"),
            exception("other-namespace", "first", "two"),
            exception("other-policy", "second", "one"),
        ]
        original = {
            "kind": "Pod",
            "metadata": {"name": "same", "namespace": "one"},
            "spec": {"containers": [{"name": "app", "image": "example:1"}]},
        }

        changed = copy.deepcopy(original)
        changed["spec"]["containers"][0]["image"] = "unreviewed:1"
        cases = [
            (original, {"first": "skip", "second": "pass"}, False),
            (changed, {"first": "fail"}, True),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "cases"
            counts = audit.write_test_cases(cases, policies, exceptions, output)
            self.assertEqual(counts, {"first": 2, "second": 1})
            seen = []
            for file in output.rglob("kyverno-test.yaml"):
                test = yaml.safe_load(file.read_text())
                docs = list(yaml.safe_load_all((file.parent / test["resources"][0]).read_text()))
                self.assertEqual(len(docs), 1)
                for ref in test["results"]:
                    seen.append((docs[0], ref["policy"], ref["result"]))
                self.check_fixture_exceptions(file, test, exceptions)
            self.assertCountEqual(
                seen,
                [
                    (original, "first", "skip"),
                    (original, "second", "pass"),
                    (changed, "first", "fail"),
                ],
            )
            # Refuse stale fixture directories rather than mixing in old tests.
            with self.assertRaises(FileExistsError):
                audit.write_test_cases(cases, policies, exceptions, output)

    def test_smaller_shards_preserve_every_case_and_all_applicable_exceptions(self):
        """Verify smaller shards preserve every case and all applicable exceptions."""

        policy = {"kind": "ValidatingPolicy", "metadata": {"name": "require-run-as-nonroot"}}
        exceptions = [
            {
                "metadata": {"name": name},
                "spec": {
                    "policyRefs": [{"kind": "ValidatingPolicy", "name": policy["metadata"]["name"]}]
                },
            }
            for name in ["reviewed", "other-workload"]
        ]
        cases = []
        for i in range(7):
            # Separate variants deliberately retain the same identity.
            doc = {
                "kind": "Pod",
                "metadata": {"name": "same" if i % 2 else f"app-{i}"},
                "spec": {"variant": i},
            }
            cases.append(
                (doc, {policy["metadata"]["name"]: "skip" if i % 2 else "fail"}, bool(i % 2))
            )
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "cases"
            counts = audit.write_test_cases(
                cases, [policy], exceptions, output, max_cases_per_shard=3
            )
            self.assertEqual(sorted(counts.values()), [2, 2, 3])
            self.assertEqual(json.loads((output / "counts.json").read_text()), counts)
            seen = Counter()
            for folder in output.iterdir():
                if not folder.is_dir():
                    continue
                seen.update(self.shard_expectations(folder, counts[folder.name], exceptions))
            expected = Counter(
                json.dumps([doc, name, result], sort_keys=True)
                for doc, refs, _ in cases
                for name, result in refs.items()
            )
            self.assertEqual(seen, expected)
            with self.assertRaises(ValueError):
                audit.write_test_cases(cases, [policy], exceptions, Path(tmp) / "invalid", 0)

    def test_seccomp_negative_companion_is_unconfined(self):
        """Verify seccomp negative companion is unconfined."""
        container = audit.noncompliant_container("restrict-seccomp-strict", "unapproved")
        self.assertEqual(container["securityContext"]["seccompProfile"]["type"], "Unconfined")

    def test_other_negative_fixtures_target_their_policy(self):
        """Verify other negative fixtures target their policy."""
        for policy, field, expected in [
            ("require-run-as-nonroot", "runAsNonRoot", False),
            ("disallow-privilege-escalation", "allowPrivilegeEscalation", True),
            ("disallow-privileged-containers", "privileged", True),
            (
                "require-drop-all-capabilities",
                "capabilities",
                {"drop": ["ALL"], "add": ["SYS_ADMIN"]},
            ),
        ]:
            with self.subTest(policy=policy):
                self.assertEqual(
                    audit.noncompliant_container(policy, "unapproved")["securityContext"][field],
                    expected,
                )

    def test_pod_identity_variants_remain_separate_failures(self):
        """Keep same-identity Pod negatives in independent CLI folders."""
        catalog = json.loads((ROOT / "kyverno/exception-catalog.json").read_text())
        entry = next(e for e in catalog["entries"] if e["kind"] == "Pod")
        positive = audit.snapshot(entry)
        original = copy.deepcopy(positive)
        cases = []

        def case(document, expected, separate=False):
            cases.append((copy.deepcopy(document), expected.copy(), separate))

        audit.identity_cases(case, entry, positive)
        self.assertTrue(cases)
        self.assertTrue(all(separate for _, _, separate in cases))
        self.assertTrue(all(set(expected.values()) == {"fail"} for _, expected, _ in cases))
        self.assertTrue(
            any(doc["metadata"]["namespace"] == "unapproved-audit-target" for doc, _, _ in cases)
        )
        self.assertTrue(
            any(doc["spec"]["serviceAccountName"] == "unapproved" for doc, _, _ in cases)
        )
        self.assertEqual(positive, original)

    def test_capability_order_is_allowed_but_duplicates_and_moved_roles_fail(self):
        """Allow capability reordering while rejecting duplicates or relocated roles."""
        policy = "require-drop-all-capabilities"
        catalog = json.loads((ROOT / "kyverno/exception-catalog.json").read_text())
        entry = next(
            e
            for e in catalog["entries"]
            if any(
                len(rule.get("capabilities", [])) > 1 and not rule.get("requirePrivileged")
                for rule in e["policies"].get(policy, {}).get("containers", {}).values()
            )
        )
        approval = entry["policies"][policy]
        role = next(
            name
            for name, rule in approval["containers"].items()
            if len(rule.get("capabilities", [])) > 1
        )
        positive = audit.derived_pod(entry)
        caps = next(c for c in positive["spec"]["containers"] if c["name"] == role)[
            "securityContext"
        ]["capabilities"]["add"]
        cases = []

        def case(document, expected, separate=False):
            cases.append((copy.deepcopy(document), expected[policy], separate))

        audit.capability_variants(case, entry, positive, policy, approval)
        outcomes = {"reordered": [], "duplicated": [], "moved": []}
        for document, expected, _ in cases:
            container = next((c for c in document["spec"]["containers"] if c["name"] == role), None)
            if container is None:
                outcomes["moved"].append(expected)
                continue
            actual = container["securityContext"]["capabilities"].get("add", [])
            if actual == list(reversed(caps)):
                outcomes["reordered"].append(expected)
            if len(actual) > len(set(actual)):
                outcomes["duplicated"].append(expected)
        self.assertEqual(outcomes["reordered"], ["skip"])
        self.assertEqual(outcomes["duplicated"], ["fail"])
        self.assertEqual(outcomes["moved"], ["fail"])

    def test_actual_workload_preparation_sanitizes_without_mutating_input(self):
        """Use current image/guards/labels while excluding unrelated application environment."""
        catalog = json.loads((ROOT / "kyverno/exception-catalog.json").read_text())
        entry = next(e for e in catalog["entries"] if e["kind"] == "Deployment")
        current = audit.snapshot(entry)
        pod = audit.pod_spec(current)
        pod["containers"][0]["env"] = [{"name": "PRIVATE_FIXTURE", "value": "must-not-copy"}]
        pod["containers"][0]["image"] = "registry.example.invalid/current:v2"
        audit.labels(current)["fixture-current-label"] = "preserved"
        before = copy.deepcopy(current)
        actual = {(entry["kind"], entry["namespace"], entry["name"]): current}
        with patch.object(audit.subprocess, "run") as run:
            prepared = audit.prepare_document(entry, actual, "unused")
        run.assert_not_called()
        container = audit.pod_spec(prepared)["containers"][0]
        self.assertNotIn("env", container)
        self.assertEqual(container["image"], "registry.example.invalid/current:v2")
        self.assertEqual(audit.labels(prepared)["fixture-current-label"], "preserved")
        self.assertEqual(current, before)


if __name__ == "__main__":
    unittest.main()
