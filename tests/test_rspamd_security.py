from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEPLOYMENT = ROOT / "mail" / "deployment-rspamd.yaml"


class RspamdSecurityTest(unittest.TestCase):
    def setUp(self):
        deployment = yaml.safe_load(DEPLOYMENT.read_text(encoding="utf-8"))
        self.pod_spec = deployment["spec"]["template"]["spec"]
        self.container = self.pod_spec["containers"][0]
        self.init = self.pod_spec["initContainers"][0]

    def test_rspamd_runs_as_the_image_non_root_identity(self):
        security = self.container["securityContext"]

        self.assertTrue(security["runAsNonRoot"])
        self.assertEqual(11333, security["runAsUser"])
        self.assertEqual(11333, security["runAsGroup"])
        self.assertFalse(security["allowPrivilegeEscalation"])
        self.assertEqual(["ALL"], security["capabilities"]["drop"])
        self.assertEqual("RuntimeDefault", self.pod_spec["securityContext"]["seccompProfile"]["type"])

    def test_permission_init_has_only_required_capabilities(self):
        security = self.init["securityContext"]

        self.assertEqual(0, security["runAsUser"])
        self.assertFalse(security["allowPrivilegeEscalation"])
        self.assertEqual(["ALL"], security["capabilities"]["drop"])
        self.assertEqual({"CHOWN", "FOWNER"}, set(security["capabilities"]["add"]))
        self.assertTrue(security["readOnlyRootFilesystem"])


if __name__ == "__main__":
    unittest.main()
