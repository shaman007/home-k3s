"""Combine Codacy CLI batches without losing their run-local references."""

import argparse
import copy
import json
from pathlib import Path


def prepare(report, reject_parser_errors=False):
    """Merge Codacy batches while preserving findings and remapping local references."""
    report = copy.deepcopy(report)
    runs = report.get("runs")
    if not isinstance(runs, list) or not runs:
        raise ValueError("Codacy produced no SARIF analysis runs; this is not a clean scan.")
    groups = {}
    for run in runs:
        # Codacy 7.9.25 emits these fields only. Fail rather than silently lose
        # or corrupt new run-local tables if its formatter changes.
        if set(run) - {"tool", "results", "invocations", "artifacts"}:
            raise ValueError("Unsupported Codacy SARIF run fields")
        if set(run["tool"]) != {"driver"}:
            raise ValueError("Unsupported Codacy SARIF tool components")
        driver = copy.deepcopy(run["tool"]["driver"])
        rules = driver.pop("rules", [])
        key = json.dumps(driver, sort_keys=True)
        if key not in groups:
            groups[key] = {
                "tool": {"driver": {**driver, "rules": []}},
                "results": [],
                "invocations": [],
                "artifacts": [],
            }
        merged = groups[key]
        target_rules = merged["tool"]["driver"]["rules"]
        rule_map = {}
        for index, rule in enumerate(rules):
            matches = [i for i, existing in enumerate(target_rules) if existing["id"] == rule["id"]]
            if matches:
                target = matches[0]
                if target_rules[target] == {"id": rule["id"]}:
                    target_rules[target] = rule
                elif rule != {"id": rule["id"]} and target_rules[target] != rule:
                    raise ValueError("Conflicting Codacy rule definitions")
            else:
                target = len(target_rules)
                target_rules.append(rule)
            rule_map[index] = target
        artifacts = run.get("artifacts", [])
        offset = len(merged["artifacts"])
        for result in run.get("results", []):
            # Codacy puts its issue hash in GitHub's source-line hash field.
            # Let upload-sarif calculate that field from the checkout instead;
            # retain the scanner's value as provenance, not a matching key.
            partial = result.get("partialFingerprints", {})
            if "primaryLocationLineHash" in partial:
                original_hash = partial["primaryLocationLineHash"]
                properties = result.setdefault("properties", {})
                provenance_key = "codacy.primaryLocationLineHash"
                if provenance_key in properties and properties[provenance_key] != original_hash:
                    raise ValueError("Conflicting Codacy fingerprint provenance")
                properties[provenance_key] = original_hash
                del partial["primaryLocationLineHash"]
            # Codacy may emit -1 when a pattern has no description, and
            # non-security results can use indices relative to their own list.
            # The explicit ruleId is authoritative in both cases.
            if "ruleId" in result:
                rule_id = result["ruleId"]
                matches = [i for i, rule in enumerate(target_rules) if rule["id"] == rule_id]
                if not matches:
                    target_rules.append({"id": rule_id})
                    matches = [len(target_rules) - 1]
                result["ruleIndex"] = matches[0]
            elif "ruleIndex" in result:
                if result["ruleIndex"] not in rule_map:
                    raise ValueError("Invalid Codacy rule index without a ruleId")
                result["ruleIndex"] = rule_map[result["ruleIndex"]]
            for location in result.get("locations", []):
                artifact = location.get("physicalLocation", {}).get("artifactLocation", {})
                if "index" in artifact:
                    if not 0 <= artifact["index"] < len(artifacts):
                        raise ValueError("Invalid Codacy artifact index")
                    artifact["index"] += offset
            merged["results"].append(result)
        merged["artifacts"].extend(artifacts)
        merged["invocations"].extend(run.get("invocations", []))
    report["runs"] = list(groups.values())
    if reject_parser_errors:
        parser_rules = {"PyLint_E0001", "PyLintPython3_E0001"}
        for run in report["runs"]:
            rules = run["tool"]["driver"]["rules"]
            for result in run["results"]:
                rule_id = result.get("ruleId")
                if rule_id is None and "ruleIndex" in result:
                    rule_id = rules[result["ruleIndex"]]["id"]
                if rule_id in parser_rules:
                    raise ValueError(
                        "Python linter reported parser errors; "
                        "refusing to replace historical results with an incomplete scan."
                    )
    return report


def main():
    """Combine Codacy CLI batches without losing their run-local references."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--reject-parser-errors", action="store_true")
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        parser.error("Input and output must be different files")
    try:
        report = prepare(
            json.loads(args.input.read_text()), reject_parser_errors=args.reject_parser_errors
        )
    except ValueError as error:
        parser.error(str(error))
    # Codacy's container may own the input. Create runner-owned output instead
    # of reopening the scanner's report for writing.
    with args.output.open("x") as stream:
        json.dump(report, stream)
    print(f"Prepared {len(report['runs'])} SARIF analysis run(s).")


if __name__ == "__main__":
    main()
