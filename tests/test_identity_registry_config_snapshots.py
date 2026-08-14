import json
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


class IdentityRegistryConfigSnapshotsTest(unittest.TestCase):
    def test_harbor_snapshot_covers_every_proxy_cache(self):
        snapshot = yaml.safe_load(
            (ROOT / "harbor/config/harbor.snapshot.yaml").read_text(encoding="utf-8")
        )
        registries = {item["name"] for item in snapshot["registries"]}
        proxies = {
            item["proxyRegistry"]
            for item in snapshot["projects"]
            if "proxyRegistry" in item
        }

        self.assertEqual(
            {
                "dockerhub",
                "ecr-public",
                "elastic",
                "github",
                "google",
                "kubernetes",
                "nvidia",
                "quay",
            },
            registries,
        )
        self.assertEqual(registries, proxies)
        self.assertEqual("<restore-from-vault>", snapshot["systemSettings"]["oidc"]["clientSecret"])

    def test_keycloak_snapshot_has_expected_custom_clients_and_no_secrets(self):
        snapshot = json.loads(
            (ROOT / "keycloak/config/master-realm.snapshot.json").read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(
            {
                "argocd",
                "dawarich",
                "grafana",
                "graphana",
                "harbor",
                "headlamp",
                "karakeep",
                "mastodon",
                "nextcloud",
                "openbao",
                "vault",
                "wordpress",
            },
            {client["clientId"] for client in snapshot["clients"]},
        )
        for client in snapshot["clients"]:
            self.assertNotIn("secret", client)
            self.assertNotIn("registrationAccessToken", client)
        openbao = next(
            client for client in snapshot["clients"] if client["clientId"] == "openbao"
        )
        self.assertIn(
            "https://openbao.w386.k8s.my.lan/ui/vault/auth/oidc/oidc/callback",
            openbao["redirectUris"],
        )
        self.assertNotIn("password", snapshot["realm"].get("smtpServer", {}))


if __name__ == "__main__":
    unittest.main()
