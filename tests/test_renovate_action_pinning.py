"""Keep action commit pins out of installer version inputs."""

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RenovateActionPinningTest(unittest.TestCase):
    def test_digest_pinning_is_scoped_to_action_references(self):
        """Installer inputs cannot represent the commit pins used by actions."""
        config = json.loads((ROOT / "renovate.json").read_text())
        rules = [
            rule for rule in config["packageRules"]
            if rule.get("pinDigests") is True
            and "github-actions" in rule.get("matchManagers", [])
        ]
        self.assertTrue(rules, "Keep immutable pins for GitHub action references")
        covered = set()
        for rule in rules:
            types = set(rule.get("matchDepTypes", []))
            self.assertTrue(types, "Manager-wide pins also affect uses-with tools")
            self.assertLessEqual(types, {"action", "workflow"})
            covered.update(types)
        self.assertEqual(covered, {"action", "workflow"})


if __name__ == "__main__":
    unittest.main()
