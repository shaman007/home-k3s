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
        self.assertTrue(
            any(
                self._is_version_pinned_upstream_install(resource)
                for resource in manifest["resources"]
            ),
            "Argo CD upstream install resource must be pinned to a release version",
        )

    @staticmethod
    def _is_version_pinned_upstream_install(resource):
        prefix = "github.com/argoproj/argo-cd//manifests/cluster-install?ref=v"
        if not resource.startswith(prefix):
            return False

        version = resource.removeprefix(prefix)
        return len(version.split(".")) == 3 and all(
            part.isdigit() for part in version.split(".")
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

    def test_renovate_scans_mastodon_helm_values(self):
        config = json.loads(RENOVATE.read_text(encoding="utf-8"))

        self.assertIn(
            "/^mastodon\\/mastodon-values\\.ya?ml$/",
            config["helm-values"]["managerFilePatterns"],
        )
        mastodon_custom_managers = [
            manager
            for manager in config["customManagers"]
            if "/^mastodon\\/mastodon-values\\.ya?ml$/"
            in manager["managerFilePatterns"]
        ]
        self.assertEqual(len(mastodon_custom_managers), 1)
        self.assertEqual(
            mastodon_custom_managers[0]["datasourceTemplate"], "docker"
        )

    def test_renovate_ignores_deprecated_manifests(self):
        config = json.loads(RENOVATE.read_text(encoding="utf-8"))

        self.assertIn("DEPRECATED/**", config["ignorePaths"])


if __name__ == "__main__":
    unittest.main()
