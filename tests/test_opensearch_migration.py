from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]


def documents(path: Path):
    return [document for document in yaml.safe_load_all(path.read_text()) if document]


class OpenSearchMigrationTest(unittest.TestCase):
    def test_opensearch_application_is_present_for_staged_cutover(self):
        application = yaml.safe_load(
            (ROOT / "argocd/application-opensearch.yaml").read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual("opensearch", application["metadata"]["name"])
        self.assertEqual("opensearch", application["spec"]["source"]["path"])

    def test_mastodon_uses_internal_opensearch_without_credentials(self):
        values = yaml.safe_load(
            (ROOT / "mastodon/mastodon-values.yaml").read_text(encoding="utf-8")
        )
        search = values["elasticsearch"]

        self.assertEqual(
            search["hostname"], "opensearch.opensearch.svc.cluster.local"
        )
        self.assertTrue(search["enabled"])
        self.assertFalse(search["tls"])
        self.assertEqual("elasticsearch-password", search["existingSecret"])
        self.assertNotIn("username", search)

    def test_opensearch_is_single_node_and_network_isolated(self):
        stateful_set = yaml.safe_load(
            (ROOT / "opensearch/stateful-set-opensearch.yaml").read_text(
                encoding="utf-8"
            )
        )
        container = stateful_set["spec"]["template"]["spec"]["containers"][0]
        env = {item["name"]: item.get("value") for item in container["env"]}

        self.assertEqual(1, stateful_set["spec"]["replicas"])
        self.assertEqual("single-node", env["discovery.type"])
        self.assertEqual("true", env["DISABLE_SECURITY_PLUGIN"])
        self.assertFalse(
            stateful_set["spec"]["template"]["spec"]["automountServiceAccountToken"]
        )

        policies = documents(
            ROOT / "opensearch/network-policy-opensearch-default-deny.yaml"
        ) + documents(ROOT / "opensearch/network-policy-opensearch-allow-mastodon.yaml")
        self.assertEqual(
            {"opensearch-default-deny", "opensearch-allow-mastodon"},
            {policy["metadata"]["name"] for policy in policies},
        )


if __name__ == "__main__":
    unittest.main()
