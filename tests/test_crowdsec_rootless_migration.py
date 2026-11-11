"""Prevent a SQLite cutover from silently starting against an empty database."""

from pathlib import Path
import unittest
import importlib.util

import yaml

ROOT = Path(__file__).resolve().parents[1]


class CrowdSecRootlessMigrationTest(unittest.TestCase):
    """Require the migration and runtime to share the persistent CrowdSec database."""

    def test_migration_and_runtime_share_the_same_persistent_database(self):
        """Verify migration and runtime share the same persistent database."""
        values = yaml.safe_load((ROOT / "crowdsec/values.yaml").read_text())
        lapi = values["lapi"]
        # The source writer must stop before the backup snapshot is taken.
        self.assertEqual("Recreate", lapi["strategy"]["type"])
        self.assertEqual(1, lapi["replicas"])
        migration = next(
            c for c in lapi["extraInitContainers"] if c["name"] == "prepare-rootless-database"
        )
        source, target = map(Path, migration["command"][1:])
        selected = Path(
            yaml.safe_load(values["config"]["config.yaml.local"])["db_config"]["db_path"]
        )
        self.assertEqual(selected, target)
        self.assertNotEqual(source, target)
        mount = next(v for v in migration["volumeMounts"] if v["name"] == "crowdsec-db")
        self.assertEqual("crowdsec", mount["subPath"])
        self.assertTrue(source.is_relative_to(mount["mountPath"]))
        self.assertTrue(target.is_relative_to(mount["mountPath"]))
        self.assertEqual(
            f"{values['image']['repository']}:{values['image']['tag']}", migration["image"]
        )


class CrowdSecRootlessAgentMountTest(unittest.TestCase):
    """Require writable parents for CrowdSec agent ConfigMap subpath mounts."""

    def test_configmap_subpaths_have_a_writable_parent(self):
        """Verify configmap subpaths have a writable parent."""
        values = yaml.safe_load((ROOT / "crowdsec/values.yaml").read_text())
        mount = next(
            v for v in values["agent"]["extraVolumeMounts"] if v["mountPath"] == "/etc/crowdsec"
        )
        volume = next(v for v in values["agent"]["extraVolumes"] if v["name"] == mount["name"])
        self.assertIn("emptyDir", volume)
        self.assertEqual(1000, values["agent"]["podSecurityContext"]["fsGroup"])


class CrowdSecRenderedMountContractTest(unittest.TestCase):
    """Check rendered mount isolation and writable parent requirements."""

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(
            "crowdsec_mounts", ROOT / "tools/ci/check_crowdsec_rootless.py"
        )
        cls.check = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.check)

    def test_database_init_cannot_read_another_subpath(self):
        """Verify database init cannot read another subpath."""
        runtime = {"name": "db", "mountPath": "/var/lib/crowdsec/data", "subPath": "crowdsec"}
        preparation = {"name": "db", "mountPath": "/var/lib/crowdsec/data"}
        doc = {
            "kind": "Deployment",
            "spec": {
                "template": {
                    "spec": {
                        "containers": [
                            {
                                "name": "crowdsec-lapi",
                                "image": "library/crowdsec-rootless:v1",
                                "volumeMounts": [runtime],
                            }
                        ],
                        "initContainers": [
                            {"name": "prepare-rootless-database", "volumeMounts": [preparation]}
                        ],
                    }
                }
            },
        }
        self.assertTrue(self.check.violations(doc))
        preparation["subPath"] = "crowdsec"
        self.assertEqual([], self.check.violations(doc))

    def test_nested_configmaps_require_a_writable_parent_mount(self):
        """Verify nested configmaps require a writable parent mount."""
        agent = {
            "name": "crowdsec-agent",
            "image": "library/crowdsec-rootless:v1",
            "volumeMounts": [
                {
                    "name": "config",
                    "mountPath": "/etc/crowdsec/acquis.yaml",
                    "subPath": "acquis.yaml",
                }
            ],
        }
        pod = {"containers": [agent], "securityContext": {"fsGroup": 1000}, "volumes": []}
        doc = {"kind": "Deployment", "spec": {"template": {"spec": pod}}}
        self.assertTrue(self.check.violations(doc))
        agent["volumeMounts"].append({"name": "parent", "mountPath": "/etc/crowdsec"})
        pod["volumes"].append({"name": "parent", "emptyDir": {}})
        self.assertEqual([], self.check.violations(doc))


if __name__ == "__main__":
    unittest.main()
