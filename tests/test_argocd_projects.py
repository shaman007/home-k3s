from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
ARGOCD = ROOT / "argocd"
CLUSTER = "https://kubernetes.default.svc"
REPOSITORY = "https://github.com/shaman007/home-k3s.git"

PROJECT_APPLICATIONS = {
    "backup-rsync", "bitwarden", "ca-scanner", "clamav", "collabora",
    "comfyui", "conduit", "convertx", "dawarich", "harbor",
    "harbor-custom", "harbor-network-policy", "hister", "homeassistant",
    "image-builder", "immich", "karakeep", "keycloak", "mail",
    "mastodon", "mastodon-custom", "mempalace", "minecraft", "nextcloud",
    "ollama", "ollama-small", "open-terminal", "open-webui", "plex",
    "stirling-pdf", "wordpress", "year", "your-spotify",
}

PROJECT_PLATFORM = {
    "argocd-deploy", "argocd-install", "cert-manager", "cilium", "coredns-custom",
    "external-secrets", "external-secrets-network-policy", "gpu-operator",
    "headlamp", "metallb",
    "metallb-config", "metrics-server", "metrics-server-network-policy",
    "reloader", "traefik", "traefik-acme-exporter", "traefik-network-policy", "vault",
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

PROJECT_ACCESS_MANAGEMENT = {"lenka"}
PROJECT_NAMESPACE_MANAGEMENT = {"namespaces"}

PROJECT_MEMBERS = {
    "applications": PROJECT_APPLICATIONS,
    "platform": PROJECT_PLATFORM,
    "storage": PROJECT_STORAGE,
    "observability": PROJECT_OBSERVABILITY,
    "access-management": PROJECT_ACCESS_MANAGEMENT,
    "namespace-management": PROJECT_NAMESPACE_MANAGEMENT,
}

SELF_HEAL_EXEMPT_APPLICATIONS = {"lenka"}

PRUNE_REQUIRED_APPLICATIONS = {
    "alloy", "ca-scanner", "clamav", "comfyui", "connectivity-exporter-network-policy",
    "convertx", "coredns-custom", "elastic-stack-network-policy",
    "elastic-system-network-policy", "external-access-analytics",
    "external-secrets-network-policy", "finance-ticker", "harbor-network-policy",
    "headlamp", "hister", "homeassistant", "image-builder", "kube-node-exporter",
    "kube-state-metrics", "logs-check", "loki-network-policy", "metallb-config",
    "metrics-server-network-policy", "monitoring-ingress", "monitoring-network-policy",
    "open-terminal", "ot-operators-network-policy", "platform-health",
    "traefik-network-policy", "unifi-exporter", "vault-network-policy", "year",
}

EXTRA_DESTINATIONS_BY_APPLICATION = {
    "cilium": {"cilium-secrets"},
    "my-adapter": {"kube-system"},
}

PROJECT_SYNC_WAVES = {
    "namespace-management": "-2",
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
        ("admissionregistration.k8s.io", "MutatingWebhookConfiguration"),
        ("admissionregistration.k8s.io", "ValidatingWebhookConfiguration"),
        ("apiextensions.k8s.io", "CustomResourceDefinition"),
        ("apiregistration.k8s.io", "APIService"),
        ("cert-manager.io", "ClusterIssuer"),
        ("networking.k8s.io", "IngressClass"),
        ("nvidia.com", "ClusterPolicy"),
        ("rbac.authorization.k8s.io", "ClusterRole"),
        ("rbac.authorization.k8s.io", "ClusterRoleBinding"),
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
    "access-management": {
        ("", "Namespace"),
        ("rbac.authorization.k8s.io", "ClusterRole"),
        ("rbac.authorization.k8s.io", "ClusterRoleBinding"),
    },
    "namespace-management": {
        ("", "Namespace"),
        ("scheduling.k8s.io", "PriorityClass"),
    },
}

EXPECTED_RESTRICTED_NAMESPACE_PERMISSIONS = {
    "access-management": {
        ("", "Secret"),
        ("", "ServiceAccount"),
        ("rbac.authorization.k8s.io", "RoleBinding"),
    },
    "namespace-management": {
        ("", "LimitRange"),
        ("", "ResourceQuota"),
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


def repository_documents(application: dict):
    sources = application["spec"].get("sources")
    if sources is None:
        sources = [application["spec"]["source"]]

    for source in sources:
        if source.get("repoURL") != REPOSITORY or "path" not in source:
            continue
        source_path = ROOT / source["path"]
        for pattern in ("*.yaml", "*.yml"):
            for manifest in source_path.rglob(pattern):
                for document in yaml.safe_load_all(
                    manifest.read_text(encoding="utf-8")
                ):
                    if isinstance(document, dict):
                        yield manifest, document


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
                PROJECT_SYNC_WAVES.get(project_name, "-1"),
            )

            expected_repositories = set()
            expected_destinations = set()
            for name in members:
                application = self.applications[name]
                expected_repositories.update(source_repositories(application))
                namespace = application["spec"]["destination"].get("namespace")
                self.assertTrue(namespace, f"{name} must have an explicit namespace")
                expected_destinations.add((CLUSTER, namespace))
                expected_destinations.update(
                    (CLUSTER, extra_namespace)
                    for extra_namespace in EXTRA_DESTINATIONS_BY_APPLICATION.get(
                        name, set()
                    )
                )
                expected_destinations.update(
                    (CLUSTER, document["metadata"]["namespace"])
                    for _, document in repository_documents(application)
                    if (document.get("metadata") or {}).get("namespace")
                )

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

    def test_cross_namespace_projects_restrict_namespaced_kinds(self):
        for project_name, expected in EXPECTED_RESTRICTED_NAMESPACE_PERMISSIONS.items():
            project = load_yaml(
                ARGOCD / f"application-project-{project_name}.yaml"
            )
            actual = {
                (permission["group"], permission["kind"])
                for permission in project["spec"]["namespaceResourceWhitelist"]
            }
            self.assertEqual(actual, expected)
            self.assertNotIn(("*", "*"), actual)

            for name in PROJECT_MEMBERS[project_name]:
                for manifest, document in repository_documents(
                    self.applications[name]
                ):
                    if not (document.get("metadata") or {}).get("namespace"):
                        continue
                    permission = (api_group(document), document.get("kind", ""))
                    self.assertIn(
                        permission,
                        expected,
                        f"{manifest.relative_to(ROOT)} requires {permission} "
                        f"from project {project_name}",
                    )

    def test_default_project_is_bootstrap_only(self):
        project = load_yaml(ARGOCD / "application-project-default.yaml")
        self.assertEqual(project["metadata"]["name"], "default")
        self.assertEqual(
            project["spec"]["sourceRepos"],
            [REPOSITORY],
        )
        self.assertEqual(
            project["spec"]["destinations"],
            [{"server": CLUSTER, "namespace": "argocd"}],
        )
        self.assertEqual(project["spec"]["clusterResourceWhitelist"], [])
        self.assertEqual(
            {
                (permission["group"], permission["kind"])
                for permission in project["spec"]["namespaceResourceWhitelist"]
            },
            {
                ("argoproj.io", "Application"),
                ("argoproj.io", "AppProject"),
            },
        )

        bootstrap = load_yaml(ARGOCD / "applications-manager.yaml")
        self.assertEqual(bootstrap["metadata"]["name"], "argocd-applications")
        self.assertEqual(bootstrap["spec"]["project"], "default")
        self.assertEqual(
            source_repositories(bootstrap),
            set(project["spec"]["sourceRepos"]),
        )
        self.assertEqual(
            bootstrap["spec"]["destination"],
            project["spec"]["destinations"][0],
        )

    def test_git_sources_use_explicit_main_branch(self):
        manifests = list(self.applications.values())
        manifests.append(load_yaml(ARGOCD / "applications-manager.yaml"))

        for application in manifests:
            sources = application["spec"].get("sources")
            if sources is None:
                sources = [application["spec"]["source"]]
            for source in sources:
                if source["repoURL"] != REPOSITORY:
                    continue
                self.assertEqual(
                    source["targetRevision"],
                    "main",
                    f'{application["metadata"]["name"]} must target main',
                )

    def test_automated_applications_self_heal_live_drift(self):
        for name, application in self.applications.items():
            automated = application["spec"]["syncPolicy"]["automated"]
            if name in SELF_HEAL_EXEMPT_APPLICATIONS:
                self.assertFalse(automated.get("selfHeal", False))
                continue
            self.assertTrue(automated.get("selfHeal", False), name)

    def test_stateless_and_companion_applications_prune(self):
        for name in PRUNE_REQUIRED_APPLICATIONS:
            automated = self.applications[name]["spec"]["syncPolicy"]["automated"]
            self.assertTrue(automated.get("prune", False), name)

    def test_self_healing_respects_ignored_runtime_fields(self):
        for name, application in self.applications.items():
            if not application["spec"].get("ignoreDifferences"):
                continue
            sync_options = application["spec"]["syncPolicy"].get("syncOptions", [])
            self.assertIn("RespectIgnoreDifferences=true", sync_options, name)

    def test_chart_only_failed_sync_can_self_heal_after_project_change(self):
        application = self.applications["my-adapter"]
        automated = application["spec"]["syncPolicy"]["automated"]

        self.assertTrue(automated["selfHeal"])

    def test_repository_manifests_fit_project_cluster_permissions(self):
        for project_name, members in PROJECT_MEMBERS.items():
            allowed = EXPECTED_CLUSTER_PERMISSIONS[project_name]
            for name in members:
                application = self.applications[name]
                for manifest, document in repository_documents(application):
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
