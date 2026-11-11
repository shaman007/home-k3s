"""Verify Codacy SARIF batch merging, reference integrity, and safe upload preparation."""

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("sarif", ROOT / "tools/ci/prepare_codacy_sarif.py")
sarif = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sarif)


def batch(rule, filename):
    """Build a SARIF batch with one rule, artifact, and finding."""
    return {
        "tool": {
            "driver": {
                "name": "Opengrep (reported by Codacy)",
                "version": "1",
                "rules": [{"id": rule}],
            }
        },
        "artifacts": [{"location": {"uri": filename}}],
        "invocations": [{"executionSuccessful": True}],
        "results": [
            {
                "ruleId": rule,
                "ruleIndex": 0,
                "message": {"text": filename},
                "partialFingerprints": {"hash": filename},
                "locations": [
                    {"physicalLocation": {"artifactLocation": {"index": 0, "uri": filename}}}
                ],
            }
        ],
    }


class CodacySarifTest(unittest.TestCase):
    """Verify finding preservation, index remapping, and safe SARIF upload preparation."""

    def test_codacy_hash_becomes_metadata_without_losing_colocated_findings(self):
        """Verify Codacy hash becomes metadata without losing colocated findings."""
        runs = [batch(rule, "same.py") for rule in ("first", "second")]
        for index, run in enumerate(runs):
            result = run["results"][0]
            result["partialFingerprints"]["primaryLocationLineHash"] = str(index) * 32
            result["properties"] = {"existing": "retained"}
            result["fingerprints"] = {"other": "retained"}
        report = {"runs": runs}
        original = copy.deepcopy(report)
        output = sarif.prepare(report)
        self.assertEqual(report, original)
        self.assertEqual(len(output["runs"][0]["results"]), 2)
        for index, result in enumerate(output["runs"][0]["results"]):
            expected = copy.deepcopy(original["runs"][index]["results"][0])
            expected["ruleIndex"] = index
            expected["locations"][0]["physicalLocation"]["artifactLocation"]["index"] = index
            expected["properties"]["codacy.primaryLocationLineHash"] = expected[
                "partialFingerprints"
            ].pop("primaryLocationLineHash")
            self.assertEqual(result, expected)
        self.assertEqual(sarif.prepare(output), output)

    def test_conflicting_fingerprint_provenance_fails(self):
        """Verify conflicting fingerprint provenance fails."""
        run = batch("a", "a.py")
        run["results"][0]["partialFingerprints"]["primaryLocationLineHash"] = "first"
        run["results"][0]["properties"] = {"codacy.primaryLocationLineHash": "second"}
        with self.assertRaisesRegex(ValueError, "fingerprint provenance"):
            sarif.prepare({"runs": [run]})

    def test_legacy_parser_errors_cannot_replace_historical_results(self):
        """Verify legacy parser errors cannot replace historical results."""
        for rule in ("PyLint_E0001", "PyLintPython3_E0001"):
            for indexed in (False, True):
                run = batch(rule, "a.py")
                if indexed:
                    del run["results"][0]["ruleId"]
                with self.assertRaisesRegex(ValueError, "incomplete scan"):
                    sarif.prepare({"runs": [run]}, reject_parser_errors=True)
        report = {"runs": [batch("PyLint_C0301", "a.py")]}
        self.assertEqual(sarif.prepare(report, reject_parser_errors=True), report)

    def test_cli_parser_failure_does_not_create_upload_or_echo_source(self):
        """Verify CLI parser failure does not create upload or echo source."""
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "input.sarif"
            output = Path(directory) / "prepared.sarif"
            run = batch("PyLintPython3_E0001", "a.py")
            run["results"][0]["message"]["text"] = "sensitive-source-sentinel"
            source.write_text(json.dumps({"runs": [run]}))
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools/ci/prepare_codacy_sarif.py"),
                    str(source),
                    str(output),
                    "--reject-parser-errors",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(output.exists())
            self.assertIn("incomplete scan", result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            self.assertNotIn("sensitive-source-sentinel", result.stdout + result.stderr)

    def test_five_batches_preserve_findings_and_remap_local_indices(self):
        """Verify five batches preserve findings and remap local indices."""
        report = {"version": "2.1.0", "runs": [batch(str(i % 2), f"{i}.py") for i in range(5)]}
        original = copy.deepcopy(report)
        output = sarif.prepare(report)
        self.assertEqual(report, original)
        self.assertEqual(len(output["runs"]), 1)
        run = output["runs"][0]
        self.assertEqual(len(run["results"]), 5)
        self.assertEqual(len(run["invocations"]), 5)
        for i, result in enumerate(run["results"]):
            self.assertEqual(
                run["tool"]["driver"]["rules"][result["ruleIndex"]]["id"], result["ruleId"]
            )
            index = result["locations"][0]["physicalLocation"]["artifactLocation"]["index"]
            self.assertEqual(run["artifacts"][index]["location"]["uri"], f"{i}.py")
            self.assertEqual(
                result["partialFingerprints"],
                original["runs"][i]["results"][0]["partialFingerprints"],
            )

    def test_empty_results_are_valid_but_missing_runs_fail(self):
        """Verify empty results are valid but missing runs fail."""
        run = batch("a", "a.py")
        run["results"] = []
        self.assertEqual(sarif.prepare({"runs": [run]})["runs"][0]["results"], [])
        for report in ({}, {"runs": []}, {"runs": None}):
            with self.assertRaises(ValueError):
                sarif.prepare(report)

    def test_single_run_is_preserved(self):
        """Preserve a single SARIF run without changing its contents."""
        report = {"version": "2.1.0", "runs": [batch("a", "a.py")]}
        self.assertEqual(sarif.prepare(report), report)

    def test_conflicting_rules_and_invalid_references_fail(self):
        """Verify conflicting rules and invalid references fail."""
        a, b = batch("a", "a.py"), batch("a", "b.py")
        a["tool"]["driver"]["rules"][0]["name"] = "original"
        b["tool"]["driver"]["rules"][0]["name"] = "conflict"
        with self.assertRaises(ValueError):
            sarif.prepare({"runs": [a, b]})
        a["results"][0]["locations"][0]["physicalLocation"]["artifactLocation"]["index"] = 5
        with self.assertRaises(ValueError):
            sarif.prepare({"runs": [a]})

    def test_negative_index_and_missing_descriptor_preserve_finding(self):
        """Verify negative index and missing descriptor preserve finding."""
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
        """Verify rule ID overrides incorrect nonnegative index."""
        run = batch("nonsecurity", "a.py")
        run["tool"]["driver"]["rules"].insert(0, {"id": "security"})
        output = sarif.prepare({"runs": [run]})["runs"][0]
        self.assertEqual(output["results"][0]["ruleIndex"], 1)

    def test_later_batch_enriches_synthesized_descriptor(self):
        """Verify later batch enriches synthesized descriptor."""
        first, second = batch("a", "a.py"), batch("a", "b.py")
        first["tool"]["driver"]["rules"] = []
        first["results"][0]["ruleIndex"] = -1
        second["tool"]["driver"]["rules"][0]["name"] = "Full description"
        output = sarif.prepare({"runs": [first, second]})["runs"][0]
        self.assertEqual(output["tool"]["driver"]["rules"], second["tool"]["driver"]["rules"])
        self.assertEqual([r["ruleIndex"] for r in output["results"]], [0, 0])

    def test_unresolvable_index_without_id_fails(self):
        """Verify unresolvable index without ID fails."""
        run = batch("a", "a.py")
        del run["results"][0]["ruleId"]
        run["results"][0]["ruleIndex"] = -1
        with self.assertRaises(ValueError):
            sarif.prepare({"runs": [run]})

    def test_cli_reads_readonly_report_and_writes_separate_output(self):
        """Verify CLI reads readonly report and writes separate output."""
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "container.sarif"
            output = Path(directory) / "prepared.sarif"
            report = {"version": "2.1.0", "runs": [batch(str(i), f"{i}.py") for i in range(5)]}
            source.write_text(json.dumps(report))
            source.chmod(0o444)
            original = source.read_bytes()
            command = [sys.executable, str(ROOT / "tools/ci/prepare_codacy_sarif.py"), str(source)]
            result = subprocess.run(
                command + [str(output)], capture_output=True, text=True, check=False
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(output.read_text()), sarif.prepare(report))
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(source.stat().st_mode & 0o777, 0o444)
            same = subprocess.run(
                command + [str(source)], capture_output=True, text=True, check=False
            )
            self.assertNotEqual(same.returncode, 0)
            self.assertEqual(source.read_bytes(), original)

    def test_new_tables_fail_instead_of_corrupting_references(self):
        """Verify new tables fail instead of corrupting references."""
        run = batch("a", "a.py")
        run["logicalLocations"] = []
        with self.assertRaises(ValueError):
            sarif.prepare({"runs": [run]})


if __name__ == "__main__":
    unittest.main()
