"""Keep staged S3 client isolation and canonical ESO transforms reproducible."""

import importlib.util
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "s3_batch", ROOT / "tools/bootstrap/prepare_dependency_batch.py"
)
BATCH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BATCH)


def read(path):
    """Load only non-secret Git manifests."""
    return yaml.safe_load((ROOT / path).read_text())


class ObservabilityS3IsolationTests(unittest.TestCase):
    """A shared projected file must not switch clients before their stage."""

    def test_store_and_compactor_have_independent_config_targets(self):
        """Separate ESO targets retain the same OpenBao source and guarded transform."""
        shared = read("thanos/external-secret-thanos-objstore-secret.yaml")
        targets = {shared["spec"]["target"]["name"]}
        for deployment, name in (
            ("thanos-store-gateway", "thanos-store-objstore-internal"),
            ("thanos-compactor", "thanos-compactor-objstore-internal"),
        ):
            config = read(f"thanos/external-secret-{name}.yaml")
            self.assertEqual(config["spec"]["data"], shared["spec"]["data"])
            self.assertEqual(
                config["spec"]["secretStoreRef"], shared["spec"]["secretStoreRef"]
            )
            self.assertEqual(
                config["spec"]["target"]["template"],
                shared["spec"]["target"]["template"],
            )
            self.assertEqual(config["spec"]["target"]["name"], name)
            self.assertNotIn(name, targets)
            targets.add(name)
            pod = read(f"thanos/deployment-{deployment}.yaml")["spec"]["template"][
                "spec"
            ]
            volume = next(v for v in pod["volumes"] if v["name"] == "objstoreyml")
            self.assertEqual(volume["secret"]["secretName"], name)
        template = shared["spec"]["target"]["template"]
        self.assertEqual(
            template,
            {
                "engineVersion": "v2",
                "mergePolicy": "Replace",
                "data": {"objstore.yml": BATCH.THANOS_TEMPLATE},
            },
        )

    def test_prometheus_keeps_current_phase_storage_contract(self):
        """Preserve the legacy sidecar until cutover, then require true separation."""
        pod = read(
            "metrics/kubernetes-prometheus/deployment-prometheus-deployment.yaml"
        )["spec"]["template"]["spec"]
        self.assertEqual([c["name"] for c in pod["initContainers"]], ["fix-perms"])
        prometheus = next(c for c in pod["containers"] if c["name"] == "prometheus")
        self.assertNotIn("command", prometheus)
        self.assertNotIn("objstoreyml", {m["name"] for m in prometheus["volumeMounts"]})
        if any(c["name"] == "thanos" for c in pod["containers"]):
            volume = next(v for v in pod["volumes"] if v["name"] == "objstoreyml")
            self.assertEqual(volume["secret"]["secretName"], "thanos-objstore-secret")
        else:
            self.assertEqual([c["name"] for c in pod["containers"]], ["prometheus"])
            self.assertFalse(any(v["name"] == "objstoreyml" for v in pod["volumes"]))
            self.assertTrue(
                all(
                    v["secret"].get("optional") for v in pod["volumes"] if "secret" in v
                )
            )
