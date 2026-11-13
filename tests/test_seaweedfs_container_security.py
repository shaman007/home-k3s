"""Verify SeaweedFS container security contexts and required writable paths."""

import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "seaweedfs/deployment-seaweedfs-s3.yaml"


class SeaweedFSContainerSecurityTest(unittest.TestCase):
    """Require restricted containers and scoped writable storage paths."""
    @classmethod
    def setUpClass(cls):
        deployment = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
        cls.pod_spec = deployment["spec"]["template"]["spec"]
        cls.containers = {
            container["name"]: container for container in cls.pod_spec["containers"]
        }

    def test_main_containers_are_non_root_with_read_only_root_filesystems(self):
        """Verify main containers are non root with read only root filesystems."""
        self.assertFalse(self.pod_spec["automountServiceAccountToken"])
        self.assertEqual(1000, self.pod_spec["securityContext"]["fsGroup"])
        self.assertEqual(
            "RuntimeDefault",
            self.pod_spec["securityContext"]["seccompProfile"]["type"],
        )

        for name in ("master", "volume", "filer", "s3"):
            security = self.containers[name]["securityContext"]
            self.assertEqual(1000, security["runAsUser"], name)
            self.assertEqual(1000, security["runAsGroup"], name)
            self.assertTrue(security["runAsNonRoot"], name)
            self.assertTrue(security["readOnlyRootFilesystem"], name)
            self.assertFalse(security["allowPrivilegeEscalation"], name)
            self.assertEqual(["ALL"], security["capabilities"]["drop"], name)

    def test_backup_storage_can_start_without_harbor_images(self):
        """Recovery of Harbor must not require Harbor to fetch any SeaweedFS image."""
        containers = self.pod_spec["initContainers"] + self.pod_spec["containers"]
        for container in containers:
            repository = (
                "docker.io/library/busybox"
                if container["name"] == "prepare-data-and-tmp"
                else "docker.io/chrislusf/seaweedfs"
            )
            with self.subTest(container=container["name"]):
                self.assertRegex(
                    container["image"],
                    "^" + repository.replace(".", r"\.") + r":[^@\s]+@sha256:[0-9a-f]{64}$",
                )
        self.assertEqual(1, len({container["image"] for container in self.containers.values()}))

    def test_only_storage_services_mount_data(self):
        """Verify only storage services mount data."""
        for name in ("master", "volume", "filer"):
            self.assertIn(
                {"name": "data", "mountPath": "/data"},
                self.containers[name]["volumeMounts"],
                name,
            )

        self.assertNotIn(
            "data",
            [mount["name"] for mount in self.containers["s3"]["volumeMounts"]],
        )


if __name__ == "__main__":
    unittest.main()
