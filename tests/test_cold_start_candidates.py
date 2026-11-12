"""Cold-start candidate safety and separation of public/internal dependencies."""

import importlib.util
import fnmatch
from collections import defaultdict
from pathlib import Path
import subprocess  # nosec B404: fixed OpenSSL fixture command, no shell.
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
MODULE_SPEC = importlib.util.spec_from_file_location(
    "cold_start", ROOT / "tools/bootstrap/prepare_cold_start.py"
)
module = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(module)


class ColdStartCandidates(unittest.TestCase):
    """Verify trust boundaries and inactive source generation."""

    @classmethod
    def setUpClass(cls):
        """Create an isolated disposable CA and independent candidate tree."""
        # unittest owns this context and closes it even if class setup fails.
        cls.base = Path(
            cls.enterClassContext(tempfile.TemporaryDirectory())  # pylint: disable=consider-using-with
        )
        subprocess.run(  # nosec B603: fixed absolute OpenSSL and isolated temporary paths.
            [
                "/usr/bin/openssl",
                "req",
                "-x509",
                "-newkey",
                "ec",
                "-pkeyopt",
                "ec_paramgen_curve:prime256v1",
                "-nodes",
                "-days",
                "2",
                "-subj",
                "/CN=TEST ONLY bootstrap root",
                "-addext",
                "basicConstraints=critical,CA:TRUE",
                "-keyout",
                str(cls.base / "key.pem"),
                "-out",
                str(cls.base / "ca.pem"),
            ],
            check=True,
            capture_output=True,
        )
        cls.pem = (cls.base / "ca.pem").read_text()
        cls.out = cls.base / "candidate"
        cls.summary = module.prepare(ROOT, cls.out, cls.pem, "192.168.30.250")

    def test_both_backends_and_raft_use_internal_trust(self):
        """Retain mounted paths while verifying both listeners and Raft trust."""
        app = yaml.safe_load((self.out / "argocd/application-openbao.yaml").read_text())
        values = yaml.safe_load(app["spec"]["source"]["helm"]["values"])
        config = values["server"]["ha"]["raft"]["config"]
        internal, public = config.split('listener "tcp" {')[1:]
        self.assertIn(module.CERT_DIR + "/tls.crt", internal)
        self.assertIn(module.CERT_DIR + "/tls.crt", public)
        self.assertIn(
            {"type": "secret", "name": "openbao-server-letsencrypt-tls"},
            values["server"]["extraVolumes"],
        )
        self.assertIn("leader_ca_cert_file", config)
        self.assertNotIn(module.OLD, config)
        self.assertEqual(module.OLD, values["server"]["ha"]["apiAddr"])

    def test_ingress_and_metrics_verify_internal_ca(self):
        """Require explicit CA verification for ingress and metrics clients."""
        transport = yaml.safe_load(
            (self.out / "openbao/servers-transport-openbao-server.yaml").read_text()
        )
        self.assertEqual(["openbao-backend-trust"], transport["spec"]["rootCAsSecrets"])
        self.assertNotIn("insecureSkipVerify", transport["spec"])
        cm = yaml.safe_load(
            (
                self.out
                / "metrics/kubernetes-prometheus/config-map-prometheus-server-conf.yaml"
            ).read_text()
        )
        config = yaml.safe_load(
            next(v for v in cm["data"].values() if "job_name: openbao" in v)
        )
        job = next(
            j for j in config["scrape_configs"] if j.get("job_name") == "openbao"
        )
        self.assertEqual("/etc/openbao-ca/ca.crt", job["tls_config"]["ca_file"])
        deployment = yaml.safe_load(
            (
                self.out
                / "metrics/kubernetes-prometheus/deployment-prometheus-deployment.yaml"
            ).read_text()
        )
        self.assertTrue(
            any(
                m["mountPath"] == "/etc/openbao-ca"
                for c in deployment["spec"]["template"]["spec"]["containers"]
                for m in c.get("volumeMounts", [])
            )
        )

    def test_all_inventory_stores_use_pinned_internal_ca(self):
        """Cover all source stores and the DNS webhook override."""
        self.assertGreater(self.summary["secret_stores"], 30)
        self.assertIn("cert-manager", self.summary["trust_namespaces"])
        store = yaml.safe_load_all(
            (self.out / "firefox-sync/secret-store-vault-secret-store.yaml").read_text()
        )
        vault = next(store)["spec"]["provider"]["vault"]
        self.assertEqual(module.NEW, vault["server"])
        self.assertTrue(vault["caBundle"])
        app = yaml.safe_load(
            (self.out / "argocd/application-godaddy-webhook.yaml").read_text()
        )
        values = yaml.safe_load(app["spec"]["source"]["helm"]["values"])
        self.assertFalse(values["openbao"]["useSystemTrust"])
        self.assertEqual(module.NEW, values["openbao"]["server"])

    def test_harbor_controller_has_no_optional_bootstrap_dependencies(self):
        """Keep internal image pulls independent of optional public middleware."""
        app = yaml.safe_load(
            (self.out / "argocd/application-traefik-registry.yaml").read_text()
        )
        values = yaml.safe_load(app["spec"]["source"]["helm"]["values"])
        for key in ("experimental", "volumes"):
            self.assertNotIn(key, values)
        self.assertEqual(2, len(values["additionalArguments"]))
        self.assertFalse(
            values["providers"]["kubernetesIngress"]["publishedService"]["enabled"]
        )
        policy = values["extraObjects"][0]
        self.assertEqual("NetworkPolicy", policy["kind"])
        self.assertEqual(
            {"app.kubernetes.io/instance": "traefik-registry-traefik"},
            policy["spec"]["podSelector"]["matchLabels"],
        )
        self.assertEqual(8443, policy["spec"]["ingress"][0]["ports"][0]["port"])
        self.assertFalse(values["persistence"]["enabled"])
        self.assertFalse(values["providers"]["kubernetesCRD"]["enabled"])
        self.assertEqual(
            ["harbor"], values["providers"]["kubernetesIngress"]["namespaces"]
        )
        ingress = yaml.safe_load(
            (self.out / "harbor/ingress-harbor-internal-registry.yaml").read_text()
        )
        self.assertEqual("traefik-registry", ingress["spec"]["ingressClassName"])
        self.assertEqual("harbor-tls", ingress["spec"]["tls"][0]["secretName"])
        self.assertNotIn(
            "traefik.ingress.kubernetes.io/router.middlewares",
            ingress["metadata"]["annotations"],
        )
        self.assertFalse(
            (self.out / "harbor/ingress-andreybondarenko-ingress.yaml").exists()
        )

    def test_registry_node_policy_is_narrow_and_included_in_candidates(self):
        """Retain Cilium node identities without opening other listeners or pods."""
        policy_path = (
            "traefik/cilium-network-policy-traefik-registry-allow-node-pulls.yaml"
        )
        policy = yaml.safe_load((self.out / policy_path).read_text())
        self.assertEqual(
            (ROOT / policy_path).read_text(), (self.out / policy_path).read_text()
        )
        self.assertEqual("CiliumNetworkPolicy", policy["kind"])
        self.assertEqual("traefik", policy["metadata"]["namespace"])
        self.assertEqual(
            {"matchLabels": {"app.kubernetes.io/instance": "traefik-registry-traefik"}},
            policy["spec"]["endpointSelector"],
        )
        ports = [{"ports": [{"port": "8443", "protocol": "TCP"}]}]
        self.assertEqual(
            [
                {"fromEntities": ["host", "remote-node"], "toPorts": ports},
                {
                    "fromEndpoints": [
                        {
                            "matchExpressions": [
                                {
                                    "key": "k8s:io.kubernetes.pod.namespace",
                                    "operator": "Exists",
                                }
                            ]
                        }
                    ],
                    "toPorts": ports,
                },
            ],
            policy["spec"]["ingress"],
        )
        self.assertNotIn("egress", policy["spec"])
        owner = yaml.safe_load(
            (ROOT / "argocd/application-traefik-network-policy.yaml").read_text()
        )
        patterns = (
            owner["spec"]["source"]["directory"]["include"].strip("{}").split(",")
        )
        self.assertTrue(
            any(fnmatch.fnmatch(Path(policy_path).name, p) for p in patterns)
        )

    def test_builder_egress_only_targets_the_internal_registry_backend(self):
        """Keep existing build egress while permitting only the new HTTPS backend."""
        path = "image-builder/network-policy-podman-builder-internal-registry.yaml"
        policy = yaml.safe_load((self.out / path).read_text())
        self.assertEqual((ROOT / path).read_text(), (self.out / path).read_text())
        spec = policy["spec"]
        self.assertEqual(["Egress"], spec["policyTypes"])
        self.assertEqual(
            {
                "app.kubernetes.io/name": "podman-builder",
                "app.kubernetes.io/instance": "podman-builder",
            },
            spec["podSelector"]["matchLabels"],
        )
        self.assertEqual(
            [
                {
                    "to": [
                        {
                            "namespaceSelector": {
                                "matchLabels": {
                                    "kubernetes.io/metadata.name": "traefik"
                                }
                            },
                            "podSelector": {
                                "matchLabels": {
                                    "app.kubernetes.io/instance": "traefik-registry-traefik"
                                }
                            },
                        }
                    ],
                    "ports": [{"protocol": "TCP", "port": 8443}],
                }
            ],
            spec["egress"],
        )

    def test_connectivity_probe_only_reaches_internal_registry_backend(self):
        """Keep the Harbor readiness probe working after internal DNS cutover."""
        path = (
            "connectivity-exporter/"
            "network-policy-connectivity-exporter-allow-egress-internal-registry.yaml"
        )
        policy = yaml.safe_load((self.out / path).read_text())
        self.assertEqual((ROOT / path).read_text(), (self.out / path).read_text())
        self.assertEqual("connectivity-exporter", policy["metadata"]["namespace"])
        self.assertEqual(
            {"matchLabels": {"app": "connectivity-exporter"}},
            policy["spec"]["podSelector"],
        )
        self.assertEqual(["Egress"], policy["spec"]["policyTypes"])
        self.assertEqual(
            [
                {
                    "to": [
                        {
                            "namespaceSelector": {
                                "matchLabels": {
                                    "kubernetes.io/metadata.name": "traefik"
                                }
                            },
                            "podSelector": {
                                "matchLabels": {
                                    "app.kubernetes.io/instance": "traefik-registry-traefik"
                                }
                            },
                        }
                    ],
                    "ports": [{"protocol": "TCP", "port": 8443}],
                }
            ],
            policy["spec"]["egress"],
        )
        owner = yaml.safe_load(
            (
                ROOT / "argocd/application-connectivity-exporter-network-policy.yaml"
            ).read_text()
        )
        patterns = (
            owner["spec"]["source"]["directory"]["include"].strip("{}").split(",")
        )
        self.assertTrue(any(fnmatch.fnmatch(Path(path).name, p) for p in patterns))

    def test_http01_selfchecks_use_public_dns_for_split_registry_hostname(self):
        """Keep public HTTP-01 validation independent of the internal HTTPS-only VIP."""
        app = yaml.safe_load(
            (ROOT / "argocd/application-cert-manager.yaml").read_text()
        )
        source = next(
            s for s in app["spec"]["sources"] if s.get("chart") == "cert-manager"
        )
        values = yaml.safe_load(source["helm"]["values"])
        self.assertIn(
            "--acme-http01-solver-nameservers=1.1.1.1:53,8.8.8.8:53",
            values["extraArgs"],
        )
        issuer = yaml.safe_load(
            (ROOT / "cert-manager/cluster-issuer-letsencrypt-prod.yaml").read_text()
        )
        self.assertEqual(
            "traefik",
            issuer["spec"]["acme"]["solvers"][0]["http01"]["ingress"][
                "ingressClassName"
            ],
        )

    def test_new_files_match_existing_argocd_source_filters(self):
        """Ensure generated manifests are visible to their owning applications."""
        files = defaultdict(list)
        for path in self.summary["files"]:
            files[Path(path).parent.as_posix()].append(Path(path).name)
        for appname, directory in [
            ("metallb-config", "metallb"),
            ("openbao-custom", "openbao"),
            ("harbor-custom", "harbor"),
        ]:
            app = yaml.safe_load(
                (ROOT / f"argocd/application-{appname}.yaml").read_text()
            )
            pattern = app["spec"]["source"]["directory"]["include"]
            patterns = pattern.strip("{}").split(",")
            for name in files[directory]:
                self.assertTrue(any(fnmatch.fnmatch(name, p) for p in patterns), name)

    def test_private_key_input_and_invalid_vip_are_rejected(self):
        """Reject private input and VIPs outside the infrastructure subnet."""
        with self.assertRaises(ValueError):
            module.prepare(
                ROOT,
                self.base / "bad-key",
                "-----BEGIN " + "PRIVATE KEY-----",
                "192.168.30.250",
            )
        with self.assertRaises(ValueError):
            module.prepare(ROOT, self.base / "bad-vip", self.pem, "8.8.8.8")

    def test_no_generated_private_key_or_plaintext_credential(self):
        """Never emit private key material in the candidate tree."""
        for path in self.out.rglob("*.yaml"):
            self.assertNotIn("PRIVATE KEY", path.read_text())
        self.assertFalse(self.summary["active"])


if __name__ == "__main__":
    unittest.main()
