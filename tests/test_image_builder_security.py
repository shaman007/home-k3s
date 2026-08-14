from pathlib import Path
import re
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
CRONJOB = ROOT / "image-builder" / "cron-job-podman-builder.yaml"
NETWORK_POLICIES = ROOT / "image-builder" / "network-policy-podman-builder.yaml"


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

    def test_builder_runs_every_two_weeks(self):
        spec = self.cronjob["spec"]
        container = spec["jobTemplate"]["spec"]["template"]["spec"]["containers"][0]
        guard = container["command"][2]

        self.assertEqual("29 2 * * 1", spec["schedule"])
        self.assertEqual("Etc/UTC", spec["timeZone"])
        self.assertIn("current_epoch_week", guard)
        self.assertIn("% 2", guard)
        self.assertIn("exec /usr/local/bin/nightly-build", guard)

    def test_builder_does_not_receive_a_service_account_token(self):
        self.assertFalse(self.pod_spec["automountServiceAccountToken"])

    def test_builder_uses_space_efficient_overlay_storage(self):
        environment = {
            item["name"]: item.get("value")
            for item in self.container["env"]
        }

        self.assertEqual("overlay", environment["STORAGE_DRIVER"])

    def test_builder_digest_is_not_a_placeholder(self):
        digest = self.container["image"].split("@sha256:", 1)[1]

        self.assertFalse(re.fullmatch(r"([0-9a-f])\1{63}", digest))

    def test_builder_network_policy_limits_traffic(self):
        policies = {
            document["metadata"]["name"]: document
            for document in yaml.safe_load_all(NETWORK_POLICIES.read_text(encoding="utf-8"))
        }
        default_deny = policies["podman-builder-default-deny"]["spec"]
        allow = policies["podman-builder-allow-build-egress"]["spec"]

        self.assertEqual({"Ingress", "Egress"}, set(default_deny["policyTypes"]))
        self.assertNotIn("ingress", default_deny)
        self.assertNotIn("egress", default_deny)
        allowed_ports = {
            (port["protocol"], port["port"])
            for rule in allow["egress"]
            for port in rule["ports"]
        }
        self.assertEqual(
            {("UDP", 53), ("TCP", 53), ("TCP", 80), ("TCP", 443)},
            allowed_ports,
        )


if __name__ == "__main__":
    unittest.main()
