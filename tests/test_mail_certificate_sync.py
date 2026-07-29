from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]


def load_yaml(path: str) -> dict:
    return yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))


class MailCertificateSyncTest(unittest.TestCase):
    def test_exporter_reads_the_traefik_pvc_without_pod_exec(self):
        cron_job = load_yaml(
            "traefik-acme-exporter/cron-job-sync-letsencrypt-prod.yaml"
        )
        pod_spec = cron_job["spec"]["jobTemplate"]["spec"]["template"]["spec"]
        container = pod_spec["containers"][0]

        self.assertEqual(cron_job["metadata"]["namespace"], "traefik")
        self.assertEqual(pod_spec["serviceAccountName"], "sync-le-tls")
        self.assertIn('"$ACME_PATH"', container["args"][0])
        self.assertNotIn("kubectl exec", container["args"][0])
        self.assertEqual(
            pod_spec["volumes"][0]["persistentVolumeClaim"],
            {"claimName": "traefik", "readOnly": True},
        )
        self.assertTrue(container["volumeMounts"][0]["readOnly"])
        self.assertIn(
            "requiredDuringSchedulingIgnoredDuringExecution",
            pod_spec["affinity"]["podAffinity"],
        )
        self.assertEqual(
            pod_spec["securityContext"],
            {
                "runAsNonRoot": True,
                "runAsUser": 65532,
                "runAsGroup": 65532,
                "fsGroup": 1000,
                "seccompProfile": {"type": "RuntimeDefault"},
            },
        )

    def test_exporter_has_cilium_access_only_to_the_kubernetes_api(self):
        policy = load_yaml(
            "traefik-acme-exporter/"
            "cilium-network-policy-sync-letsencrypt-prod-kube-apiserver.yaml"
        )

        self.assertEqual(policy["metadata"]["namespace"], "traefik")
        self.assertEqual(
            policy["spec"]["endpointSelector"]["matchLabels"],
            {"app.kubernetes.io/name": "sync-letsencrypt-prod"},
        )
        self.assertEqual(policy["spec"]["egress"], [
            {"toEntities": ["kube-apiserver"]},
            {
                "toServices": [{
                    "k8sService": {
                        "namespace": "default",
                        "serviceName": "kubernetes",
                    },
                }],
                "toPorts": [{
                    "ports": [{"port": "443", "protocol": "TCP"}],
                }],
            },
        ])

    def test_exporter_can_patch_only_the_mail_tls_secret(self):
        role = load_yaml("mail/role-sync-le-tls.yaml")
        binding = load_yaml("mail/role-binding-sync-le-tls.yaml")

        self.assertEqual(role["rules"], [{
            "apiGroups": [""],
            "resources": ["secrets"],
            "resourceNames": ["letsencrypt-prod"],
            "verbs": ["get", "patch"],
        }])
        self.assertEqual(binding["subjects"], [{
            "kind": "ServiceAccount",
            "name": "sync-le-tls",
            "namespace": "traefik",
        }])

    def test_traefik_no_longer_grants_mail_pod_exec(self):
        traefik = (ROOT / "argocd/application-traefik.yaml").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("sync-le-tls-traefik-readexec", traefik)
        self.assertNotIn("pods/exec", traefik)

    def test_cert_manager_has_a_cascading_cleanup_finalizer(self):
        application = load_yaml("argocd/application-cert-manager.yaml")
        self.assertEqual(
            application["metadata"]["finalizers"],
            ["resources-finalizer.argocd.argoproj.io"],
        )
        self.assertNotIn("sources", application["spec"])


if __name__ == "__main__":
    unittest.main()
