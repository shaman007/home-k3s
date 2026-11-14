"""Check reviewed security contexts and writable storage for monitoring containers."""

import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def load_yaml(path: str) -> dict:
    """Read a repository manifest with the safe YAML loader."""
    return yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))


def container_by_name(pod_spec: dict, name: str, section: str = "containers") -> dict:
    """Select a named regular or init container from the pod specification."""
    return next(container for container in pod_spec[section] if container["name"] == name)


class MonitoringContainerSecurityTest(unittest.TestCase):
    """Require restricted monitoring containers and explicit writable state volumes."""
    def assert_restricted(self, container: dict, uid: int):
        """Require a restricted container context with its reviewed nonroot user."""
        security = container["securityContext"]

        self.assertFalse(security["allowPrivilegeEscalation"])
        self.assertEqual(["ALL"], security["capabilities"]["drop"])
        self.assertTrue(security["readOnlyRootFilesystem"])
        self.assertTrue(security["runAsNonRoot"])
        self.assertEqual(uid, security["runAsUser"])

    def test_monitoring_containers_have_read_only_roots(self):
        """Verify monitoring containers have read only roots."""
        workloads = (
            (
                "metrics/kubernetes-prometheus/deployment-alertmanager.yaml",
                (("alertmanager", 65534),),
            ),
            (
                "metrics/kubernetes-prometheus/deployment-prometheus-deployment.yaml",
                (("prometheus", 65534),),
            ),
            ("thanos/stateful-set-thanos-receive.yaml", (("thanos", 1001),)),
            ("thanos/deployment-thanos-querier.yaml", (("thanos", 1001),)),
            ("thanos/deployment-thanos-compactor.yaml", (("thanos", 1001),)),
            ("thanos/deployment-thanos-store-gateway.yaml", (("thanos", 1001),)),
        )

        for path, expected_containers in workloads:
            pod_spec = load_yaml(path)["spec"]["template"]["spec"]
            self.assertEqual(
                "RuntimeDefault", pod_spec["securityContext"]["seccompProfile"]["type"]
            )
            for name, uid in expected_containers:
                with self.subTest(path=path, container=name):
                    self.assert_restricted(container_by_name(pod_spec, name), uid)

    def test_monitoring_state_uses_explicit_volumes(self):
        """Verify monitoring state uses explicit volumes."""
        workloads = (
            (
                "metrics/kubernetes-prometheus/deployment-alertmanager.yaml",
                "alertmanager",
                "/alertmanager",
            ),
            (
                "metrics/kubernetes-prometheus/deployment-prometheus-deployment.yaml",
                "prometheus",
                "/prometheus/",
            ),
            ("thanos/deployment-thanos-compactor.yaml", "thanos", "/data/"),
            ("thanos/deployment-thanos-store-gateway.yaml", "thanos", "/data/"),
            ("thanos/stateful-set-thanos-receive.yaml", "thanos", "/data"),
        )

        for path, container_name, state_path in workloads:
            with self.subTest(path=path, container=container_name):
                pod_spec = load_yaml(path)["spec"]["template"]["spec"]
                container = container_by_name(pod_spec, container_name)
                mount_paths = {mount["mountPath"] for mount in container["volumeMounts"]}
                self.assertIn(state_path, mount_paths)

    def test_ownership_init_containers_keep_only_required_capabilities(self):
        """Verify ownership init containers keep only required capabilities."""
        paths = (
            "metrics/kubernetes-prometheus/deployment-prometheus-deployment.yaml",
            "thanos/deployment-thanos-compactor.yaml",
            "thanos/deployment-thanos-store-gateway.yaml",
        )

        for path in paths:
            with self.subTest(path=path):
                pod_spec = load_yaml(path)["spec"]["template"]["spec"]
                init_name = "fix-perms" if "prometheus" in path else "volume-mount-hack"
                init = container_by_name(pod_spec, init_name, "initContainers")
                security = init["securityContext"]

                self.assertFalse(security["allowPrivilegeEscalation"])
                self.assertEqual(["ALL"], security["capabilities"]["drop"])
                self.assertEqual(["CHOWN"], security["capabilities"]["add"])
                self.assertTrue(security["readOnlyRootFilesystem"])
                self.assertEqual(0, security["runAsUser"])

    def test_only_prometheus_mounts_a_service_account_token(self):
        """Verify only Prometheus mounts a service account token."""
        false_paths = (
            "metrics/kubernetes-prometheus/deployment-alertmanager.yaml",
            "thanos/deployment-thanos-querier.yaml",
            "thanos/deployment-thanos-compactor.yaml",
            "thanos/deployment-thanos-store-gateway.yaml",
            "thanos/stateful-set-thanos-receive.yaml",
        )

        for path in false_paths:
            pod_spec = load_yaml(path)["spec"]["template"]["spec"]
            self.assertFalse(pod_spec["automountServiceAccountToken"], path)

        prometheus = load_yaml(
            "metrics/kubernetes-prometheus/deployment-prometheus-deployment.yaml"
        )["spec"]["template"]["spec"]
        self.assertTrue(prometheus["automountServiceAccountToken"])


if __name__ == "__main__":
    unittest.main()
