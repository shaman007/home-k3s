"""Guard Registry namespace isolation and Reloader's unused batch permissions."""

from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_SA = {"kind": "ServiceAccount", "name": "traefik-registry", "namespace": "traefik"}


def load(relative):
    """Load one repository manifest."""
    return yaml.safe_load((ROOT / relative).read_text(encoding="utf-8"))


def chart_values(application):
    """Decode an Application's inline Helm values."""
    return yaml.safe_load(load(f"argocd/application-{application}.yaml")["spec"]["source"]["helm"]["values"])


def registry_authorized(group, resource, verb, namespace=None):
    """Evaluate additive RBAC grants to the Registry service account."""
    documents = chart_values("traefik-registry")["extraObjects"] + [
        load("harbor/role-traefik-registry.yaml"),
        load("harbor/role-binding-traefik-registry.yaml"),
    ]
    roles = {
        (doc["kind"], doc["metadata"].get("namespace"), doc["metadata"]["name"]): doc
        for doc in documents if doc["kind"] in {"Role", "ClusterRole"}
    }
    for binding in documents:
        if binding["kind"] not in {"RoleBinding", "ClusterRoleBinding"}:
            continue
        if REGISTRY_SA not in binding["subjects"]:
            continue
        scope = binding["metadata"].get("namespace")
        if binding["kind"] == "RoleBinding" and (namespace is None or scope != namespace):
            continue
        ref = binding["roleRef"]
        role = roles[(ref["kind"], scope if ref["kind"] == "Role" else None, ref["name"])]
        for rule in role["rules"]:
            if (group in rule["apiGroups"] or "*" in rule["apiGroups"]) and (
                resource in rule["resources"] or "*" in rule["resources"]
            ) and (verb in rule["verbs"] or "*" in rule["verbs"]):
                return True
    return False


class RegistryReloaderRbacTest(unittest.TestCase):
    """Preserve provider discovery while rejecting unrelated data access."""

    def test_registry_keeps_ingress_class_discovery(self):
        """Namespaced chart mode would disable processing ingressClassName references."""
        values = chart_values("traefik-registry")
        self.assertFalse(values["rbac"]["enabled"])
        self.assertFalse(values["rbac"]["namespaced"])
        self.assertEqual(["harbor"], values["providers"]["kubernetesIngress"]["namespaces"])
        self.assertFalse(any("disableclusterscoperesources=true" in arg.lower()
                             for arg in values["additionalArguments"]))
        self.assertTrue(values["ingressClass"]["enabled"])
        for resource, group in [("ingressclasses", "networking.k8s.io"), ("nodes", "")]:
            for verb in ["get", "list", "watch"]:
                self.assertTrue(registry_authorized(group, resource, verb))

    def test_registry_data_access_is_only_in_harbor(self):
        """Required watches work, without a cluster-wide or cross-namespace grant."""
        for resource, group in [("services", ""), ("secrets", ""),
                                ("endpointslices", "discovery.k8s.io"),
                                ("ingresses", "networking.k8s.io")]:
            for verb in ["list", "watch"]:
                with self.subTest(resource=resource, verb=verb):
                    self.assertTrue(registry_authorized(group, resource, verb, "harbor"))
                    self.assertFalse(registry_authorized(group, resource, verb))
                    for namespace in ["traefik", "argocd", "openbao"]:
                        self.assertFalse(registry_authorized(group, resource, verb, namespace))
        self.assertTrue(registry_authorized("", "secrets", "get", "harbor"))
        self.assertFalse(registry_authorized("", "secrets", "get", "argocd"))
        self.assertTrue(registry_authorized("networking.k8s.io", "ingresses/status", "update", "harbor"))
        self.assertFalse(registry_authorized("networking.k8s.io", "ingresses/status", "update", "traefik"))
        self.assertFalse(registry_authorized("batch", "jobs", "create", "harbor"))

    def test_registry_retains_existing_cluster_binding_identity(self):
        """Replacing existing identities avoids leaving a broad obsolete binding."""
        objects = chart_values("traefik-registry")["extraObjects"]
        for kind in ["ClusterRole", "ClusterRoleBinding"]:
            self.assertEqual(["traefik-registry-traefik"], [doc["metadata"]["name"]
                             for doc in objects if doc["kind"] == kind])

    def test_reloader_disables_batch_without_disabling_rollouts(self):
        """Keep Deployment/DaemonSet/StatefulSet reloads and secret/configmap watches."""
        values = chart_values("reloader")["reloader"]
        self.assertTrue(values["ignoreJobs"])
        self.assertTrue(values["ignoreCronJobs"])
        self.assertFalse(values.get("ignoreSecrets", False))
        self.assertFalse(values.get("ignoreConfigMaps", False))
        self.assertTrue(values.get("watchGlobally", True))
        self.assertEqual("annotations", values["reloadStrategy"])


if __name__ == "__main__":
    unittest.main()
