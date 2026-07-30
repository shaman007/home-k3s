from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]


def load_yaml(path: str) -> dict:
    documents = yaml.safe_load_all((ROOT / path).read_text(encoding="utf-8"))
    return next(document for document in documents if document)


class LowRiskContainerSecurityTest(unittest.TestCase):
    def assert_restricted_container(self, path: str, uid: int, gid: int):
        workload = load_yaml(path)
        pod_spec = workload["spec"]["template"]["spec"]
        container = pod_spec["containers"][0]
        security = container["securityContext"]

        self.assertFalse(security["allowPrivilegeEscalation"], path)
        self.assertEqual(["ALL"], security["capabilities"]["drop"], path)
        self.assertTrue(security["readOnlyRootFilesystem"], path)
        self.assertTrue(security["runAsNonRoot"], path)
        self.assertEqual(uid, security["runAsUser"], path)
        self.assertEqual(gid, security["runAsGroup"], path)
        seccomp = security.get("seccompProfile", pod_spec.get("securityContext", {}).get("seccompProfile"))
        self.assertEqual("RuntimeDefault", seccomp["type"], path)

    def test_stateless_workloads_have_explicit_restricted_contexts(self):
        workloads = (
            ("connectivity-exporter/deployment-connectivity-exporter.yaml", 65534, 65534, 65534),
            ("canitiser/deployment-ca-report-ui.yaml", 10001, 100, 100),
            ("headlamp/deployment-headlamp.yaml", 100, 101, 101),
            ("unifi/poller/deployment-unifi-poller.yaml", 65532, 65532, None),
        )

        for path, uid, gid, fs_group in workloads:
            with self.subTest(path=path):
                self.assert_restricted_container(path, uid, gid)
                if fs_group is not None:
                    pod_spec = load_yaml(path)["spec"]["template"]["spec"]
                    self.assertEqual(fs_group, pod_spec["securityContext"]["fsGroup"])
                    self.assertEqual(
                        "OnRootMismatch",
                        pod_spec["securityContext"]["fsGroupChangePolicy"],
                    )

    def test_high_port_nginx_workloads_run_without_root(self):
        paths = (
            "metrics/deployment-external-access-analytics-exporter.yaml",
            "metrics/deployment-finance-ticker-exporter.yaml",
            "metrics/deployment-platform-health-exporter.yaml",
            "synapse/deployment-nginx-matrix.yaml",
            "wordpress/deployment-wordpress-analytics-exporter.yaml",
        )

        for path in paths:
            with self.subTest(path=path):
                self.assert_restricted_container(path, 101, 101)
                pod_spec = load_yaml(path)["spec"]["template"]["spec"]
                self.assertFalse(pod_spec["automountServiceAccountToken"], path)
                self.assertEqual(101, pod_spec["securityContext"]["fsGroup"], path)

    def test_non_api_workloads_do_not_mount_service_account_tokens(self):
        paths = (
            "connectivity-exporter/deployment-connectivity-exporter.yaml",
            "unifi/poller/deployment-unifi-poller.yaml",
        )

        for path in paths:
            with self.subTest(path=path):
                pod_spec = load_yaml(path)["spec"]["template"]["spec"]
                self.assertFalse(pod_spec["automountServiceAccountToken"], path)

    def test_reloader_uses_chart_supported_restricted_context(self):
        application = load_yaml("argocd/application-reloader.yaml")
        values = yaml.safe_load(application["spec"]["source"]["helm"]["values"])
        reloader = values["reloader"]
        security = reloader["deployment"]["containerSecurityContext"]

        self.assertTrue(reloader["readOnlyRootFileSystem"])
        self.assertFalse(security["allowPrivilegeEscalation"])
        self.assertEqual(["ALL"], security["capabilities"]["drop"])
        self.assertTrue(security["readOnlyRootFilesystem"])


if __name__ == "__main__":
    unittest.main()
