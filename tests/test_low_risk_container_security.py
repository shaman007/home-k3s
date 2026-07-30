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

    def test_connectivity_exporter_keeps_image_compatible_uid(self):
        path = "connectivity-exporter/deployment-connectivity-exporter.yaml"
        pod_spec = load_yaml(path)["spec"]["template"]["spec"]
        security = pod_spec["containers"][0]["securityContext"]

        self.assertFalse(security["allowPrivilegeEscalation"])
        self.assertEqual(["ALL"], security["capabilities"]["drop"])
        self.assertTrue(security["readOnlyRootFilesystem"])
        self.assertEqual("RuntimeDefault", security["seccompProfile"]["type"])
        self.assertNotIn("runAsUser", security)
        self.assertNotIn("runAsNonRoot", security)

    def test_headlamp_tmp_fits_extracted_frontend(self):
        pod_spec = load_yaml("headlamp/deployment-headlamp.yaml")["spec"]["template"]["spec"]
        tmp = next(volume for volume in pod_spec["volumes"] if volume["name"] == "tmp")

        self.assertEqual("64Mi", tmp["emptyDir"]["sizeLimit"])

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

    def test_exporters_use_read_only_root_filesystems(self):
        workload_specs = (
            (
                "metrics/kubernetes-node-exporter/daemon-set-node-exporter.yaml",
                "node-exporter",
                65534,
            ),
            ("clamav/deployment-clamav.yaml", "exporter", None),
            ("your-spotify/stateful-set-mongodb.yaml", "mongo-exporter", 65535),
        )

        for path, container_name, uid in workload_specs:
            with self.subTest(path=path, container=container_name):
                pod_spec = load_yaml(path)["spec"]["template"]["spec"]
                container = next(
                    item
                    for item in pod_spec["containers"]
                    if item["name"] == container_name
                )
                security = container["securityContext"]

                self.assertFalse(pod_spec["automountServiceAccountToken"])
                self.assertFalse(security["allowPrivilegeEscalation"])
                self.assertEqual(["ALL"], security["capabilities"]["drop"])
                self.assertTrue(security["readOnlyRootFilesystem"])
                self.assertTrue(security["runAsNonRoot"])
                if uid is not None:
                    self.assertEqual(uid, security["runAsUser"])

    def test_redis_exporter_sidecars_are_read_only(self):
        paths = (
            "argocd/application-redis.yaml",
            "argocd/application-redis-dawarich.yaml",
            "argocd/application-redis-mail.yaml",
            "argocd/application-redis-mastodon.yaml",
            "argocd/application-redis-wordpress.yaml",
        )

        for path in paths:
            with self.subTest(path=path):
                application = load_yaml(path)
                values = yaml.safe_load(application["spec"]["source"]["helm"]["values"])
                security = values["redisExporter"]["securityContext"]

                self.assertFalse(security["allowPrivilegeEscalation"])
                self.assertEqual(["ALL"], security["capabilities"]["drop"])
                self.assertTrue(security["readOnlyRootFilesystem"])
                self.assertTrue(security["runAsNonRoot"])

    def test_redis_operator_uses_chart_supported_restricted_context(self):
        application = load_yaml("argocd/application-redis-operator.yaml")
        values = yaml.safe_load(application["spec"]["source"]["helm"]["values"])
        pod_security = values["podSecurityContext"]
        security = values["securityContext"]

        self.assertTrue(pod_security["runAsNonRoot"])
        self.assertEqual(65532, pod_security["runAsUser"])
        self.assertEqual("RuntimeDefault", pod_security["seccompProfile"]["type"])
        self.assertFalse(security["allowPrivilegeEscalation"])
        self.assertEqual(["ALL"], security["capabilities"]["drop"])
        self.assertTrue(security["readOnlyRootFilesystem"])
        self.assertTrue(security["runAsNonRoot"])


if __name__ == "__main__":
    unittest.main()
