"""Convert Codacy issue JSON to SARIF without decoding source-file contents."""

import argparse
import json
from pathlib import Path, PurePosixPath

TOOL_NAMES = {
    "bandit": "Bandit", "opengrep": "Opengrep", "shellcheck": "Shellcheck",
    "pylintpython3": "Pylintpython3", "prospector": "Prospector", "remark-lint": "Remark-lint",
}


def scalar(value):
    """Accept Circe's scalar and wrapped value-class representations."""
    return value["value"] if isinstance(value, dict) and set(value) == {"value"} else value


def convert(records, tool):
    """Preserve every issue; reject file errors, unknown records and malformed data."""
    if not isinstance(records, list) or tool not in TOOL_NAMES:
        raise ValueError("Expected Codacy issue array and supported tool")
    rules, findings = {}, []
    for record in records:
        if not isinstance(record, dict) or set(record) != {"Issue"}:
            raise ValueError("Codacy returned a file error or unsupported result; scan is incomplete")
        issue = record["Issue"]
        rule_id = scalar(issue["patternId"])
        filename = issue["filename"]
        message = issue["message"]
        if isinstance(message, dict):
            message = message.get("text")
        location = issue["location"]
        if set(location) in ({"LineLocation"}, {"FullLocation"}):
            location = next(iter(location.values()))
        line = location["line"]
        level, category = issue["level"], issue.get("category")
        # Codacy serializes enum labels, not Scala identifiers Err/Warn.
        level = {"Error": "Err", "Warning": "Warn"}.get(level, level)
        if (not isinstance(rule_id, str) or not rule_id or not isinstance(filename, str)
                or not filename or PurePosixPath(filename).is_absolute()
                or ".." in PurePosixPath(filename).parts or not isinstance(message, str)
                or not isinstance(line, int) or isinstance(line, bool)
                or level not in {"Err", "High", "Warn", "Info"}):
            raise ValueError("Malformed Codacy issue")
        security = category == "Security"
        severity = ({"Err": "error", "High": "error", "Warn": "warning", "Info": "note"}
                    if security else {"Err": "warning", "High": "warning", "Warn": "note", "Info": "note"})
        rules.setdefault(rule_id, {"id": rule_id})
        findings.append({
            "ruleId": rule_id, "level": severity[level], "message": {"text": message},
            "locations": [{"physicalLocation": {
                "artifactLocation": {"uri": filename}, "region": {"startLine": max(1, line)},
            }}],
            # Retain all original analyzer fields, including category and columns.
            "properties": {"codacy.issue": issue},
        })
    return {"version": "2.1.0", "$schema": "https://json.schemastore.org/sarif-2.1.0.json", "runs": [{
        "tool": {"driver": {"name": TOOL_NAMES[tool] + " (reported by Codacy)", "rules": list(rules.values())}},
        "invocations": [{"executionSuccessful": True}], "results": findings,
    }]}


def main():
    """Reject partial JSON before creating a runner-owned SARIF report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("tool", choices=TOOL_NAMES)
    args = parser.parse_args()
    try:
        report = convert(json.loads(args.input.read_text(encoding="utf-8")), args.tool)
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=True)
    except (ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    print(f"Converted {len(report['runs'][0]['results'])} Codacy findings to SARIF.")


if __name__ == "__main__":
    main()
