"""Evaluate reviewed audit markers with the real Kubernetes CEL engine in Kyverno."""

import copy
import json
from pathlib import Path
import shutil
import subprocess  # nosec B404 -- local Kyverno CLI, no cluster access
import tempfile
import unittest

import yaml
from tools.monitoring.generate_privileged_audit_exceptions import (
    CATALOG,
    OUTPUT,
    documents,
    render_alloy,
    START,
    END,
    ROOT,
)

ENTRIES = json.loads(CATALOG.read_text())["entries"]


def cel_dynamic(value):
    """Keep heterogeneous fixture maps dynamic, like API admission oldObject."""
    if isinstance(value, dict):
        return (
            "{"
            + ",".join(
                json.dumps(k) + ":dyn(" + cel_dynamic(v) + ")" for k, v in value.items()
            )
            + "}"
        )
    if isinstance(value, list):
        return "[" + ",".join("dyn(" + cel_dynamic(v) + ")" for v in value) + "]"
    return json.dumps(value)


def pod(entry, case="positive"):
    labels = {"app": entry["app"]}
    if entry.get("revisionHash"):
        labels["controller-revision-hash"] = entry["revisionHash"]
    return {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "name": entry["podPrefix"] + case,
            "namespace": entry["namespace"],
            "labels": labels,
            "ownerReferences": [dict(entry["owner"], controller=True)],
        },
        "spec": copy.deepcopy(entry["spec"]),
    }


class PrivilegedAuditGenerationTests(unittest.TestCase):
    def test_generated_policy_matches_reviewed_catalog(self):
        self.assertEqual(
            documents(ENTRIES), list(yaml.safe_load_all(OUTPUT.read_text()))
        )
        text = (ROOT / "kubernetes-audit/config-map-audit-alloy.yaml").read_text()
        self.assertEqual(
            render_alloy(ENTRIES), text[text.index(START) : text.index(END) + len(END)]
        )
        policy, binding = documents(ENTRIES)
        self.assertEqual("Ignore", policy["spec"]["failurePolicy"])
        self.assertEqual([{"expression": "true"}], policy["spec"]["validations"])
        self.assertEqual(["Audit"], binding["spec"]["validationActions"])
        self.assertEqual(6, len(ENTRIES))
        for entry in ENTRIES:
            self.assertNotIn("*", entry["createActor"])
            self.assertTrue(entry["owner"]["uid"])
            if entry["owner"]["kind"] == "DaemonSet":
                self.assertTrue(entry["revisionHash"])


@unittest.skipUnless(
    shutil.which("kyverno"), "install Kyverno CLI for native CEL tests"
)
class PrivilegedAuditCELTests(unittest.TestCase):
    def evaluate(self, resources, actor, expected, update_old=None):
        policy, binding = documents(ENTRIES)
        # Production remains Audit/true. The local test exposes the very same marker
        # expression as a Deny assertion to get explicit pass/fail/error outcomes.
        policy["spec"]["failurePolicy"] = "Fail"
        policy["spec"]["validations"] = [{"expression": 'variables.reviewed != ""'}]
        binding["spec"]["validationActions"] = ["Deny"]
        if update_old is not None:
            variable = policy["spec"]["variables"][-1]
            expression = variable["expression"].replace("request.operation", '"UPDATE"')
            variable["expression"] = (
                "[dyn("
                + cel_dynamic(update_old)
                + ")].map(oldObject, "
                + expression
                + ")[0]"
            )
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "policy.yaml").write_text(yaml.safe_dump_all([policy, binding]))
            (tmp / "pods.yaml").write_text(yaml.safe_dump_all(resources))
            (tmp / "user.yaml").write_text(
                yaml.safe_dump({"userInfo": {"username": actor}})
            )
            result = subprocess.run(
                [
                    "kyverno",
                    "apply",
                    str(tmp / "policy.yaml"),
                    "--resource",
                    str(tmp / "pods.yaml"),
                    "--userinfo",
                    str(tmp / "user.yaml"),
                    "--policy-report",
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertIn(result.returncode, [0, 1], result.stdout + result.stderr)
            output = result.stdout
            self.assertIn("apiVersion:", output, (output + result.stderr)[-6000:])
            report = yaml.safe_load(output[output.index("apiVersion:") :])
            self.assertEqual(
                0, report["summary"]["error"], (output + result.stderr)[-6000:]
            )
            actual = {
                r["resources"][0]["name"]: r["result"]
                for r in report.get("results", [])
            }
            self.assertEqual(expected, actual, (output + result.stderr)[-6000:])

    def test_creation_shapes_and_security_boundaries(self):
        for entry in ENTRIES:
            with self.subTest(profile=entry["id"]):
                resources = [pod(entry)]
                expected = {resources[0]["metadata"]["name"]: "pass"}
                for mutation in [
                    "owner",
                    "service-account",
                    "namespace",
                    "label",
                    "image",
                    "extra-container",
                    "privileged-init",
                    "ephemeral",
                    "host-pid",
                    "share-process",
                    "hostpath",
                    "security",
                    "mount",
                    "revision",
                    "pod-name",
                    "fake-token-mount",
                    "missing-label",
                    "missing-revision",
                ]:
                    if mutation in ["revision", "missing-revision"] and not entry.get(
                        "revisionHash"
                    ):
                        continue
                    p = pod(entry, mutation)
                    s = p["spec"]
                    if mutation == "owner":
                        p["metadata"]["ownerReferences"][0]["uid"] = "other"
                    elif mutation == "service-account":
                        s["serviceAccountName"] = "other"
                    elif mutation == "namespace":
                        p["metadata"]["namespace"] = "other"
                    elif mutation == "label":
                        p["metadata"]["labels"]["app"] = "other"
                    elif mutation == "missing-label":
                        p["metadata"].pop("labels")
                    elif mutation == "missing-revision":
                        p["metadata"]["labels"].pop("controller-revision-hash")
                    elif mutation == "revision":
                        p["metadata"]["labels"]["controller-revision-hash"] = "other"
                    elif mutation == "image":
                        s["containers"][0]["image"] = "docker.io/other/other:1"
                    elif mutation == "extra-container":
                        s["containers"].append(
                            {
                                "name": "shell",
                                "image": "busybox",
                                "securityContext": {"privileged": True},
                            }
                        )
                    elif mutation == "privileged-init":
                        s.setdefault("initContainers", []).append(
                            {
                                "name": "shell",
                                "image": "busybox",
                                "securityContext": {"privileged": True},
                            }
                        )
                    elif mutation == "ephemeral":
                        s["ephemeralContainers"] = [
                            {
                                "name": "debug",
                                "image": "busybox",
                                "securityContext": {"privileged": True},
                            }
                        ]
                    elif mutation == "host-pid":
                        s["hostPID"] = not s.get("hostPID", False)
                    elif mutation == "share-process":
                        s["shareProcessNamespace"] = not s["shareProcessNamespace"]
                    elif mutation == "hostpath":
                        s.setdefault("volumes", []).append(
                            {"name": "host-root", "hostPath": {"path": "/"}}
                        )
                    elif mutation == "security":
                        s["containers"][0].setdefault("securityContext", {})[
                            "capabilities"
                        ] = {"add": ["SYS_ADMIN"]}
                    elif mutation == "pod-name":
                        p["metadata"]["name"] = "other-workload"
                        p["metadata"]["generateName"] = entry["podPrefix"]
                    elif mutation == "fake-token-mount":
                        s["containers"][0].setdefault("volumeMounts", []).append(
                            {
                                "name": "kube-api-access-fake",
                                "mountPath": "/host-root",
                                "readOnly": True,
                            }
                        )
                    elif mutation == "mount":
                        s["containers"][0].setdefault("volumeMounts", []).append(
                            {"name": "host-root", "mountPath": "/host-root"}
                        )
                    resources.append(p)
                    expected[p["metadata"]["name"]] = "fail"
                self.evaluate(resources, entry["createActor"], expected)
                p = pod(entry, "admin")
                self.evaluate([p], "admin", {p["metadata"]["name"]: "fail"})

    def test_longhorn_only_metadata_update_is_reviewed(self):
        entry = next(e for e in ENTRIES if e["id"] == "longhorn-manager")
        original = pod(entry)
        good = copy.deepcopy(original)
        good["metadata"]["name"] = entry["podPrefix"] + "metadata"
        good["metadata"]["labels"]["longhorn.io/test-metadata"] = "true"
        changed = copy.deepcopy(original)
        changed["metadata"]["name"] = entry["podPrefix"] + "spec-change"
        changed["spec"]["containers"][0]["resources"] = {"requests": {"memory": "64Mi"}}
        # Resource changes do not alter security-shape matching, but must still fail
        # the exact old/new Pod spec equality required for update suppression.
        self.evaluate(
            [good, changed],
            entry["metadataUpdateActor"],
            {good["metadata"]["name"]: "pass", changed["metadata"]["name"]: "fail"},
            update_old=original,
        )
