#!/usr/bin/env python3
"""Read-only operational evidence; stdout is one versioned JSON report."""

import argparse
import ast
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys

import yaml

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "metrics/config-map-platform-health-report-scripts.yaml"
ASSESSORS = {
    "utc_now", "parse_time", "check", "argocd_application_check",
    "longhorn_backup_check", "longhorn_maintenance_check",
    "cronjob_recently_succeeded", "recurring_job_due_cutoff",
}
LIMITS = {
    "argocd": "Controller status only; no refresh or sync. Does not prove an application request works or that Git is published.",
    "backups": "Backup metadata and scheduler status only; no object download, decryption or restore. Does not prove recoverability.",
    "baseline": "Read-only baseline, not upgrade authorization or a complete recovery snapshot. No etcd quorum, disk identity, Talos API or functional recovery checks.",
}


class CollectionError(Exception):
    """An expected bounded collection failure, without raw command output."""


def load_assessors():
    """Reuse only pure assessment functions, excluding report delivery and API code."""
    source = yaml.safe_load(REPORT.read_text())["data"]["platform-health-report.py"]
    tree = ast.parse(source, filename=str(REPORT))
    functions = [node for node in tree.body
                 if isinstance(node, ast.FunctionDef) and node.name in ASSESSORS]
    if {node.name for node in functions} != ASSESSORS:
        raise ValueError("Platform assessment interface changed")
    namespace = {"datetime": datetime, "timedelta": timedelta, "timezone": timezone}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(REPORT), "exec"), namespace)
    return namespace


def collect(context, timeout):
    """Pin all GETs to the chosen context; never emit API bodies or stderr."""
    def read(resource, namespace=None):
        command = ["kubectl", "get", resource, "--context", context,
                   f"--request-timeout={timeout}s", "-o", "json"]
        command += ["--namespace", namespace] if namespace else ["--all-namespaces"]
        try:
            result = subprocess.run(command, capture_output=True, text=True,
                                    timeout=timeout + 5, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise CollectionError(f"Unable to collect {resource}: {type(exc).__name__}") from None
        if result.returncode:
            raise CollectionError(f"Unable to collect {resource}: kubectl exit {result.returncode}")
        try:
            data = json.loads(result.stdout)
            if not isinstance(data, dict) or not isinstance(data.get("items"), list):
                raise ValueError("Expected a resource list")
            if not all(isinstance(item, dict) for item in data["items"]):
                raise ValueError("Invalid list item")
            return data["items"]
        except (ValueError, TypeError):
            raise CollectionError(f"Unable to collect {resource}: invalid JSON resource list") from None
    return read


def identity(item):
    metadata = item.get("metadata", {})
    return {key: metadata.get(key) for key in ("namespace", "name", "uid")}


def assessment(name, issues, evidence):
    return {"name": name, "passed": bool(evidence) and not issues,
            "summary": f"{len(evidence)} item(s), {len(issues)} issue(s); empty inventory fails",
            "details": evidence, "review_details": issues,
            "failures": len(issues) or int(not evidence)}


def argo(read, assessors, app=None, revision=None, source_position=None):
    applications = read("applications.argoproj.io", "argocd")
    if app:
        applications = [item for item in applications if item.get("metadata", {}).get("name") == app]
    # Conditions can contain arbitrary controller error text. Retain types, not messages.
    applications = deepcopy(applications)
    for item in applications:
        for condition in (item.get("status") or {}).get("conditions") or []:
            condition.pop("message", None)
    checks = [assessors["argocd_application_check"](applications)]
    if revision:
        if len(applications) != 1:
            raise CollectionError("Revision verification requires exactly one existing application")
        item = applications[0]
        sources = item.get("spec", {}).get("sources")
        if sources:
            if source_position is None or source_position > len(sources):
                raise CollectionError("Multi-source revision verification requires a valid --source-position")
            revisions = (item.get("status", {}).get("sync") or {}).get("revisions") or []
            actual = revisions[source_position - 1] if len(revisions) >= source_position else None
        else:
            if source_position not in (None, 1):
                raise CollectionError("Single-source application only has source position 1")
            actual = (item.get("status", {}).get("sync") or {}).get("revision")
        matches = actual == revision
        checks.append({"name": "expected_revision", "passed": matches,
                       "summary": "Compared exact observed source revision to the requested revision",
                       "details": [{"application": app, "source_position": source_position or 1,
                                    "expected": revision, "observed": actual}],
                       "failures": int(not matches)})
    return checks


def backups(read, assessors, now):
    volumes = read("volumes.longhorn.io", "longhorn-system")
    recurring = read("recurringjobs.longhorn.io", "longhorn-system")
    copies = read("backups.longhorn.io", "longhorn-system")
    cronjobs = read("cronjobs.batch", "longhorn-system")
    cutoff = now - timedelta(hours=24)
    checks = [assessors["longhorn_backup_check"](volumes, recurring, copies, cutoff),
              assessors["longhorn_maintenance_check"](recurring, cronjobs, cutoff)]
    jobs = read("cronjobs.batch", "talos-backup")
    jobs = [item for item in jobs if item.get("metadata", {}).get("name") == "talos-backup"]
    future = []
    for items, field in ((copies, "backupCreatedAt"), (cronjobs + jobs, "lastSuccessfulTime")):
        for item in items:
            timestamp = assessors["parse_time"](item.get("status", {}).get(field))
            if timestamp and timestamp > now:
                future.append({**identity(item), "field": field})
    checks.append({"name": "backup_timestamps", "passed": not future,
                   "summary": "Future timestamps cannot establish backup freshness",
                   "details": future, "failures": len(future)})
    issues, evidence = [], []
    for job in jobs:
        success, last = assessors["cronjob_recently_succeeded"](job, now - timedelta(hours=2))
        # Future controller timestamps are not credible freshness evidence.
        success = success and last <= now
        detail = {**identity(job), "suspended": job.get("spec", {}).get("suspend", False),
                  "last_success": last.isoformat() if last else None}
        evidence.append(detail)
        if not success:
            issues.append(detail)
    checks.append(assessment("talos_backup_schedule", issues, evidence))
    return checks


def baseline(read):
    checks = []
    issues, evidence = [], []
    for node in read("nodes"):
        conditions = {entry.get("type"): entry.get("status")
                      for entry in node.get("status", {}).get("conditions", [])}
        detail = {**identity(node), "conditions": conditions,
                  "unschedulable": node.get("spec", {}).get("unschedulable", False),
                  "versions": {key: node.get("status", {}).get("nodeInfo", {}).get(key)
                               for key in ("osImage", "kernelVersion", "kubeletVersion",
                                           "containerRuntimeVersion", "architecture")}}
        evidence.append(detail)
        if conditions.get("Ready") != "True" or any(
                conditions.get(key) == "True" for key in ("MemoryPressure", "DiskPressure", "PIDPressure")):
            issues.append(detail)
    checks.append(assessment("nodes", issues, evidence))
    for resource in ("deployments.apps", "statefulsets.apps", "daemonsets.apps"):
        issues, evidence = [], []
        for item in read(resource):
            spec, status = item.get("spec", {}), item.get("status", {})
            daemon = resource == "daemonsets.apps"
            desired = status.get("desiredNumberScheduled", 0) if daemon else spec.get("replicas", 1)
            ready = status.get("numberReady", 0) if daemon else status.get("readyReplicas", 0)
            observed = status.get("observedGeneration", 0) >= item.get("metadata", {}).get("generation", 1)
            detail = {**identity(item), "desired": desired, "ready": ready,
                      "generation_observed": observed}
            if not daemon:
                detail["original_replicas"] = desired
            if resource == "statefulsets.apps":
                detail["pvc_retention"] = spec.get("persistentVolumeClaimRetentionPolicy", {})
            evidence.append(detail)
            if desired != ready or not observed or item.get("metadata", {}).get("deletionTimestamp"):
                issues.append(detail)
        checks.append(assessment(resource, issues, evidence))
    issues, evidence = [], []
    for volume in read("volumes.longhorn.io", "longhorn-system"):
        status = volume.get("status", {})
        state, robustness = status.get("state"), status.get("robustness")
        detail = {**identity(volume), "state": state, "robustness": robustness}
        evidence.append(detail)
        if not ((state == "attached" and robustness == "healthy")
                or (state == "detached" and robustness in {"healthy", "unknown"})):
            issues.append(detail)
    checks.append(assessment("longhorn_volumes", issues, evidence))
    return checks


def run(procedure, read, app=None, revision=None, source_position=None, now=None):
    now = now or datetime.now(timezone.utc)
    assessors = load_assessors()
    assessors["utc_now"] = lambda: now
    if procedure == "argocd":
        return argo(read, assessors, app, revision, source_position)
    if procedure == "backups":
        return backups(read, assessors, now)
    return baseline(read)


def positive_int(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("procedure", choices=tuple(LIMITS))
    parser.add_argument("--context", default="admin@home-k8s")
    parser.add_argument("--timeout", type=positive_int, default=15, help="per-request timeout in seconds")
    parser.add_argument("--app", help="select one Argo CD application")
    parser.add_argument("--revision", help="exact expected source revision (requires --app)")
    parser.add_argument("--source-position", type=positive_int, help="one-based source index for --revision")
    args = parser.parse_args(argv)
    if (args.app or args.revision or args.source_position) and args.procedure != "argocd":
        parser.error("application/revision options require argocd")
    if args.revision and not args.app:
        parser.error("--revision requires --app")
    if args.source_position and not args.revision:
        parser.error("--source-position requires --revision")
    now = datetime.now(timezone.utc)
    result = {"format_version": 1, "procedure": args.procedure,
              "checked_at": now.isoformat(), "context": args.context,
              "limitations": LIMITS[args.procedure]}
    try:
        checks = run(args.procedure, collect(args.context, args.timeout),
                     args.app, args.revision, args.source_position, now)
        passed = all(check["passed"] for check in checks)
        result.update(status="passed" if passed else "failed", checks=checks)
        code = 0 if passed else 1
    except (CollectionError, ValueError, TypeError, KeyError, AttributeError, OSError, yaml.YAMLError) as exc:
        # Unknown input errors are reported by type only, never raw resource/error text.
        message = str(exc) if isinstance(exc, CollectionError) else type(exc).__name__
        result.update(status="error", error=message, checks=[])
        code = 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    sys.exit(main())
