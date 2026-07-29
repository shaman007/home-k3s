from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
ARGOCD = ROOT / "argocd"
PROJECT = ARGOCD / "application-project-workloads.yaml"
REPOSITORY = "https://github.com/shaman007/home-k3s.git"

WORKLOAD_APPLICATIONS = {
    "backup-rsync": "backup-rsync",
    "bitwarden": "bitwarden",
    "ca-scanner": "ca-scanner",
    "clamav": "clamav",
    "conduit": "matrix",
    "connectivity-exporter-core": "connectivity-exporter",
    "connectivity-exporter-network-policy": "connectivity-exporter",
    "convertx": "convertx",
    "dawarich": "dawarich",
    "hister": "hister",
    "homeassistant": "homeassistant",
    "image-builder": "image-builder",
    "karakeep": "karakeep",
    "keycloak": "keycloak",
    "mempalace": "mempalace",
    "minecraft": "minecraft",
    "nextcloud": "nextcloud",
    "ollama": "ollama",
    "ollama-small": "ollama",
    "seaweedfs": "seaweedfs",
    "stirling-pdf": "stirling-pdf",
    "unifi-exporter": "unifi",
    "wordpress": "wordpress",
    "year": "year",
    "your-spotify": "spotify",
}

CLUSTER_SCOPED_KINDS = {
    "APIService",
    "CSIDriver",
    "ClusterRole",
    "ClusterRoleBinding",
    "CustomResourceDefinition",
    "MutatingWebhookConfiguration",
    "Namespace",
    "PersistentVolume",
    "PriorityClass",
    "RuntimeClass",
    "StorageClass",
    "ValidatingWebhookConfiguration",
    "VolumeSnapshotClass",
}


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


class ArgoCdWorkloadsProjectTest(unittest.TestCase):
    def test_project_has_strict_source_destination_and_scope_boundaries(self):
        project = load_yaml(PROJECT)
        self.assertEqual(project["kind"], "AppProject")
        self.assertEqual(project["metadata"]["name"], "workloads")
        self.assertEqual(
            project["metadata"]["annotations"]["argocd.argoproj.io/sync-wave"],
            "-1",
        )
        self.assertEqual(project["spec"]["sourceRepos"], [REPOSITORY])
        self.assertEqual(project["spec"]["clusterResourceWhitelist"], [])

        destinations = {
            (destination["server"], destination["namespace"])
            for destination in project["spec"]["destinations"]
        }
        expected_destinations = {
            ("https://kubernetes.default.svc", namespace)
            for namespace in WORKLOAD_APPLICATIONS.values()
        }
        self.assertEqual(destinations, expected_destinations)

    def test_selected_applications_use_the_workloads_project(self):
        discovered = {}
        for path in ARGOCD.glob("application-*.yaml"):
            document = load_yaml(path)
            if document.get("kind") != "Application":
                continue
            if document["spec"].get("project") != "workloads":
                continue

            name = document["metadata"]["name"]
            discovered[name] = document["spec"]["destination"].get("namespace")
            self.assertEqual(document["spec"]["source"]["repoURL"], REPOSITORY)
            self.assertNotIn("sources", document["spec"])

        self.assertEqual(discovered, WORKLOAD_APPLICATIONS)

    def test_workload_sources_do_not_contain_cluster_scoped_manifests(self):
        for path in ARGOCD.glob("application-*.yaml"):
            application = load_yaml(path)
            if application.get("kind") != "Application":
                continue
            if application["spec"].get("project") != "workloads":
                continue

            source_path = ROOT / application["spec"]["source"]["path"]
            for manifest in source_path.glob("*.yaml"):
                for document in yaml.safe_load_all(manifest.read_text(encoding="utf-8")):
                    if not isinstance(document, dict):
                        continue
                    kind = document.get("kind", "")
                    self.assertFalse(
                        kind.startswith("Cluster") or kind in CLUSTER_SCOPED_KINDS,
                        f"{manifest.relative_to(ROOT)} contains cluster-scoped kind {kind}",
                    )


if __name__ == "__main__":
    unittest.main()
