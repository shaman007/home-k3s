import copy
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("sarif", ROOT / "tools/ci/prepare-codacy-sarif.py")
sarif = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sarif)


def batch(rule, filename):
    return {
        "tool": {"driver": {"name": "Opengrep (reported by Codacy)", "version": "1", "rules": [{"id": rule}]}},
        "artifacts": [{"location": {"uri": filename}}],
        "invocations": [{"executionSuccessful": True}],
        "results": [{"ruleId": rule, "ruleIndex": 0, "message": {"text": filename},
                     "partialFingerprints": {"hash": filename},
                     "locations": [{"physicalLocation": {"artifactLocation": {"index": 0, "uri": filename}}}]}],
    }


class CodacySarifTest(unittest.TestCase):
    def test_five_batches_preserve_findings_and_remap_local_indices(self):
        report = {"version": "2.1.0", "runs": [batch(str(i % 2), f"{i}.py") for i in range(5)]}
        original = copy.deepcopy(report)
        output = sarif.prepare(report)
        self.assertEqual(report, original)
        self.assertEqual(len(output["runs"]), 1)
        run = output["runs"][0]
        self.assertEqual(len(run["results"]), 5)
        self.assertEqual(len(run["invocations"]), 5)
        for i, result in enumerate(run["results"]):
            self.assertEqual(run["tool"]["driver"]["rules"][result["ruleIndex"]]["id"], result["ruleId"])
            index = result["locations"][0]["physicalLocation"]["artifactLocation"]["index"]
            self.assertEqual(run["artifacts"][index]["location"]["uri"], f"{i}.py")
            self.assertEqual(result["partialFingerprints"], original["runs"][i]["results"][0]["partialFingerprints"])

    def test_empty_results_are_valid_but_missing_runs_fail(self):
        run = batch("a", "a.py")
        run["results"] = []
        self.assertEqual(sarif.prepare({"runs": [run]})["runs"][0]["results"], [])
        for report in ({}, {"runs": []}, {"runs": None}):
            with self.assertRaises(ValueError):
                sarif.prepare(report)

    def test_single_run_is_preserved(self):
        report = {"version": "2.1.0", "runs": [batch("a", "a.py")]}
        self.assertEqual(sarif.prepare(report), report)

    def test_conflicting_rules_and_invalid_references_fail(self):
        a, b = batch("a", "a.py"), batch("a", "b.py")
        a["tool"]["driver"]["rules"][0]["name"] = "original"
        b["tool"]["driver"]["rules"][0]["name"] = "conflict"
        with self.assertRaises(ValueError):
            sarif.prepare({"runs": [a, b]})
        a["results"][0]["locations"][0]["physicalLocation"]["artifactLocation"]["index"] = 5
        with self.assertRaises(ValueError):
            sarif.prepare({"runs": [a]})

    def test_negative_index_and_missing_descriptor_preserve_finding(self):
        run = batch("undocumented", "a.py")
        run["tool"]["driver"]["rules"] = []
        run["results"][0]["ruleIndex"] = -1
        output = sarif.prepare({"runs": [run]})["runs"][0]
        self.assertEqual(output["tool"]["driver"]["rules"], [{"id": "undocumented"}])
        self.assertEqual(output["results"][0]["ruleIndex"], 0)
        expected = copy.deepcopy(run["results"][0])
        expected["ruleIndex"] = 0
        self.assertEqual(output["results"][0], expected)

    def test_rule_id_overrides_incorrect_nonnegative_index(self):
        run = batch("nonsecurity", "a.py")
        run["tool"]["driver"]["rules"].insert(0, {"id": "security"})
        output = sarif.prepare({"runs": [run]})["runs"][0]
        self.assertEqual(output["results"][0]["ruleIndex"], 1)

    def test_later_batch_enriches_synthesized_descriptor(self):
        first, second = batch("a", "a.py"), batch("a", "b.py")
        first["tool"]["driver"]["rules"] = []
        first["results"][0]["ruleIndex"] = -1
        second["tool"]["driver"]["rules"][0]["name"] = "Full description"
        output = sarif.prepare({"runs": [first, second]})["runs"][0]
        self.assertEqual(output["tool"]["driver"]["rules"], second["tool"]["driver"]["rules"])
        self.assertEqual([r["ruleIndex"] for r in output["results"]], [0, 0])

    def test_unresolvable_index_without_id_fails(self):
        run = batch("a", "a.py")
        del run["results"][0]["ruleId"]
        run["results"][0]["ruleIndex"] = -1
        with self.assertRaises(ValueError):
            sarif.prepare({"runs": [run]})

    def test_new_tables_fail_instead_of_corrupting_references(self):
        run = batch("a", "a.py")
        run["logicalLocations"] = []
        with self.assertRaises(ValueError):
            sarif.prepare({"runs": [run]})


if __name__ == "__main__":
    unittest.main()
