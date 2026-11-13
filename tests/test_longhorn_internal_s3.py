"""Offline routing transition contracts; synthetic Secrets only."""

import base64
import copy
import graphlib
import importlib.util
import json
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "longhorn_s3", ROOT / "tools/bootstrap/prepare_longhorn_s3.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def apply_patch(document, operations):
    """Minimal atomic RFC6902 test/replace simulator, not a live API client."""
    result = copy.deepcopy(document)
    for operation in operations:
        parent = result
        parts = operation["path"].strip("/").split("/")
        for part in parts[:-1]:
            parent = parent[part]
        if operation["op"] == "test":
            if parent[parts[-1]] != operation["value"]:
                raise ValueError("Precondition failed")
        elif operation["op"] == "replace":
            parent[parts[-1]] = operation["value"]
        else:
            raise AssertionError("Unexpected patch operation")
    return result


class LonghornInternalS3Tests(unittest.TestCase):
    """Keep credentials, backups and the current live routing outside the proposal."""

    def setUp(self):
        self.plan = json.loads(MODULE.PLAN.read_text())
        self.secret = {
            "metadata": {
                "name": "longhorn-backup-s3",
                "namespace": "longhorn-system",
                "resourceVersion": "123",
                "labels": {"fixture": "retained"},
            },
            "type": "Opaque",
            "data": {
                "AWS_ENDPOINTS": base64.b64encode(
                    self.plan["old_endpoint"].encode()
                ).decode(),
                "AWS_ACCESS_KEY_ID": "c3ludGhldGlj",
                "AWS_SECRET_ACCESS_KEY": "Zml4dHVyZQ==",
                "AWS_CERT": "dGVzdC1jYQ==",
                "AWS_VIRTUAL_HOSTED_STYLE": "ZmFsc2U=",
            },
        }

    def test_roundtrip_changes_only_endpoint(self):
        """Roundtrip changes only endpoint."""
        changed = apply_patch(self.secret, MODULE.endpoint_patch("123"))
        self.assertEqual(
            base64.b64decode(changed["data"]["AWS_ENDPOINTS"]).decode(),
            self.plan["new_endpoint"],
        )
        restored = apply_patch(changed, MODULE.endpoint_patch("123", rollback=True))
        self.assertEqual(restored, self.secret)
        changed["data"]["AWS_ENDPOINTS"] = self.secret["data"]["AWS_ENDPOINTS"]
        self.assertEqual(changed, self.secret)
        self.assertEqual(self.plan["backup_target_url"], "s3://backup@us-east-1/")

    def test_stale_or_wrong_target_fails_without_partial_changes(self):
        """Stale or wrong target fails without partial changes."""
        for path, value in (
            ("resourceVersion", "124"),
            ("name", "other"),
            ("namespace", "other"),
        ):
            secret = copy.deepcopy(self.secret)
            secret["metadata"][path] = value
            original = copy.deepcopy(secret)
            with self.subTest(path=path), self.assertRaises(ValueError):
                apply_patch(secret, MODULE.endpoint_patch("123"))
            self.assertEqual(secret, original)
        secret = copy.deepcopy(self.secret)
        secret["data"]["AWS_ENDPOINTS"] = "dW5leHBlY3RlZA=="
        with self.assertRaises(ValueError):
            apply_patch(secret, MODULE.endpoint_patch("123"))
        with self.assertRaises(ValueError):
            apply_patch(self.secret, MODULE.endpoint_patch("123", rollback=True))

    def test_invalid_version_rejected(self):
        """Invalid version rejected."""
        for value in ("", "../123", "abc"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                MODULE.endpoint_patch(value)

    def test_service_and_existing_policy_support_endpoint(self):
        """Service and existing policy support endpoint."""
        service = yaml.safe_load((ROOT / "seaweedfs/service-s3.yaml").read_text())
        self.assertEqual(service["metadata"]["name"], "s3")
        self.assertEqual(service["metadata"]["namespace"], "seaweedfs")
        self.assertEqual(service["spec"].get("type", "ClusterIP"), "ClusterIP")
        self.assertEqual(
            self.plan["new_endpoint"], "http://s3.seaweedfs.svc.cluster.local:8333"
        )
        self.assertIn(
            {"name": "s3", "port": 8333, "targetPort": 8333}, service["spec"]["ports"]
        )
        deployment = yaml.safe_load(
            (ROOT / "seaweedfs/deployment-seaweedfs-s3.yaml").read_text()
        )
        labels = deployment["spec"]["template"]["metadata"]["labels"]
        self.assertTrue(
            all(labels[k] == v for k, v in service["spec"]["selector"].items())
        )
        policy = yaml.safe_load(
            (
                ROOT
                / "seaweedfs/network-policy-seaweedfs-allow-ingress-from-longhorn.yaml"
            ).read_text()
        )
        self.assertTrue(
            any(
                {"protocol": "TCP", "port": 8333} in rule["ports"]
                and any(
                    source.get("namespaceSelector", {})
                    .get("matchLabels", {})
                    .get("kubernetes.io/metadata.name")
                    == "longhorn-system"
                    for source in rule["from"]
                )
                for rule in policy["spec"]["ingress"]
            )
        )

    def test_current_dr_cycle_and_proposed_break_are_explicit(self):
        """Current dr cycle and proposed break are explicit."""
        graph = yaml.safe_load((ROOT / "docs/startup/dependencies.yaml").read_text())

        def order(extra):
            dependencies = {node: set() for node in graph["nodes"]}
            for edge in graph["edges"] + extra:
                dependencies[edge["to"]].add(edge["from"])
            return list(graphlib.TopologicalSorter(dependencies).static_order())

        scenarios = graph["recovery_scenarios"]
        with self.assertRaises(graphlib.CycleError):
            order(scenarios["current_public_s3_geoip_loss"]["extra_edges"])
        self.assertTrue(order(scenarios["prepared_direct_s3"]["extra_edges"]))
        self.assertEqual(
            scenarios["prepared_direct_s3"]["endpoint"], self.plan["new_endpoint"]
        )
        for scenario in scenarios.values():
            for source in scenario["evidence"]:
                self.assertTrue((ROOT / source).is_file())


if __name__ == "__main__":
    unittest.main()
