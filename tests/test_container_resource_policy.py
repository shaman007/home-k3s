"""Verify resource request and limit policy checks for repository workloads."""

import importlib.util
from pathlib import Path
import unittest
import json

import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "container_resources", ROOT / "tools/ci/check-container-resources.py"
)
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


class ContainerResourcePolicyTests(unittest.TestCase):
    """Check resource policy defaults, explicit requirements, and operator-created templates."""
    def workload(self, resources=None, init=None):
        """Build a Deployment with configurable application and init-container resources."""
        return {
            "kind": "Deployment",
            "metadata": {"name": "test"},
            "spec": {
                "template": {
                    "spec": {
                        "containers": [{"name": "app", "resources": resources or {}}],
                        "initContainers": init or [],
                    }
                }
            },
        }

    def defaults(self, namespace="app", cpu=None):
        """Build namespace admission defaults with an optional CPU limit."""
        limits = {
            "type": "Container",
            "defaultRequest": {"memory": "64Mi", "cpu": "10m"},
            "default": {"memory": "256Mi"},
        }
        if cpu:
            limits["default"]["cpu"] = cpu
        return {
            "kind": "LimitRange",
            "metadata": {"name": "defaults", "namespace": namespace},
            "spec": {"limits": [limits]},
        }

    def test_operator_created_template_can_use_namespace_admission_defaults(self):
        """Verify operator created template can use namespace admission defaults."""
        count, errors = policy.check([("app", self.defaults()), ("app", self.workload())])
        self.assertEqual(1, count)
        self.assertEqual([], errors)

    def test_defaults_do_not_leak_between_namespaces(self):
        """Verify defaults do not leak between namespaces."""
        _, errors = policy.check([("app", self.defaults("other")), ("app", self.workload())])
        self.assertEqual(2, len(errors))

    def test_request_alone_does_not_supply_a_memory_limit(self):
        """Verify request alone does not supply a memory limit."""
        _, errors = policy.check([("app", self.workload({"requests": {"memory": "64Mi"}}))])
        self.assertEqual(1, len(errors))
        self.assertIn("memory limits", errors[0])

    def test_cpu_requests_are_allowed_but_quotas_are_rejected(self):
        """Verify CPU requests are allowed but quotas are rejected."""
        resources = {"requests": {"cpu": "100m", "memory": "64Mi"}, "limits": {"memory": "256Mi"}}
        self.assertEqual([], policy.check([("app", self.workload(resources))])[1])
        resources["limits"]["cpu"] = "500m"
        self.assertIn("CPU limit", policy.check([("app", self.workload(resources))])[1][0])

    def test_admission_cannot_reintroduce_cpu_limits(self):
        """Verify admission cannot reintroduce CPU limits."""
        _, errors = policy.check([("app", self.defaults(cpu="1")), ("app", self.workload())])
        self.assertIn("CPU ceiling", errors[0])

    def test_gpu_operator_resources_cannot_hide_cpu_limits_in_custom_resources(self):
        """Verify GPU operator resources cannot hide CPU limits in custom resources."""
        document = {
            "kind": "ClusterPolicy",
            "metadata": {"name": "gpu"},
            "spec": {
                "devicePlugin": {
                    "resources": {
                        "requests": {"memory": "64Mi"},
                        "limits": {"cpu": "1", "memory": "256Mi"},
                    }
                }
            },
        }
        _, errors = policy.check([("gpu", document)])
        self.assertEqual(1, len(errors))
        self.assertIn("CPU limit", errors[0])

    def test_empty_configmaps_are_not_workloads(self):
        """Verify empty ConfigMaps are not workloads."""
        self.assertEqual((0, []), policy.check([("storage", {"kind": "ConfigMap", "data": None})]))

    def test_native_longhorn_csi_settings_are_checked(self):
        """Verify native Longhorn CSI settings are checked."""

        settings = {
            "system-managed-csi-components-resource-limits": json.dumps(
                {"csi-attacher": {"requests": {"memory": "64Mi"}}}
            )
        }
        document = {
            "kind": "ConfigMap",
            "metadata": {"name": "settings"},
            "data": {"default-setting.yaml": yaml.safe_dump(settings)},
        }
        _, errors = policy.check([("storage", document)])
        self.assertEqual(1, len(errors))
        self.assertIn("memory limits", errors[0])

    def test_init_containers_require_memory_too(self):
        """Verify init containers require memory too."""
        resources = {"requests": {"memory": "64Mi"}, "limits": {"memory": "256Mi"}}
        count, errors = policy.check([("app", self.workload(resources, [{"name": "init"}]))])
        self.assertEqual(2, count)
        self.assertEqual(2, len(errors))
        self.assertTrue(all("/init:" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
