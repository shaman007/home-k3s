from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]

EXPECTED_LABELS = {
    "pod-security.kubernetes.io/warn": "restricted",
    "pod-security.kubernetes.io/warn-version": "latest",
    "pod-security.kubernetes.io/audit": "restricted",
    "pod-security.kubernetes.io/audit-version": "latest",
}


def load_yaml(path: str) -> dict:
    return yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))


class PodSecurityNamespaceLabelsTest(unittest.TestCase):
    def test_explicit_namespaces_have_restricted_audit_and_warn(self):
        for path in (
            "comfyui/namespace-comfyui.yaml",
            "open-terminal/namespace-open-terminal.yaml",
            "open-webui/namespace-open-webui.yaml",
        ):
            namespace = load_yaml(path)
            self.assertEqual("Namespace", namespace["kind"])
            labels = namespace["metadata"]["labels"]
            for name, value in EXPECTED_LABELS.items():
                self.assertEqual(value, labels.get(name), path)
            self.assertNotIn("pod-security.kubernetes.io/enforce", labels)

    def test_argo_managed_namespaces_have_restricted_audit_and_warn(self):
        for path in (
            "argocd/application-argocd-install.yaml",
            "argocd/application-ollama.yaml",
        ):
            application = load_yaml(path)
            sync_policy = application["spec"]["syncPolicy"]
            labels = sync_policy["managedNamespaceMetadata"]["labels"]
            for name, value in EXPECTED_LABELS.items():
                self.assertEqual(value, labels.get(name), path)
            self.assertNotIn("pod-security.kubernetes.io/enforce", labels)
            self.assertIn("CreateNamespace=true", sync_policy["syncOptions"])


if __name__ == "__main__":
    unittest.main()
