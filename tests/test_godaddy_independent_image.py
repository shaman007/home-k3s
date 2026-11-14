"""Exercise inactive cutover rendering and the independently published image contract."""

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "godaddy_independent", ROOT / "tools/godaddy-webhook/prepare_independent.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class IndependentWebhookTests(unittest.TestCase):
    """Keep preparation inactive and signing identities narrowly scoped."""

    def test_candidate_preserves_chart_runtime_and_verifies_only_new_identity(self):
        """Only image identity changes; policies retain existing enforcement behavior."""
        digest = "sha256:" + "a" * 64
        files = MODULE.candidates(digest)
        values = yaml.safe_load(files["values-ghcr.yaml"])
        self.assertEqual(set(values), {"image"})
        self.assertEqual(
            values["image"], {"repository": MODULE.IMAGE, "digest": digest}
        )
        policies = list(yaml.safe_load_all(files["policy-verify-godaddy-ghcr.yaml"]))
        self.assertEqual(len(policies), 2)
        for policy in policies:
            spec = policy["spec"]
            self.assertEqual(spec["validationActions"], ["Audit"])
            self.assertEqual(spec["failurePolicy"], "Ignore")
            self.assertEqual(
                spec["attestors"][0]["cosign"]["keyless"]["identities"],
                [
                    {
                        "issuer": "https://token.actions.githubusercontent.com",
                        "subject": MODULE.IDENTITY,
                    }
                ],
            )
            self.assertEqual(
                spec["matchImageReferences"],
                [{"glob": MODULE.IMAGE + ":*"}, {"glob": MODULE.IMAGE + "@*"}],
            )
        active = yaml.safe_load(
            (ROOT / "tools/godaddy-webhook/chart/values.yaml").read_text()
        )
        self.assertTrue(active["image"]["repository"].startswith("harbor."))

    def test_output_is_new_and_outside_active_repository(self):
        """Refuse an active source destination or overwriting a reviewed candidate."""
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "candidate"
            args = [
                "prepare",
                "--digest",
                "sha256:" + "b" * 64,
                "--output",
                str(output),
            ]
            with patch("sys.argv", args), patch("builtins.print"):
                MODULE.main()
                self.assertEqual(len(list(output.iterdir())), 2)
                with self.assertRaises(FileExistsError):
                    MODULE.main()
            args[-1] = str(ROOT / "tools/godaddy-webhook/chart")
            with (
                patch("sys.argv", args),
                patch("sys.stderr"),
                self.assertRaises(SystemExit),
            ):
                MODULE.main()

    def test_mutable_or_injected_digest_is_rejected(self):
        """Do not emit image tags or malformed references as accepted digests."""
        for digest in (
            "latest",
            "sha256:" + "A" * 64,
            "sha256:" + "a" * 63,
            "sha256:" + "a" * 64 + "\nx",
        ):
            with self.subTest(digest=digest), self.assertRaises(ValueError):
                MODULE.candidates(digest)

    def test_publishing_requires_manual_main_run_and_no_cluster_credentials(self):
        """A push cannot publish, and publication cannot deploy or require Harbor."""
        text = (ROOT / ".github/workflows/publish-godaddy-webhook.yml").read_text()
        workflow = yaml.safe_load(text)
        self.assertEqual(
            workflow.get("on", workflow.get(True)), {"workflow_dispatch": None}
        )
        job = workflow["jobs"]["publish"]
        self.assertIn("github.ref == 'refs/heads/main'", job["if"])
        self.assertEqual(
            job["permissions"],
            {"contents": "read", "packages": "write", "id-token": "write"},
        )
        for forbidden in (
            "harbor.",
            "kubectl",
            "KUBECONFIG",
            "secrets.",
            "pull_request_target",
        ):
            self.assertNotIn(forbidden, text)
        self.assertIn(MODULE.IDENTITY, text)
        self.assertIn("go test -mod=readonly -race ./...", text)
        self.assertIn("cosign verify", text)
        self.assertIn('"$IMAGE@$digest"', text)


if __name__ == "__main__":
    unittest.main()
