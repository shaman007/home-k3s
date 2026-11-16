"""Keep all findings while avoiding Codacy's broken source-reading formatter."""

import copy
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CONVERTER = load("codacy_json", "tools/ci/codacy_json_to_sarif.py")
PREPARE = load("codacy_prepare", "tools/ci/prepare_codacy_sarif.py")


class CodacyJsonTests(unittest.TestCase):
    def issue(self, rule="Bandit_B101"):
        return {"Issue": {"patternId": rule, "filename": "aiy-voice/server.py",
                          "message": {"text": "Unicode message: česky, русский"},
                          "level": "High", "category": "Security",
                          "location": {"LineLocation": {"line": 12}}}}

    def test_keeps_all_issues_without_reading_sources(self):
        records = [self.issue(), self.issue(), self.issue("Bandit_B102")]
        report = PREPARE.prepare(CONVERTER.convert(records, "bandit"), False)
        run = report["runs"][0]
        self.assertEqual(len(run["results"]), 3)
        self.assertEqual(len(run["tool"]["driver"]["rules"]), 2)
        self.assertEqual(run["results"][0]["properties"]["codacy.issue"], records[0]["Issue"])
        self.assertEqual(run["results"][0]["level"], "error")

    def test_file_errors_unknown_records_and_bad_locations_fail(self):
        for records in ([{"FileError": {"filename": "broken.py", "message": "decode"}}],
                        [{"FileMetrics": {}}], [{}], None):
            with self.subTest(records=records), self.assertRaises(ValueError):
                CONVERTER.convert(records, "bandit")
        record = self.issue()
        record["Issue"]["filename"] = "../outside.py"
        with self.assertRaises(ValueError):
            CONVERTER.convert([record], "bandit")

    def test_parser_errors_remain_fatal_after_conversion(self):
        report = CONVERTER.convert([self.issue("PyLintPython3_E0001")], "pylintpython3")
        with self.assertRaisesRegex(ValueError, "parser errors"):
            PREPARE.prepare(report, True)

    def test_empty_success_and_wrapped_fields(self):
        self.assertEqual(CONVERTER.convert([], "bandit")["runs"][0]["results"], [])
        record = copy.deepcopy(self.issue())
        record["Issue"]["patternId"] = {"value": "Bandit_B101"}
        record["Issue"]["location"] = {"FullLocation": {"line": 0, "column": 4}}
        result = CONVERTER.convert([record], "bandit")["runs"][0]["results"][0]
        self.assertEqual(result["ruleId"], "Bandit_B101")
        self.assertEqual(result["locations"][0]["physicalLocation"]["region"]["startLine"], 1)
