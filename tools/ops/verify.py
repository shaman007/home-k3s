#!/usr/bin/env python3
"""Read-only operational evidence; stdout is one versioned JSON report."""

import argparse
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

try:
    from tools.ops import platform_checks
    from tools.security.probe_commands import (
        CommandTimeout,
        run_command,
        user_executable,
    )
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from tools.ops import platform_checks
    from tools.security.probe_commands import (
        CommandTimeout,
        run_command,
        user_executable,
    )


ROOT = Path(__file__).resolve().parents[2]
ASSESSORS = set(platform_checks.ASSESSMENT_NAMES)

LIMITS = {
    "argocd": (
        "Controller status only; no refresh or sync. Does not prove a"
        "n application request works or that Git is published."
    ),
    "backups": (
        "Backup metadata and scheduler status only; no object downloa"
        "d, decryption or restore. Does not prove recoverability."
    ),
    "baseline": (
        "Read-only baseline, not upgrade authorization or a complete "
        "recovery snapshot. No etcd quorum, disk identity, Talos API "
        "or functional recovery checks."
    ),
}


class CollectionError(Exception):
    """An expected bounded collection failure, without raw command output."""


def load_assessors():
    """Select static assessment functions, never execute YAML as Python."""
    return {name: getattr(platform_checks, name) for name in ASSESSORS}


def collect(context, timeout):
    """Pin all GETs to the chosen context; never emit API bodies or stderr."""

    def read(resource, namespace=None):
        """Fetch and validate one bounded Kubernetes resource-list response."""
        command = [
            user_executable("kubectl"),
            "get",
            resource,
            "--context",
            context,
            f"--request-timeout={timeout}s",
            "-o",
            "json",
        ]
        command += ["--namespace", namespace] if namespace else ["--all-namespaces"]
        try:
            result = run_command(
                command,
                capture_output=True,
                text=True,
                timeout=timeout + 5,
                check=False,
            )
        except (OSError, CommandTimeout) as exc:
            raise CollectionError(
                f"Unable to collect {resource}: {type(exc).__name__}"
            ) from None
        if result.returncode:
            raise CollectionError(
                f"Unable to collect {resource}: kubectl exit {result.returncode}"
            )
        try:
            data = json.loads(result.stdout)
            if not isinstance(data, dict) or not isinstance(data.get("items"), list):
                raise ValueError("Expected a resource list")
            if not all(isinstance(item, dict) for item in data["items"]):
                raise ValueError("Invalid list item")
            return data["items"]
        except (ValueError, TypeError):
            raise CollectionError(
                f"Unable to collect {resource}: invalid JSON resource list"
            ) from None

    return read


def identity(item):
    """Select non-secret Kubernetes object identity fields."""
    metadata = item.get("metadata", {})
    return {key: metadata.get(key) for key in ("namespace", "name", "uid")}


def assessment(name, issues, evidence):
    """Build a fail-closed inventory check and its selected evidence."""
    return {
        "name": name,
        "passed": bool(evidence) and not issues,
        "summary": f"{len(evidence)} item(s), {len(issues)} issue(s); empty inventory fails",
        "details": evidence,
        "review_details": issues,
        "failures": len(issues) or int(not evidence),
    }


def argo(read, assessors, app=None, revision=None, source_position=None):
    """Verify controller health and the requested source revision."""
    applications = read("applications.argoproj.io", "argocd")
    if app:
        applications = [
            item for item in applications if item.get("metadata", {}).get("name") == app
        ]
    # Conditions can contain arbitrary controller error text. Retain types, not messages.
    applications = deepcopy(applications)
    for item in applications:
        for condition in (item.get("status") or {}).get("conditions") or []:
            condition.pop("message", None)
    checks = [assessors["argocd_application_check"](applications)]
    if revision:
        if len(applications) != 1:
            raise CollectionError(
                "Revision verification requires exactly one existing application"
            )
        item = applications[0]
        sources = item.get("spec", {}).get("sources")
        if sources:
            if source_position is None or source_position > len(sources):
                raise CollectionError(
                    (
                        "Multi-source revision verification requires a valid --source"
                        "-position"
                    )
                )
            revisions = (item.get("status", {}).get("sync") or {}).get(
                "revisions"
            ) or []
            actual = (
                revisions[source_position - 1]
                if len(revisions) >= source_position
                else None
            )
        else:
            if source_position not in (None, 1):
                raise CollectionError(
                    "Single-source application only has source position 1"
                )
            actual = (item.get("status", {}).get("sync") or {}).get("revision")
        matches = actual == revision
        checks.append(
            {
                "name": "expected_revision",
                "passed": matches,
                "summary": (
                    "Compared exact observed source revision to the requested revision"
                ),
                "details": [
                    {
                        "application": app,
                        "source_position": source_position or 1,
                        "expected": revision,
                        "observed": actual,
                    }
                ],
                "failures": int(not matches),
            }
        )
    return checks


def future_backup_timestamps(groups, now, parse_time):
    "Reject future timestamps as evidence that a copy or schedule already succeeded."
    future = []
    for items, field in groups:
        for item in items:
            timestamp = parse_time(item.get("status", {}).get(field))
            if timestamp and timestamp > now:
                future.append({**identity(item), "field": field})
    return {
        "name": "backup_timestamps",
        "passed": not future,
        "summary": "Future timestamps cannot establish backup freshness",
        "details": future,
        "failures": len(future),
    }


def talos_backup_schedule(jobs, assessors, now):
    "Check the hourly Talos backup without confusing a future success with freshness."
    issues, evidence = [], []
    for job in jobs:
        success, last = assessors["cronjob_recently_succeeded"](
            job, now - timedelta(hours=2)
        )
        success = success and last <= now
        detail = {
            **identity(job),
            "suspended": job.get("spec", {}).get("suspend", False),
            "last_success": last.isoformat() if last else None,
        }
        evidence.append(detail)
        if not success:
            issues.append(detail)
    return assessment("talos_backup_schedule", issues, evidence)


def backups(read, assessors, now):
    """Collect backup objects and evaluate each independently defined freshness gate."""
    volumes = read("volumes.longhorn.io", "longhorn-system")
    recurring = read("recurringjobs.longhorn.io", "longhorn-system")
    copies = read("backups.longhorn.io", "longhorn-system")
    cronjobs = read("cronjobs.batch", "longhorn-system")
    cutoff = now - timedelta(hours=24)
    jobs = [
        item
        for item in read("cronjobs.batch", "talos-backup")
        if item.get("metadata", {}).get("name") == "talos-backup"
    ]
    return [
        assessors["longhorn_backup_check"](volumes, recurring, copies, cutoff),
        assessors["longhorn_maintenance_check"](recurring, cronjobs, cutoff),
        future_backup_timestamps(
            ((copies, "backupCreatedAt"), (cronjobs + jobs, "lastSuccessfulTime")),
            now,
            assessors["parse_time"],
        ),
        talos_backup_schedule(jobs, assessors, now),
    ]


def node_baseline(nodes):
    """Retain node versions and fail readiness or active pressure problems."""
    issues, evidence = [], []
    for node in nodes:
        conditions = {
            entry.get("type"): entry.get("status")
            for entry in node.get("status", {}).get("conditions", [])
        }
        detail = {
            **identity(node),
            "conditions": conditions,
            "unschedulable": node.get("spec", {}).get("unschedulable", False),
            "versions": {
                key: node.get("status", {}).get("nodeInfo", {}).get(key)
                for key in (
                    "osImage",
                    "kernelVersion",
                    "kubeletVersion",
                    "containerRuntimeVersion",
                    "architecture",
                )
            },
        }
        evidence.append(detail)
        if conditions.get("Ready") != "True" or any(
            conditions.get(key) == "True"
            for key in ("MemoryPressure", "DiskPressure", "PIDPressure")
        ):
            issues.append(detail)
    return assessment("nodes", issues, evidence)


def workload_baseline(resource, items):
    "Preserve desired replica and PVC-retention observations for one controller kind."
    issues, evidence = [], []
    for item in items:
        spec, status = item.get("spec", {}), item.get("status", {})
        daemon = resource == "daemonsets.apps"
        desired = (
            status.get("desiredNumberScheduled", 0)
            if daemon
            else spec.get("replicas", 1)
        )
        ready = (
            status.get("numberReady", 0) if daemon else status.get("readyReplicas", 0)
        )
        observed = status.get("observedGeneration", 0) >= item.get("metadata", {}).get(
            "generation", 1
        )
        detail = {
            **identity(item),
            "desired": desired,
            "ready": ready,
            "generation_observed": observed,
        }
        if not daemon:
            detail["original_replicas"] = desired
        if resource == "statefulsets.apps":
            detail["pvc_retention"] = spec.get(
                "persistentVolumeClaimRetentionPolicy", {}
            )
        evidence.append(detail)
        if (
            desired != ready
            or not observed
            or item.get("metadata", {}).get("deletionTimestamp")
        ):
            issues.append(detail)
    return assessment(resource, issues, evidence)


def volume_baseline(volumes):
    """Require stable attached volumes while accepting intentionally detached ones."""
    issues, evidence = [], []
    for volume in volumes:
        status = volume.get("status", {})
        state, robustness = status.get("state"), status.get("robustness")
        detail = {**identity(volume), "state": state, "robustness": robustness}
        evidence.append(detail)
        if not (
            (state == "attached" and robustness == "healthy")
            or (state == "detached" and robustness in {"healthy", "unknown"})
        ):
            issues.append(detail)
    return assessment("longhorn_volumes", issues, evidence)


def baseline(read):
    """Assemble baseline evidence without mixing resource-specific assessment state."""
    return [
        node_baseline(read("nodes")),
        *[
            workload_baseline(resource, read(resource))
            for resource in ("deployments.apps", "statefulsets.apps", "daemonsets.apps")
        ],
        volume_baseline(read("volumes.longhorn.io", "longhorn-system")),
    ]


@dataclass(frozen=True)
class ArgoSelection:
    """Group optional source-revision selection without a positional argument trap."""

    app: str | None = None
    revision: str | None = None
    source_position: int | None = None


def run(procedure, read, selection=None, now=None):
    """Evaluate one read-only procedure using a scoped, concurrency-safe clock."""
    now = now or datetime.now(timezone.utc)
    assessors = load_assessors()
    selection = selection or ArgoSelection()
    with platform_checks.at_time(now):
        if procedure == "argocd":
            return argo(
                read,
                assessors,
                selection.app,
                selection.revision,
                selection.source_position,
            )
        if procedure == "backups":
            return backups(read, assessors, now)
        return baseline(read)


def positive_int(value):
    """Parse a strictly positive integer command-line option."""
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def main(argv=None):
    """Parse command options, run the procedure and report its outcome."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("procedure", choices=tuple(LIMITS))
    parser.add_argument("--context", default="admin@home-k8s")
    parser.add_argument(
        "--timeout",
        type=positive_int,
        default=15,
        help="per-request timeout in seconds",
    )
    parser.add_argument("--app", help="select one Argo CD application")
    parser.add_argument(
        "--revision", help="exact expected source revision (requires --app)"
    )
    parser.add_argument(
        "--source-position",
        type=positive_int,
        help="one-based source index for --revision",
    )
    args = parser.parse_args(argv)
    if (
        args.app or args.revision or args.source_position
    ) and args.procedure != "argocd":
        parser.error("application/revision options require argocd")
    if args.revision and not args.app:
        parser.error("--revision requires --app")
    if args.source_position and not args.revision:
        parser.error("--source-position requires --revision")
    now = datetime.now(timezone.utc)
    result = {
        "format_version": 1,
        "procedure": args.procedure,
        "checked_at": now.isoformat(),
        "context": args.context,
        "limitations": LIMITS[args.procedure],
    }
    try:
        checks = run(
            args.procedure,
            collect(args.context, args.timeout),
            ArgoSelection(args.app, args.revision, args.source_position),
            now=now,
        )
        passed = all(check["passed"] for check in checks)
        result.update(status="passed" if passed else "failed", checks=checks)
        code = 0 if passed else 1
    except (
        CollectionError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        OSError,
    ) as exc:
        # Unknown input errors are reported by type only, never raw resource/error text.
        message = str(exc) if isinstance(exc, CollectionError) else type(exc).__name__
        result.update(status="error", error=message, checks=[])
        code = 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    sys.exit(main())
