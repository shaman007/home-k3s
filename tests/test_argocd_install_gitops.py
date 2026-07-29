import json
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
KUSTOMIZATION = ROOT / "argocd-install" / "kustomization.yaml"
APPLICATION = ROOT / "argocd" / "application-argocd-install.yaml"
RENOVATE = ROOT / "renovate.json"


class ArgoCdInstallGitopsTest(unittest.TestCase):
    def test_upstream_install_is_version_pinned(self):
        manifest = yaml.safe_load(KUSTOMIZATION.read_text(encoding="utf-8"))

        self.assertEqual(manifest["namespace"], "argocd")
        self.assertIn(
            "github.com/argoproj/argo-cd//manifests/cluster-install?ref=v3.4.1",
            manifest["resources"],
        )

    def test_install_is_managed_by_argocd(self):
        application = yaml.safe_load(APPLICATION.read_text(encoding="utf-8"))

        self.assertEqual(application["spec"]["source"]["path"], "argocd-install")
        self.assertEqual(application["spec"]["project"], "platform")
        self.assertTrue(application["spec"]["syncPolicy"]["automated"]["prune"])
        self.assertTrue(application["spec"]["syncPolicy"]["automated"]["selfHeal"])
        self.assertIn(
            "ServerSideApply=true",
            application["spec"]["syncPolicy"]["syncOptions"],
        )

    def test_renovate_requires_review_for_non_patch_upgrades(self):
        config = json.loads(RENOVATE.read_text(encoding="utf-8"))
        rules = [
            rule
            for rule in config["packageRules"]
            if "argocd-install/kustomization.yaml" in rule.get("matchFileNames", [])
        ]

        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0]["matchManagers"], ["kustomize"])
        self.assertEqual(rules[0]["matchUpdateTypes"], ["minor", "major"])
        self.assertFalse(rules[0]["automerge"])


if __name__ == "__main__":
    unittest.main()
