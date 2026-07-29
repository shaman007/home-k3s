from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
ARGOCD = ROOT / "argocd"
CLUSTER = "https://kubernetes.default.svc"

PROJECT_APPLICATIONS = {
    "backup-rsync", "bitwarden", "ca-scanner", "clamav", "collabora",
    "comfyui", "conduit", "convertx", "dawarich", "harbor",
    "harbor-custom", "harbor-network-policy", "hister", "homeassistant",
    "image-builder", "immich", "karakeep", "keycloak", "lenka", "mail",
    "mastodon", "mastodon-custom", "mempalace", "minecraft", "nextcloud",
    "ollama", "ollama-small", "open-terminal", "open-webui", "plex",
    "stirling-pdf", "wordpress", "year", "your-spotify",
}

PROJECT_PLATFORM = {
    "argocd-deploy", "cilium", "coredns-custom", "external-secrets",
    "external-secrets-network-policy", "gpu-operator", "headlamp", "metallb",
    "metallb-config", "metrics-server", "metrics-server-network-policy",
    "namespaces", "reloader", "traefik", "traefik-network-policy", "vault",
    "vault-custom", "vault-network-policy",
}

PROJECT_STORAGE = {
    "kubernetes-snapshot-controller", "longhorn", "longhorn-custom",
    "ot-operators-network-policy", "redis", "redis-dawarich", "redis-mail",
    "redis-mastodon", "redis-operator", "redis-wordpress", "seaweedfs",
}

PROJECT_OBSERVABILITY = {
    "alloy", "connectivity-exporter-core",
    "connectivity-exporter-network-policy", "elastic-stack-custom",
    "elastic-stack-network-policy", "elastic-system",
    "elastic-system-network-policy", "external-access-analytics",
    "finance-ticker", "grafana", "kube-node-exporter", "kube-state-metrics",
    "kubernetes-prometheus", "logs-check", "loki", "loki-external-secrets",
    "loki-network-policy", "monitoring-ingress", "monitoring-network-policy",
    "my-adapter", "platform-health", "thanos", "unifi-exporter",
}

PROJECT_MEMBERS = {
    "applications": PROJECT_APPLICATIONS,
    "platform": PROJECT_PLATFORM,
    "storage": PROJECT_STORAGE,
    "observability": PROJECT_OBSERVABILITY,
}

EXPECTED_CLUSTER_PERMISSIONS = {
    "applications": {
        ("", "Namespace"),
        ("", "PersistentVolume"),
        ("external-secrets.io", "ClusterSecretStore"),
        ("rbac.authorization.k8s.io", "ClusterRole"),
        ("rbac.authorization.k8s.io", "ClusterRoleBinding"),
    },
    "platform": {
        ("", "Namespace"),
        ("admissionregistration.k8s.io", "ValidatingWebhookConfiguration"),
        ("apiextensions.k8s.io", "CustomResourceDefinition"),
        ("apiregistration.k8s.io", "APIService"),
        ("networking.k8s.io", "IngressClass"),
        ("nvidia.com", "ClusterPolicy"),
        ("rbac.authorization.k8s.io", "ClusterRole"),
        ("rbac.authorization.k8s.io", "ClusterRoleBinding"),
        ("scheduling.k8s.io", "PriorityClass"),
    },
    "storage": {
        ("apiextensions.k8s.io", "CustomResourceDefinition"),
        ("rbac.authorization.k8s.io", "ClusterRole"),
        ("rbac.authorization.k8s.io", "ClusterRoleBinding"),
        ("scheduling.k8s.io", "PriorityClass"),
    },
    "observability": {
        ("admissionregistration.k8s.io", "ValidatingWebhookConfiguration"),
        ("apiextensions.k8s.io", "CustomResourceDefinition"),
        ("rbac.authorization.k8s.io", "ClusterRole"),
        ("rbac.authorization.k8s.io", "ClusterRoleBinding"),
    },
}

CLUSTER_SCOPED_KINDS = {
    "APIService", "CSIDriver", "ClusterRole", "ClusterRoleBinding",
    "ClusterSecretStore", "CustomResourceDefinition", "IngressClass",
    "MutatingWebhookConfiguration", "Namespace", "PersistentVolume",
    "PriorityClass", "RuntimeClass", "StorageClass",
    "ValidatingWebhookConfiguration", "VolumeSnapshotClass",
}


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def application_documents() -> dict[str, dict]:
    applications = {}
    for path in ARGOCD.glob("application-*.yaml"):
        document = load_yaml(path)
        if document.get("kind") == "Application":
            applications[document["metadata"]["name"]] = document
    return applications


def source_repositories(application: dict) -> set[str]:
    sources = application["spec"].get("sources")
    if sources is None:
        sources = [application["spec"]["source"]]
    return {source["repoURL"] for source in sources}


def api_group(document: dict) -> str:
    api_version = document.get("apiVersion", "")
    return api_version.split("/", 1)[0] if "/" in api_version else ""


class ArgoCdProjectsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.applications = application_documents()

    def test_every_application_is_assigned_exactly_once(self):
        expected = set().union(*PROJECT_MEMBERS.values())
        self.assertEqual(set(self.applications), expected)

        for project, members in PROJECT_MEMBERS.items():
            for name in members:
                self.assertEqual(self.applications[name]["spec"]["project"], project)

        self.assertNotIn(
            "default",
            {application["spec"]["project"] for application in self.applications.values()},
        )
        self.assertNotIn(
            "workloads",
            {application["spec"]["project"] for application in self.applications.values()},
        )

    def test_projects_use_only_required_sources_and_destinations(self):
        for project_name, members in PROJECT_MEMBERS.items():
            project = load_yaml(
                ARGOCD / f"application-project-{project_name}.yaml"
            )
            self.assertEqual(project["kind"], "AppProject")
            self.assertEqual(project["metadata"]["name"], project_name)
            self.assertEqual(
                project["metadata"]["annotations"]["argocd.argoproj.io/sync-wave"],
                "-1",
            )

            expected_repositories = set()
            expected_destinations = set()
            for name in members:
                application = self.applications[name]
                expected_repositories.update(source_repositories(application))
                namespace = application["spec"]["destination"].get("namespace")
                self.assertTrue(namespace, f"{name} must have an explicit namespace")
                expected_destinations.add((CLUSTER, namespace))

            self.assertEqual(set(project["spec"]["sourceRepos"]), expected_repositories)
            self.assertEqual(
                {
                    (destination["server"], destination["namespace"])
                    for destination in project["spec"]["destinations"]
                },
                expected_destinations,
            )

    def test_cluster_permissions_are_explicit(self):
        for project_name, expected in EXPECTED_CLUSTER_PERMISSIONS.items():
            project = load_yaml(
                ARGOCD / f"application-project-{project_name}.yaml"
            )
            actual = {
                (permission["group"], permission["kind"])
                for permission in project["spec"]["clusterResourceWhitelist"]
            }
            self.assertEqual(actual, expected)
            self.assertNotIn(("*", "*"), actual)

    def test_repository_manifests_fit_project_cluster_permissions(self):
        for project_name, members in PROJECT_MEMBERS.items():
            allowed = EXPECTED_CLUSTER_PERMISSIONS[project_name]
            for name in members:
                application = self.applications[name]
                source = application["spec"].get("source")
                if not source or "path" not in source:
                    continue

                source_path = ROOT / source["path"]
                for pattern in ("*.yaml", "*.yml"):
                    for manifest in source_path.rglob(pattern):
                        for document in yaml.safe_load_all(
                            manifest.read_text(encoding="utf-8")
                        ):
                            if not isinstance(document, dict):
                                continue
                            kind = document.get("kind", "")
                            if not (
                                kind.startswith("Cluster")
                                or kind in CLUSTER_SCOPED_KINDS
                            ):
                                continue
                            permission = (api_group(document), kind)
                            self.assertIn(
                                permission,
                                allowed,
                                f"{manifest.relative_to(ROOT)} requires {permission} "
                                f"from project {project_name}",
                            )


if __name__ == "__main__":
    unittest.main()
