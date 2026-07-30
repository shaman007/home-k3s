from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]


def documents(path: Path):
    return list(yaml.safe_load_all(path.read_text(encoding="utf-8")))


class HeadlampOidcSecurityTest(unittest.TestCase):
    def test_headlamp_uses_oidc_secret(self):
        deployment = documents(ROOT / "headlamp" / "deployment-headlamp.yaml")[0]
        container = deployment["spec"]["template"]["spec"]["containers"][0]
        env = {item["name"]: item for item in container["env"]}

        self.assertEqual("headlamp", env["HEADLAMP_CONFIG_OIDC_CLIENT_ID"]["value"])
        self.assertEqual(
            "https://sso.andreybondarenko.com/realms/master",
            env["HEADLAMP_CONFIG_OIDC_IDP_ISSUER_URL"]["value"],
        )
        self.assertEqual(
            "headlamp-oidc-secret",
            env["HEADLAMP_CONFIG_OIDC_CLIENT_SECRET"]["valueFrom"]["secretKeyRef"]["name"],
        )

    def test_headlamp_container_uses_restricted_security_context(self):
        deployment = documents(ROOT / "headlamp" / "deployment-headlamp.yaml")[0]
        pod_spec = deployment["spec"]["template"]["spec"]
        container_security = pod_spec["containers"][0]["securityContext"]

        self.assertEqual("RuntimeDefault", pod_spec["securityContext"]["seccompProfile"]["type"])
        self.assertTrue(container_security["runAsNonRoot"])
        self.assertEqual(100, container_security["runAsUser"])
        self.assertEqual(101, container_security["runAsGroup"])
        self.assertFalse(container_security["allowPrivilegeEscalation"])
        self.assertEqual(["ALL"], container_security["capabilities"]["drop"])

    def test_no_long_lived_headlamp_tokens_or_service_account_admin(self):
        active = [
            path
            for path in ROOT.rglob("*.yaml")
            if "DEPRECATED" not in path.parts
        ]
        for path in active:
            for document in documents(path):
                if not isinstance(document, dict):
                    continue
                self.assertFalse(
                    document.get("kind") == "Secret"
                    and document.get("type") == "kubernetes.io/service-account-token",
                    path,
                )
                if document.get("kind") != "ClusterRoleBinding":
                    continue
                if document.get("roleRef", {}).get("name") != "cluster-admin":
                    continue
                for subject in document.get("subjects", []):
                    self.assertNotEqual("ServiceAccount", subject.get("kind"), path)

    def test_oidc_users_have_expected_rbac(self):
        admin = documents(ROOT / "lenka" / "rbac-shaman007-cluster-admin.yaml")[0]
        readonly = documents(ROOT / "lenka" / "readonly-infra-rbac.yaml")[0]
        namespace_admin = documents(ROOT / "lenka" / "rbac-lenka-admin.yaml")[1]

        self.assertEqual("cluster-admin", admin["roleRef"]["name"])
        self.assertEqual("shaman007", admin["subjects"][0]["name"])
        self.assertEqual("view", readonly["roleRef"]["name"])
        self.assertEqual("lenka", readonly["subjects"][0]["name"])
        self.assertEqual("lenka", namespace_admin["metadata"]["namespace"])
        self.assertEqual("admin", namespace_admin["roleRef"]["name"])

    def test_api_server_maps_preferred_username_without_prefix(self):
        patch = documents(ROOT / "talos" / "api-server-oidc.yaml")[0]
        args = patch["cluster"]["apiServer"]["extraArgs"]

        self.assertEqual("headlamp", args["oidc-client-id"])
        self.assertEqual("preferred_username", args["oidc-username-claim"])
        self.assertEqual("-", args["oidc-username-prefix"])


if __name__ == "__main__":
    unittest.main()
