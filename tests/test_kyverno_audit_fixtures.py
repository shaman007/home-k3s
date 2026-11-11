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
    "audit_cases", ROOT / "tools/kyverno/test-audit-policies.py"
)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class AuditFixtureTests(unittest.TestCase):
    """Preserve policy assertions and applicable exceptions across generated test shards."""
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
                loaded = list(yaml.safe_load_all((file.parent / test["exceptions"][0]).read_text()))
                expected = (
                    exceptions[:2] if test["results"][0]["policy"] == "first" else exceptions[2:]
                )
                self.assertEqual(loaded, expected)
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
                self.assertEqual(
                    list(yaml.safe_load_all((folder / "exceptions.yaml").read_text())), exceptions
                )
                self.assertEqual(len(list(folder.glob("case-*"))), 1)
                actual = 0
                for file in folder.rglob("kyverno-test.yaml"):
                    test = yaml.safe_load(file.read_text())
                    self.assertLessEqual(len(test["metadata"]["name"]), 63)
                    resources = list(
                        yaml.safe_load_all((file.parent / test["resources"][0]).read_text())
                    )
                    for ref in test["results"]:
                        matches = [
                            d for d in resources if d["metadata"]["name"] == ref["resources"][0]
                        ]
                        self.assertEqual(len(matches), 1)
                        seen[
                            json.dumps([matches[0], ref["policy"], ref["result"]], sort_keys=True)
                        ] += 1
                        actual += 1
                self.assertEqual(actual, counts[folder.name])
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


if __name__ == "__main__":
    unittest.main()
