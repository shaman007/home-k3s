"""Verify Renovate handling of the private Traefik image and its source version."""

import json
from pathlib import Path
import re
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
APP = "argocd/application-traefik-private.yaml"
VALUES = "traefik-private/values.yaml"


class PrivateTraefikRenovateTest(unittest.TestCase):
    """Keep private Traefik image updates synchronized across both value sources."""

    def traefik_manager(self):
        """Select and verify the unique Docker manager covering the private application."""
        config = json.loads((ROOT / "renovate.json").read_text())
        managers = [
            manager
            for manager in config["customManagers"]
            if manager.get("depNameTemplate") == "docker.io/traefik"
        ]
        self.assertEqual(len(managers), 1)
        manager = managers[0]
        self.assertEqual(manager["datasourceTemplate"], "docker")
        self.assertTrue(
            any(re.search(pattern[1:-1], APP) for pattern in manager["managerFilePatterns"])
        )
        return manager

    def test_future_image_updates_cover_both_equal_value_sources(self):
        """Verify future image updates cover both equal value sources."""
        manager = self.traefik_manager()
        # This expression uses only syntax shared by Python and Renovate's RE2,
        # apart from the named capture spelling.
        pattern = re.compile(
            manager["matchStrings"][0].replace("(?<currentValue>", "(?P<currentValue>")
        )
        original_app = (ROOT / APP).read_text()
        original_values = (ROOT / VALUES).read_text()
        matches = list(pattern.finditer(original_app))
        self.assertEqual(len(matches), 1)
        match = matches[0]
        values = yaml.safe_load(original_values)
        image = values["image"]
        self.assertEqual(
            manager["depNameTemplate"],
            f"{image['registry']}/{image['repository']}",
        )
        self.assertEqual(match["currentValue"], image["tag"])

        for next_version in ["v3.7.99", "v3.8.0", "v4.0.0"]:
            with self.subTest(version=next_version):
                start, end = match.span("currentValue")
                updated_app = original_app[:start] + next_version + original_app[end:]
                updated_values = yaml.safe_load(original_values)
                updated_values["image"]["tag"] = next_version
                embedded = yaml.safe_load(updated_app)["spec"]["source"]["helm"]["values"]
                self.assertEqual(yaml.safe_load(embedded), updated_values)
                self.assertEqual(pattern.search(updated_app)["currentValue"], next_version)

    def test_both_managers_share_a_group_for_all_update_types(self):
        """Verify both managers share a group for all update types."""
        config = json.loads((ROOT / "renovate.json").read_text())
        rules = [
            rule
            for rule in config["packageRules"]
            if rule.get("groupSlug") == "private-traefik-image"
        ]
        self.assertEqual(len(rules), 1)
        rule = rules[0]
        self.assertEqual(set(rule["matchFileNames"]), {APP, VALUES})
        self.assertEqual(rule["matchPackageNames"], ["docker.io/traefik"])
        self.assertEqual(rule["matchDatasources"], ["docker"])
        self.assertTrue(rule["groupName"])
        self.assertNotIn("matchUpdateTypes", rule)
        self.assertNotIn("matchManagers", rule)
