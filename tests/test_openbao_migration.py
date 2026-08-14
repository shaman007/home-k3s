from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]


def load_yaml(path: str):
    return yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))


class OpenBaoMigrationTest(unittest.TestCase):
    def test_parallel_openbao_release_is_pinned_and_isolated(self):
        application = load_yaml("argocd/application-openbao.yaml")
        source = application["spec"]["source"]
        values = yaml.safe_load(source["helm"]["values"])

        self.assertEqual("ghcr.io/openbao/charts", source["repoURL"])
        self.assertEqual("openbao", source["chart"])
        self.assertEqual("0.28.6", source["targetRevision"])
        self.assertEqual("openbao", application["spec"]["destination"]["namespace"])
        self.assertEqual(2, values["server"]["ha"]["replicas"])
        self.assertTrue(values["server"]["ha"]["raft"]["enabled"])
        self.assertTrue(values["server"]["ha"]["raft"]["setNodeId"])
        self.assertEqual(
            "https://openbao-active.openbao.svc:8200",
            values["server"]["ha"]["apiAddr"],
        )
        # OpenBao 2.6.1 blocks its initialization API while retry_join has no
        # leader. The rehearsal initializes and restores node 0 first; the
        # active-Service retry_join block is added back before node 1 joins.
        self.assertNotIn(
            "retry_join", values["server"]["ha"]["raft"]["config"]
        )
        self.assertEqual(
            {"whenDeleted": "Retain", "whenScaled": "Retain"},
            values["server"]["persistentVolumeClaimRetentionPolicy"],
        )
        self.assertFalse(values["snapshotAgent"]["enabled"])

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

    def test_source_vault_can_issue_only_openbao_server_names(self):
        script = (ROOT / "vault/configure-pki-acme.sh").read_text(encoding="utf-8")
        policy = (ROOT / "vault/policy-vault-pki-renewer.hcl").read_text(
            encoding="utf-8"
        )
        renewer = (ROOT / "vault/cron-job-vault-pki-renewer.yaml").read_text(
            encoding="utf-8"
        )

        self.assertIn("pki-root/roles/openbao-server", script)
        self.assertIn('path "pki-root/issue/openbao-server"', policy)
        self.assertIn('"openbao" "openbao-server-tls"', renewer)
        self.assertNotIn("openbao.w386.k8s.my.lan", script)

    def test_tls_bootstrap_rbac_precedes_certificate_wait(self):
        for path in (
            "openbao/role-vault-pki-renewer.yaml",
            "openbao/role-binding-vault-pki-renewer.yaml",
        ):
            with self.subTest(path=path):
                resource = load_yaml(path)
                self.assertEqual(
                    "-2",
                    resource["metadata"]["annotations"][
                        "argocd.argoproj.io/sync-wave"
                    ],
                )

    def test_production_consumers_remain_on_vault_during_rehearsal(self):
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
                    self.assertIn("https://vault.vault.svc:8200", source)


if __name__ == "__main__":
    unittest.main()
