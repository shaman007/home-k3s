from pathlib import Path
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

    def test_builder_uses_versioned_upstream_runtime(self):
        image = self.container["image"]

        self.assertRegex(image, r"^quay\.io/podman/stable:v\d+\.\d+\.\d+$")
        self.assertNotIn(":latest", image)
        self.assertNotIn("@sha256:", image)
        self.assertEqual("IfNotPresent", self.container["imagePullPolicy"])

    def test_builder_runs_weekly(self):
        spec = self.cronjob["spec"]
        container = spec["jobTemplate"]["spec"]["template"]["spec"]["containers"][0]

        self.assertEqual("29 2 * * 1", spec["schedule"])
        self.assertEqual("Etc/UTC", spec["timeZone"])
        self.assertEqual(["/bin/bash", "-c"], container["command"])
        self.assertIn("exec ./build.sh", container["args"][0])

    def test_builder_does_not_receive_a_service_account_token(self):
        self.assertFalse(self.pod_spec["automountServiceAccountToken"])

    def test_builder_uses_space_efficient_overlay_storage(self):
        environment = {
            item["name"]: item.get("value")
            for item in self.container["env"]
        }

        self.assertEqual("overlay", environment["STORAGE_DRIVER"])

    def test_checkout_uses_versioned_upstream_git_sync(self):
        checkout = self.pod_spec["initContainers"][0]

        self.assertRegex(
            checkout["image"],
            r"^registry\.k8s\.io/git-sync/git-sync:v\d+\.\d+\.\d+$",
        )
        self.assertNotIn("@sha256:", checkout["image"])

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
