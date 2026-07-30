from pathlib import Path
import re
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
CRONJOB = ROOT / "image-builder" / "cron-job-podman-builder.yaml"


class ImageBuilderSecurityTest(unittest.TestCase):
    def setUp(self):
        self.cronjob = yaml.safe_load(CRONJOB.read_text(encoding="utf-8"))
        self.pod_spec = self.cronjob["spec"]["jobTemplate"]["spec"]["template"]["spec"]
        self.container = self.pod_spec["containers"][0]

    def test_builder_runtime_is_pinned_by_digest(self):
        image = self.container["image"]

        self.assertRegex(image, r"^harbor\.andreybondarenko\.com/library/podman-builder@sha256:[0-9a-f]{64}$")
        self.assertNotIn(":latest", image)
        self.assertEqual("IfNotPresent", self.container["imagePullPolicy"])

    def test_builder_does_not_receive_a_service_account_token(self):
        self.assertFalse(self.pod_spec["automountServiceAccountToken"])

    def test_builder_digest_is_not_a_placeholder(self):
        digest = self.container["image"].split("@sha256:", 1)[1]

        self.assertFalse(re.fullmatch(r"([0-9a-f])\1{63}", digest))


if __name__ == "__main__":
    unittest.main()
