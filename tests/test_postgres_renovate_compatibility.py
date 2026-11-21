"""Prevent image automation from crossing an unvalidated database major."""

import fnmatch
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAIN = "harbor.andreybondarenko.com/dockerhub/postgres"


def policy(path, package):
    """Find the last scoped compatibility guard, as later rules take precedence."""
    found = None
    for rule in json.loads((ROOT / "renovate.json").read_text())["packageRules"]:
        if "allowedVersions" not in rule:
            continue
        if package not in rule.get("matchDepNames", rule.get("matchPackageNames", [])):
            continue
        if not any(fnmatch.fnmatchcase(path, p) for p in rule.get("matchFileNames", [])):
            continue
        found = rule
    if found is None:
        raise AssertionError(f"Missing scoped PostgreSQL guard: {path}, {package}")
    return found


def permits(rule, tag):
    expression = rule["allowedVersions"]
    if not (expression.startswith("/") and expression.endswith("/")):
        raise AssertionError("Expected an explicit compatibility regex")
    return re.search(expression[1:-1], tag) is not None


class PostgreSQLCompatibilityTests(unittest.TestCase):
    def test_aliased_images_match_dependency_names(self):
        """Registry aliases change packageName; Harbor selectors must use depName."""
        config = json.loads((ROOT / "renovate.json").read_text())
        for rule in config["packageRules"]:
            for package in rule.get("matchPackageNames", []):
                for alias in config["registryAliases"]:
                    self.assertFalse(package.startswith(alias + "/"),
                                     f"Aliased image must use matchDepNames: {package}")

    def test_keycloak_keeps_supported_major_and_security_patch_updates(self):
        """A generic PostgreSQL19 proposal must not roll SSO forward again."""
        rule = policy("keycloak/stateful-set-keycloak-postgres.yaml", PLAIN)
        self.assertTrue(permits(rule, "18.7"))
        self.assertFalse(permits(rule, "19.0"))
        self.assertFalse(permits(rule, "19rc2"))
        self.assertTrue(rule["ignoreUnstable"])

    def test_ordinary_database_guard_tracks_the_reviewed_manifest_major(self):
        """A higher major needs both migration manifests and a deliberate guard change."""
        for namespace in ("bitwarden", "mastodon"):
            path = f"{namespace}/stateful-set-{namespace}-postgres.yaml"
            major = int(re.search(r"dockerhub/postgres:(\d+)", (ROOT / path).read_text())[1])
            rule = policy(path, PLAIN)
            self.assertTrue(permits(rule, f"{major}.7"))
            self.assertFalse(permits(rule, f"{major + 1}.0"))
            self.assertTrue(rule["ignoreUnstable"])

    def test_postgis_disallows_pg19_for_both_image_families(self):
        source = (ROOT / "dawarich/stateful-set-dawarich-postgres.yaml").read_text()
        major = int(re.search(r"/(?:postgis|postgis/postgis):(\d+)", source)[1])
        for package in (
            "harbor.andreybondarenko.com/github/cloudnative-pg/postgis",
            "harbor.andreybondarenko.com/dockerhub/postgis/postgis",
        ):
            rule = policy("dawarich/stateful-set-dawarich-postgres.yaml", package)
            self.assertTrue(permits(rule, f"{major}-3.7"))
            self.assertTrue(permits(rule, f"{major}.7-3.7.0-standard-trixie"))
            self.assertFalse(permits(rule, f"{major + 1}-3.7"))
            self.assertFalse(permits(rule, "19-3.7"))
            self.assertFalse(permits(rule, "19rc2-3.7"))

    def test_immich_requires_a_supported_vector_image(self):
        package = "harbor.andreybondarenko.com/github/immich-app/postgres"
        rule = policy("immich/stateful-set-immich-postgres.yaml", package)
        source = (ROOT / "immich/stateful-set-immich-postgres.yaml").read_text()
        major = int(re.search(r"immich-app/postgres:(\d+)", source)[1])
        self.assertTrue(permits(rule, f"{major}-vectorchord1.1.1-pgvector0.8.7"))
        self.assertFalse(permits(rule, f"{major + 1}-vectorchord1.1.1-pgvector0.8.7"))
        self.assertFalse(permits(rule, "19-vectorchord1.1.1-pgvector0.8.7"))
        self.assertFalse(permits(rule, "19rc2-vectorchord1.1.1"))

    def test_documentdb_major_is_capped_and_pair_requires_review(self):
        package = "harbor.andreybondarenko.com/github/ferretdb/postgres-documentdb"
        rule = policy("your-spotify/stateful-set-ferretdb-postgres.yaml", package)
        self.assertTrue(permits(rule, "17-0.107.0-ferretdb-2.7.0"))
        self.assertFalse(permits(rule, "18-0.107.0-ferretdb-2.7.0"))
        self.assertFalse(rule["automerge"])
        rules = json.loads((ROOT / "renovate.json").read_text())["packageRules"]
        paired = [r for r in rules if r.get("groupName") == "FerretDB and DocumentDB compatibility"]
        self.assertEqual(len(paired), 1)
        self.assertIn(package, paired[0]["matchDepNames"])
        self.assertIn("harbor.andreybondarenko.com/github/ferretdb/ferretdb", paired[0]["matchDepNames"])
        self.assertFalse(paired[0]["automerge"])

    def test_harbor_bundled_database_stays_on_the_reviewed_chart_series(self):
        """The vendor DB must not be upgraded as an independent postgres image."""
        rule = policy("argocd/application-harbor.yaml", "harbor")
        self.assertEqual(rule["matchManagers"], ["argocd"])
        self.assertEqual(rule["matchDatasources"], ["helm"])
        self.assertTrue(permits(rule, "1.19.5"))
        self.assertFalse(permits(rule, "1.20.0"))
        self.assertFalse(permits(rule, "2.0.0"))


if __name__ == "__main__":
    unittest.main()
