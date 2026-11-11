"""Verify image signature trust and release-signing configuration."""

import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(
        name.replace("-", "_"), ROOT / "tools/supply-chain" / (name + ".py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SignatureTrustTests(unittest.TestCase):
    def test_audits_preserve_rollout_safety_and_restrict_identity(self):
        docs = list(yaml.safe_load_all((ROOT / "kyverno/policy-verify-own-ghcr.yaml").read_text()))
        self.assertEqual(len(docs), 3)
        for doc in docs:
            spec = doc["spec"]
            self.assertEqual(spec["validationActions"], ["Audit"])
            self.assertEqual(spec["failurePolicy"], "Ignore")
            self.assertFalse(spec["validationConfigurations"]["mutateDigest"])
            self.assertTrue(spec["validationConfigurations"]["required"])
            identity = spec["attestors"][0]["cosign"]["keyless"]["identities"][0]
            self.assertEqual(identity["issuer"], "https://token.actions.githubusercontent.com")
            regex = identity["subjectRegExp"]
            repo, workflow = {
                "verify-dockerfiles-ghcr": ("Dockerfiles", "docker-publish.yml"),
                "verify-bastioncam-ghcr": ("bastioncam", "container.yml"),
                "verify-immich-fork-ghcr": ("immich", "docker.yml"),
            }[doc["metadata"]["name"]]
            expected = (
                f"https://github.com/shaman007/{repo}/.github/workflows/{workflow}@refs/heads/main"
            )
            self.assertRegex(expected, regex)
            self.assertRegex(expected.replace("heads/main", "tags/v1.2.3"), regex)
            for bad in [
                expected + "-evil",
                expected.replace("shaman007/", "attacker/"),
                expected.replace("heads/main", "pull/42/merge"),
                expected.replace("heads/main", "heads/untrusted"),
                expected.replace(workflow, "other.yml"),
            ]:
                self.assertIsNone(re.search(regex, bad), bad)

    def test_harbor_preparation_refuses_invalid_key(self):
        with self.assertRaises(subprocess.CalledProcessError):
            load("prepare-harbor-signing").prepare("not a public key")

    def test_subresources_have_admission_checks_without_background_rbac(self):
        generated = load("generate-ephemeral-policies")
        self.assertEqual(generated.OUTPUT.read_text(), generated.generate())
        docs = list(yaml.safe_load_all(generated.generate()))
        self.assertEqual(len(docs), 6)
        for policy in docs:
            spec = policy["spec"]
            self.assertFalse(spec["evaluation"]["background"]["enabled"])
            self.assertTrue(spec["evaluation"]["admission"]["enabled"])
            self.assertEqual(
                spec["matchConstraints"]["resourceRules"][0]["resources"],
                ["pods/ephemeralcontainers"],
            )
            expression = spec["validations"][0]["expression"]
            self.assertIn("images.initContainers", expression)
            self.assertIn("images.ephemeralContainers", expression)
            self.assertEqual(spec["validationActions"], ["Audit"])

    def test_harbor_renderer_preserves_integrated_signing_contract(self):
        public = (ROOT / "docs/supply-chain/cosign.pub").read_text()
        documents = load("prepare-harbor-signing").prepare(public)
        self.assertEqual(
            documents["cron-job-podman-builder.yaml"],
            yaml.safe_load((ROOT / "image-builder/cron-job-podman-builder.yaml").read_text()),
        )
        self.assertNotIn("PRIVATE KEY", yaml.safe_dump(documents))
        policy = documents["policy-verify-own-harbor.yaml"]
        self.assertEqual(policy["spec"]["attestors"][0]["cosign"]["key"]["data"], public)

    def test_harbor_renderer_preserves_updated_helper_images(self):
        module = load("prepare-harbor-signing")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in (
                "image-builder/cron-job-podman-builder.yaml",
                "kyverno/policy-verify-own-ghcr.yaml",
            ):
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text((ROOT / relative).read_text())
            path = root / "image-builder/cron-job-podman-builder.yaml"
            cron = yaml.safe_load(path.read_text())
            helpers = cron["spec"]["jobTemplate"]["spec"]["template"]["spec"]["initContainers"]
            expected = {}
            for helper in helpers:
                if helper["name"] in {"copy-busybox", "copy-cosign"}:
                    helper["image"] = helper["image"].rsplit(":", 1)[0] + ":future-version"
                    expected[helper["name"]] = helper["image"]
            self.assertEqual(len(expected), 2)
            path.write_text(yaml.safe_dump(cron))
            with patch.object(module, "ROOT", root):
                rendered = module.prepare((ROOT / "docs/supply-chain/cosign.pub").read_text())
            actual = rendered["cron-job-podman-builder.yaml"]
            self.assertEqual(actual, cron)


class ReleaseSigningTests(unittest.TestCase):
    def setUp(self):
        self.module = load("sign-release-assets")
        self.asset = {"id": 123, "name": "app.tar.gz", "updated_at": "2026-11-10"}
        self.env = patch.dict(
            os.environ,
            {
                "GITHUB_REPOSITORY": "shaman007/key-val",
                "GITHUB_WORKFLOW_REF": (
                    "shaman007/key-val/.github/workflows/sign-release.yml@refs/tags/v1"
                ),
                "RELEASE_TAG": "v1",
            },
        )
        self.env.start()
        self.addCleanup(self.env.stop)

    def invoke(self, initial, final=None, fail_verify=False):
        calls = []
        self.last_calls = calls
        releases = iter([initial, initial if final is None else final])

        def fake(*args, **kwargs):
            calls.append(args)
            if args[:2] == ("gh", "api") and "stdout" not in kwargs:
                return subprocess.CompletedProcess(
                    args, 0, json.dumps({"draft": False, "assets": next(releases)})
                )
            if args[:2] == ("cosign", "verify-blob") and fail_verify:
                raise subprocess.CalledProcessError(1, args)
            return subprocess.CompletedProcess(args, 0)

        with patch.object(self.module, "run", side_effect=fake):
            self.module.main()
        return calls

    def test_signs_bytes_verifies_exact_workflow_then_uploads(self):
        calls = self.invoke([self.asset])
        verify = next(c for c in calls if c[:2] == ("cosign", "verify-blob"))
        self.assertIn("https://github.com/" + os.environ["GITHUB_WORKFLOW_REF"], verify)
        download = next(c for c in calls if "Accept: application/octet-stream" in c)
        self.assertEqual(download[-1], "repos/shaman007/key-val/releases/assets/123")
        self.assertEqual(calls[-1][:3], ("gh", "release", "upload"))

    def test_rejects_no_files_and_unsafe_paths(self):
        for assets in ([], [dict(self.asset, name="../secret")], [dict(self.asset, name="$(id)")]):
            with self.assertRaises(SystemExit):
                self.invoke(assets)

    def test_changed_assets_and_failed_verification_prevent_upload(self):
        for fail, final in [(False, [dict(self.asset, id=456)]), (True, None)]:
            with self.assertRaises((SystemExit, subprocess.CalledProcessError)):
                self.invoke([self.asset], final=final, fail_verify=fail)
            self.assertFalse(any(c[:3] == ("gh", "release", "upload") for c in self.last_calls))


if __name__ == "__main__":
    unittest.main()
