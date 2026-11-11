"""Exercise Restricted pod-context validation across supported workload forms."""

import importlib.util
import json
import tempfile
from pathlib import Path
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "restricted_contexts", ROOT / "tools/ci/check_restricted_contexts.py"
)
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


class RestrictedContextTests(unittest.TestCase):
    """Check inherited Restricted contexts and reject unsafe container overrides."""

    def pod(self):
        """Build a restricted pod fixture with inherited nonroot and seccomp settings."""
        return {
            "securityContext": {"runAsNonRoot": True, "seccompProfile": {"type": "RuntimeDefault"}},
            "containers": [
                {
                    "name": "app",
                    "securityContext": {
                        "allowPrivilegeEscalation": False,
                        "capabilities": {"drop": ["ALL"]},
                    },
                }
            ],
        }

    def test_scope_combines_argo_and_rendered_namespace_enforcement(self):
        """Both namespace-enforcement sources cover workloads with inherited destinations."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "argocd").mkdir()
            rendered = root / "rendered"
            rendered.mkdir()
            app = {
                "kind": "Application",
                "metadata": {"name": "fixture"},
                "spec": {
                    "destination": {"namespace": "argo-enforced"},
                    "syncPolicy": {
                        "managedNamespaceMetadata": {
                            "labels": {"pod-security.kubernetes.io/enforce": "restricted"}
                        }
                    },
                },
            }
            (root / "argocd/fixture.yaml").write_text(yaml.safe_dump(app))
            (rendered / "inventory.json").write_text(json.dumps(["fixture"]))
            documents = [
                {
                    "kind": "Namespace",
                    "metadata": {
                        "name": "rendered-enforced",
                        "labels": {"pod-security.kubernetes.io/enforce": "restricted"},
                    },
                },
                {"kind": "Pod", "metadata": {"name": "fixture"}, "spec": self.pod()},
            ]
            (rendered / "fixture.yaml").write_text(yaml.safe_dump_all(documents))
            loaded, enforced = policy.load_scope(root, rendered)
        self.assertEqual(enforced, {"argo-enforced", "rendered-enforced"})
        self.assertEqual(loaded, [("argo-enforced", doc) for doc in documents])

    def test_valid_pod_context_inheritance(self):
        """Accept containers inheriting the restricted pod security context."""
        self.assertEqual([], policy.violations(self.pod()))

    def test_container_cannot_override_nonroot_with_root(self):
        """Verify container cannot override nonroot with root."""
        pod = self.pod()
        pod["containers"][0]["securityContext"]["runAsUser"] = 0
        self.assertTrue(any("zero" in e for e in policy.violations(pod)))

    def test_root_init_container_is_also_checked(self):
        """Verify root init container is also checked."""
        pod = self.pod()
        pod["initContainers"] = [{"name": "permissions", "securityContext": {"runAsUser": 0}}]
        self.assertTrue(any("permissions" in e and "zero" in e for e in policy.violations(pod)))

    def test_forbidden_extra_capability_is_rejected(self):
        """Verify forbidden extra capability is rejected."""
        pod = self.pod()
        pod["containers"][0]["securityContext"]["capabilities"]["add"] = ["CHOWN"]
        self.assertTrue(any("added capabilities" in e for e in policy.violations(pod)))

    def test_host_mount_cannot_hide_behind_valid_contexts(self):
        """Verify host mount cannot hide behind valid contexts."""
        pod = self.pod()
        pod["volumes"] = [{"name": "host", "hostPath": {"path": "/"}}]
        self.assertIn("hostPath", policy.violations(pod))

    def test_cronjob_template_is_included(self):
        """Verify cronjob template is included."""
        pod = self.pod()
        doc = {"kind": "CronJob", "spec": {"jobTemplate": {"spec": {"template": {"spec": pod}}}}}
        self.assertEqual([pod], list(policy.templates(doc)))


if __name__ == "__main__":
    unittest.main()
