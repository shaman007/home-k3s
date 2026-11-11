"""The review-only webhook build generator must not overwrite predictable files."""

import base64
import hashlib
from pathlib import Path
import runpy
import stat
import tempfile
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]


class WebhookBuildManifestTest(unittest.TestCase):
    """Verify secure file allocation while retaining deterministic source/image identity."""

    def test_repeated_generation_uses_private_distinct_files(self):
        """Keep existing review files intact and allocate each output exclusively at 0600."""
        allocate = tempfile.mkstemp
        with tempfile.TemporaryDirectory() as directory:
            def temporary_manifest(**options):
                """Allocate real exclusive files inside the disposable test directory."""
                return allocate(dir=directory, **options)

            outputs = []
            documents = []
            for _ in range(2):
                with (
                    patch.object(tempfile, "mkstemp", side_effect=temporary_manifest),
                    patch("builtins.print"),
                ):
                    namespace = runpy.run_path(
                        str(ROOT / "tools/godaddy-webhook/prepare_build.py")
                    )
                output = Path(namespace["output"])
                self.assertEqual(output.parent, Path(directory))
                self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
                outputs.append(output)
                documents.append(list(yaml.safe_load_all(output.read_text())))
                if len(outputs) == 1:
                    output.write_text("reviewed-first-output")
            self.assertNotEqual(outputs[0], outputs[1])
            self.assertEqual(outputs[0].read_text(), "reviewed-first-output")
            self.assertEqual(documents[0], documents[1])
            config, job = documents[0]
            source = base64.b64decode(config["binaryData"]["source.tar.gz"])
            digest = hashlib.sha256(source).hexdigest()[:12]
            self.assertEqual(config["metadata"]["name"], "godaddy-webhook-build-" + digest)
            self.assertEqual(job["metadata"]["name"], config["metadata"]["name"])
            self.assertFalse(job["spec"]["template"]["spec"]["automountServiceAccountToken"])


if __name__ == "__main__":
    unittest.main()
