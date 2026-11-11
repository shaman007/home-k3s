"""Verify OpenBao migration manifests and dependent secret-store configuration."""

from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]


def load_yaml(path: str):
    return yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))


class OpenBaoMigrationTest(unittest.TestCase):
    def test_openbao_release_is_pinned_and_ha_configured(self):
        application = load_yaml("argocd/application-openbao.yaml")
        source = application["spec"]["source"]
        values = yaml.safe_load(source["helm"]["values"])

        self.assertEqual("ghcr.io/openbao/charts", source["repoURL"])
        self.assertEqual("openbao", source["chart"])
        self.assertRegex(source["targetRevision"], r"^\d+\.\d+\.\d+$")
        self.assertEqual("openbao", application["spec"]["destination"]["namespace"])
        self.assertEqual(3, values["server"]["ha"]["replicas"])
        self.assertIn(
            {
                "key": "node-role.kubernetes.io/control-plane",
                "operator": "Exists",
                "effect": "NoSchedule",
            },
            values["server"]["tolerations"],
        )
        self.assertTrue(values["server"]["ha"]["raft"]["enabled"])
        self.assertTrue(values["server"]["ha"]["raft"]["setNodeId"])
        self.assertEqual(
            "https://openbao-api.int.andreybondarenko.com:8200",
            values["server"]["ha"]["apiAddr"],
        )
        self.assertIn(
            'leader_api_addr = "https://openbao-api.int.andreybondarenko.com:8200"',
            values["server"]["ha"]["raft"]["config"],
        )
        self.assertNotIn(
            'leader_api_addr = "https://openbao-0.',
            values["server"]["ha"]["raft"]["config"],
        )
        self.assertEqual(
            {"whenDeleted": "Retain", "whenScaled": "Retain"},
            values["server"]["persistentVolumeClaimRetentionPolicy"],
        )
        self.assertFalse(values["snapshotAgent"]["enabled"])

    def test_backend_uses_public_certificates_without_private_trust(self):
        values = yaml.safe_load(
            load_yaml("argocd/application-openbao.yaml")["spec"]["source"]["helm"]["values"]
        )
        server = values["server"]
        self.assertNotIn("BAO_CACERT", server["extraEnvironmentVars"])
        self.assertEqual(
            "openbao-api.int.andreybondarenko.com",
            server["extraEnvironmentVars"]["BAO_TLS_SERVER_NAME"],
        )
        self.assertEqual(
            [{"type": "secret", "name": "openbao-server-letsencrypt-tls"}], server["extraVolumes"]
        )
        config = server["ha"]["raft"]["config"]
        self.assertNotIn("leader_ca_cert_file", config)
        self.assertNotIn("/openbao-server-tls/", config)
        self.assertEqual(2, config.count("tls_auto_reload = true"))
        self.assertIn('cluster_address = "[::]:8201"', config)
        transport = load_yaml("openbao/servers-transport-openbao-server.yaml")["spec"]
        self.assertEqual("openbao-api.int.andreybondarenko.com", transport["serverName"])
        self.assertNotIn("rootCAs", transport)
        self.assertTrue(load_yaml("openbao/cron-job-vault-pki-renewer.yaml")["spec"]["suspend"])

    def test_ingress_bridge_uses_public_sni_transport(self):
        bridge = load_yaml("openbao/service-openbao-public-tls.yaml")
        self.assertEqual(
            "openbao-openbao-server@kubernetescrd",
            bridge["metadata"]["annotations"][
                "traefik.ingress.kubernetes.io/service.serverstransport"
            ],
        )
        self.assertEqual(
            "https",
            bridge["metadata"]["annotations"][
                "traefik.ingress.kubernetes.io/service.serversscheme"
            ],
        )
        self.assertEqual("true", bridge["spec"]["selector"]["openbao-active"])
        self.assertEqual(8202, bridge["spec"]["ports"][0]["targetPort"])
        for filename in ("openbao/ingress-openbao-ingress-letsencrypt.yaml",):
            ingress = load_yaml(filename)
            self.assertEqual(
                "openbao-public-tls",
                ingress["spec"]["rules"][0]["http"]["paths"][0]["backend"]["service"]["name"],
            )

    def test_openbao_tls_data_is_runtime_managed(self):
        application = load_yaml("argocd/application-openbao-custom.yaml")
        ignored = application["spec"]["ignoreDifferences"]
        self.assertIn(
            {
                "group": "",
                "kind": "Secret",
                "name": "openbao-server-tls",
                "jsonPointers": ["/data"],
            },
            ignored,
        )
        secret = load_yaml("openbao/secret-openbao-server-tls.yaml")
        self.assertEqual({}, secret["data"])
        self.assertEqual("Opaque", secret["type"])

    def test_retired_backend_issuer_cannot_be_recreated_by_bootstrap(self):
        script = (ROOT / "vault/configure-pki-acme.sh").read_text(encoding="utf-8")
        policy = (ROOT / "vault/policy-vault-pki-renewer.hcl").read_text(encoding="utf-8")
        renewer = load_yaml("openbao/cron-job-vault-pki-renewer.yaml")
        self.assertNotIn("vault write pki-root/roles/openbao-server", script)
        self.assertNotIn('path "pki-root/issue/openbao-server"', policy)
        self.assertTrue(renewer["spec"]["suspend"])
        pod = renewer["spec"]["jobTemplate"]["spec"]["template"]["spec"]
        self.assertFalse(pod["automountServiceAccountToken"])
        self.assertNotIn("volumes", pod)
        self.assertNotIn("env", pod["containers"][0])
        self.assertEqual([], load_yaml("openbao/role-vault-pki-renewer.yaml")["rules"])
        self.assertFalse(
            load_yaml("openbao/service-account-vault-pki-renewer.yaml")[
                "automountServiceAccountToken"
            ]
        )
        self.assertNotIn("vault write", script)

    def test_tls_bootstrap_rbac_precedes_certificate_wait(self):
        for path in (
            "openbao/role-vault-pki-renewer.yaml",
            "openbao/role-binding-vault-pki-renewer.yaml",
        ):
            with self.subTest(path=path):
                resource = load_yaml(path)
                self.assertEqual(
                    "-2",
                    resource["metadata"]["annotations"]["argocd.argoproj.io/sync-wave"],
                )

        certificate = load_yaml("openbao/certificate-openbao-ingress-letsencrypt-internal-tls.yaml")
        ingress = load_yaml("openbao/ingress-openbao-ingress-letsencrypt.yaml")
        self.assertEqual(
            "0",
            certificate["metadata"]["annotations"]["argocd.argoproj.io/sync-wave"],
        )
        self.assertEqual(
            "0",
            ingress["metadata"]["annotations"]["argocd.argoproj.io/sync-wave"],
        )

    def test_server_can_reach_kubernetes_service_registration_api(self):
        policies = list(
            yaml.safe_load_all(
                (
                    ROOT / "openbao/network-policy-openbao-allow-egress-kube-api-cilium.yaml"
                ).read_text(encoding="utf-8")
            )
        )
        self.assertEqual(2, len(policies))
        for policy in policies:
            self.assertEqual("CiliumNetworkPolicy", policy["kind"])
            self.assertEqual(["kube-apiserver"], policy["spec"]["egress"][0]["toEntities"])
            service = policy["spec"]["egress"][1]["toServices"][0]["k8sService"]
            self.assertEqual({"namespace": "default", "serviceName": "kubernetes"}, service)

    def test_traefik_can_reach_acme_solver_and_openbao(self):
        solver_policy = load_yaml("openbao/network-policy-allow-cert-manager-http01-solver.yaml")
        self.assertEqual(
            {"acme.cert-manager.io/http01-solver": "true"},
            solver_policy["spec"]["podSelector"]["matchLabels"],
        )
        self.assertEqual(8089, solver_policy["spec"]["ingress"][0]["ports"][0]["port"])

        traefik_policy = load_yaml(
            "traefik/network-policy-traefik-allow-egress-ingress-namespaces.yaml"
        )
        namespaces = {
            selector["namespaceSelector"]["matchLabels"]["kubernetes.io/metadata.name"]
            for selector in traefik_policy["spec"]["egress"][0]["to"]
        }
        self.assertIn("openbao", namespaces)

    def test_openbao_can_reach_external_keycloak_discovery(self):
        policies = list(
            yaml.safe_load_all(
                (ROOT / "openbao/network-policy-openbao.yaml").read_text(encoding="utf-8")
            )
        )
        egress = next(
            policy for policy in policies if policy["metadata"]["name"] == "openbao-allow-egress"
        )
        cidrs = {
            target["ipBlock"]["cidr"]
            for rule in egress["spec"]["egress"]
            for target in rule.get("to", [])
            if "ipBlock" in target
        }
        self.assertIn("81.19.4.105/32", cidrs)

    def test_production_consumers_use_openbao_after_cutover(self):
        secret_stores = [
            path
            for path in ROOT.rglob("*secret-store*.yaml")
            if "DEPRECATED" not in path.parts and "openbao" not in path.parts
        ]
        self.assertTrue(secret_stores)
        for path in secret_stores:
            source = path.read_text(encoding="utf-8")
            if "provider:" in source and "vault:" in source:
                with self.subTest(path=path.relative_to(ROOT)):
                    self.assertIn("https://openbao-api.int.andreybondarenko.com:8200", source)
                    self.assertNotIn("caBundle:", source)
                    self.assertNotIn("caProvider:", source)
                    self.assertNotIn("https://vault.vault.svc:8200", source)


if __name__ == "__main__":
    unittest.main()
