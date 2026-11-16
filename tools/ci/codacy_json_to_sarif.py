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


def required_text(value, field):
    """Reject missing or non-string analyzer fields without echoing source content."""
    if not isinstance(value, str) or not value:
        raise ValueError(f"Malformed Codacy {field}")
    return value


def source_location(issue):
    """Validate a checkout-relative path and normalize Codacy's line variants."""
    filename = required_text(issue["filename"], "filename")
    path = PurePosixPath(filename)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("Codacy issue is outside the checkout")
    location = issue["location"]
    if set(location) in ({"LineLocation"}, {"FullLocation"}):
        location = next(iter(location.values()))
    line = location["line"]
    if not isinstance(line, int) or isinstance(line, bool):
        raise ValueError("Malformed Codacy source line")
    return {"artifactLocation": {"uri": filename}, "region": {"startLine": max(1, line)}}


def issue_severity(issue):
    """Match the native formatter's security and non-security severity mapping."""
    level = issue["level"]
    level = {"Error": "Err", "Warning": "Warn"}.get(level, level)
    if level not in {"Err", "High", "Warn", "Info"}:
        raise ValueError("Unsupported Codacy severity")
    if issue.get("category") == "Security":
        return {"Err": "error", "High": "error", "Warn": "warning", "Info": "note"}[level]
    return {"Err": "warning", "High": "warning", "Warn": "note", "Info": "note"}[level]


def issue_result(issue):
    """Retain one complete analyzer issue without opening its source file."""
    rule_id = required_text(scalar(issue["patternId"]), "rule ID")
    message = issue["message"]
    if isinstance(message, dict):
        message = message.get("text")
    message = required_text(message, "message")
    return {
        "ruleId": rule_id,
        "level": issue_severity(issue),
        "message": {"text": message},
        "locations": [{"physicalLocation": source_location(issue)}],
        "properties": {"codacy.issue": issue},
    }


def convert(records, tool):
    """Preserve every issue; reject file errors, unknown records and malformed data."""
    if not isinstance(records, list) or tool not in TOOL_NAMES:
        raise ValueError("Expected Codacy issue array and supported tool")
    rules, findings = {}, []
    for record in records:
        if not isinstance(record, dict) or set(record) != {"Issue"}:
            raise ValueError(
                "Codacy returned a file error or unsupported result; scan is incomplete"
            )
        result = issue_result(record["Issue"])
        rules.setdefault(result["ruleId"], {"id": result["ruleId"]})
        findings.append(result)
    driver = {
        "name": TOOL_NAMES[tool] + " (reported by Codacy)",
        "rules": list(rules.values()),
    }
    return {
        "version": "2.1.0",
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "runs": [{
            "tool": {"driver": driver},
            "invocations": [{"executionSuccessful": True}],
            "results": findings,
        }],
    }


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
