"""Combine Codacy CLI batches without losing their run-local references."""

import copy
import json
import sys
from pathlib import Path


def prepare(report):
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
                "results": [], "invocations": [], "artifacts": [],
            }
        merged = groups[key]
        target_rules = merged["tool"]["driver"]["rules"]
        rule_map = {}
        for index, rule in enumerate(rules):
            matches = [i for i, existing in enumerate(target_rules) if existing["id"] == rule["id"]]
            if matches:
                target = matches[0]
                if target_rules[target] != rule:
                    raise ValueError("Conflicting Codacy rule definitions")
            else:
                target = len(target_rules)
                target_rules.append(rule)
            rule_map[index] = target
        artifacts = run.get("artifacts", [])
        offset = len(merged["artifacts"])
        for result in run.get("results", []):
            if "ruleIndex" in result:
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
    return report


if __name__ == "__main__":
    path = Path(sys.argv[1])
    report = prepare(json.loads(path.read_text()))
    path.write_text(json.dumps(report))
    print(f"Prepared {len(report['runs'])} SARIF analysis run(s).")
