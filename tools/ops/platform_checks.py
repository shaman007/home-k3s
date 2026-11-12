"""Static daily-report assessments, guarded by source-drift and behavior tests."""

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone

SOURCE_SHA256 = "d711c3e2800af99c9ebc95f2a5946b9ca008075d26149082cae8284fff9d370e"
ASSESSMENT_NAMES = (
    "utc_now",
    "parse_time",
    "check",
    "argocd_application_check",
    "longhorn_backup_check",
    "longhorn_maintenance_check",
    "cronjob_recently_succeeded",
    "recurring_job_due_cutoff",
)
_CLOCK = ContextVar("platform_assessment_time", default=None)


@contextmanager
def at_time(instant):
    """Scope the observation clock without modifying shared function globals."""
    token = _CLOCK.set(instant)
    try:
        yield
    finally:
        _CLOCK.reset(token)


def utc_now():
    """Return the scoped observation time or the current UTC instant."""
    return _CLOCK.get() or datetime.now(timezone.utc)


def parse_time(value):
    """Parse controller UTC timestamp strings while preserving absent values."""
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def check(name, passed, summary, details=None, review_details=None):
    """Build the established daily-report result and failure-count contract."""
    details = details or []
    review_details = details if review_details is None else (review_details or [])
    return {
        "name": name,
        "passed": bool(passed),
        "summary": summary,
        "details": details,
        "review_details": review_details,
        "failures": 0 if passed else len(review_details) or 1,
    }


def application_reasons(app):
    """Explain controller health, pause, automation and condition failures."""
    metadata, status = app.get("metadata", {}), app.get("status") or {}
    reasons = []
    for field, expected in (("health", "Healthy"), ("sync", "Synced")):
        observed = (status.get(field) or {}).get("status", "Unknown")
        if observed != expected:
            reasons.append(f"{field}={observed}")
    if (
        str(
            (metadata.get("annotations") or {}).get(
                "argocd.argoproj.io/skip-reconcile", ""
            )
        ).lower()
        == "true"
    ):
        reasons.append("reconciliation paused (skip-reconcile)")
    automated = (app.get("spec", {}).get("syncPolicy") or {}).get("automated")
    if automated is None or automated.get("enabled") is False:
        reasons.append("auto-sync disabled")
    identity = metadata.get("namespace", "argocd"), metadata.get("name", "unknown")
    if identity != ("argocd", "lenka") and not (automated or {}).get("selfHeal", False):
        reasons.append("self-healing disabled")
    if metadata.get("deletionTimestamp"):
        reasons.append("application deleting")
    reasons.extend(
        f"{item.get('type', 'Unknown')}: {item.get('message', '')}"
        for item in status.get("conditions") or []
    )
    return reasons


def operation_reasons(app):
    """Retain pending, failed and stalled operation distinctions."""
    operation = (app.get("status") or {}).get("operationState") or {}
    phase = operation.get("phase")
    reasons = []
    if phase in {"Running", "Terminating", "Failed", "Error"}:
        reason = f"operation={phase}"
        if phase in {"Running", "Terminating"}:
            started = parse_time(operation.get("startedAt"))
            if started and utc_now() - started >= timedelta(minutes=30):
                reason += " (stalled for at least 30 minutes)"
        reasons.append(reason)
    if app.get("operation") and phase not in {"Running", "Terminating"}:
        reasons.append("sync operation pending")
    return reasons


def argocd_application_check(applications):
    """Apply the report's strict application policy and sole Lenka exception."""
    issues = []
    for app in applications:
        reasons = application_reasons(app) + operation_reasons(app)
        if reasons:
            metadata = app.get("metadata", {})
            issues.append(
                {
                    "namespace": metadata.get("namespace", "argocd"),
                    "item": metadata.get("name", "unknown"),
                    "value": 1,
                    "value_name": "argocd_application_issue",
                    "message": "; ".join(reasons),
                }
            )
    return check(
        "argocd_applications",
        bool(applications) and not issues,
        f"Argo CD: {len(applications) - len(issues)}/{len(applications)} application(s) "
        "healthy, synced and unpaused with expected automation. "
        "Lenka is exempt only from self-healing. Empty inventory fails.",
        issues,
    )


def latest_completed_backups(backups):
    """Index completed copies by volume and target, using creation timestamps."""
    latest = {}
    for backup in backups:
        status = backup.get("status", {})
        created = parse_time(status.get("backupCreatedAt"))
        if status.get("state") != "Completed" or not created:
            continue
        labels = backup.get("metadata", {}).get("labels", {})
        key = (
            status.get("volumeName") or labels.get("backup-volume"),
            status.get("backupTargetName") or labels.get("backup-target", "default"),
        )
        latest[key] = max(latest.get(key, created), created)
    return latest


def selected_for_backup(volume, backup_jobs):
    """Keep group policies and deleted named backup selectors in expected coverage."""
    labels = volume["metadata"].get("labels", {})
    return any(
        labels.get("recurring-job.longhorn.io/" + job["metadata"]["name"]) == "enabled"
        or any(
            labels.get("recurring-job-group.longhorn.io/" + group) == "enabled"
            for group in job.get("spec", {}).get("groups", [])
        )
        for job in backup_jobs
    ) or any(
        key.startswith("recurring-job.longhorn.io/backup-") and value == "enabled"
        for key, value in labels.items()
    )


def longhorn_backup_check(volumes, recurring, backups, cutoff):
    """Check expected coverage independently of deleted Pods or old failed copies."""
    backup_jobs = [
        job
        for job in recurring
        if job.get("spec", {}).get("task") in {"backup", "backup-force"}
    ]
    latest = latest_completed_backups(backups)
    details, issues = [], []
    for volume in volumes:
        if not selected_for_backup(volume, backup_jobs):
            continue
        metadata = volume["metadata"]
        target = volume.get("spec", {}).get("backupTargetName") or "default"
        created = latest.get((metadata["name"], target))
        detail = {
            "namespace": "longhorn-system",
            "item": metadata["name"],
            "value": int((utc_now() - created).total_seconds() / 3600)
            if created
            else -1,
            "value_name": "longhorn_backup_age_hours",
        }
        details.append(detail)
        if not created or created < cutoff:
            issues.append(detail)
    return check(
        "longhorn_backups",
        bool(details) and not issues,
        f"Backup coverage: {len(details) - len(issues)}/{len(details)} expected volume(s) "
        "have a recent completed backup; age -1 means missing.",
        details,
        issues,
    )


def cronjobs_by_recurring_owner(cronjobs):
    """Associate generated schedules with their Longhorn owner names."""
    by_owner = {}
    for cronjob in cronjobs:
        for owner in cronjob.get("metadata", {}).get("ownerReferences", []):
            api_group, _, version = owner.get("apiVersion", "").partition("/")
            if (
                owner.get("kind") == "RecurringJob"
                and api_group == "longhorn.io"
                and version
                and "/" not in version
            ):
                by_owner[owner["name"]] = cronjob
    return by_owner


def recurring_schedule_succeeded(job, cronjob, cutoff):
    """Handle monthly not-yet-due schedules without accepting suspended jobs."""
    due_cutoff = recurring_job_due_cutoff(job, cronjob, cutoff)
    if (
        cronjob
        and not cronjob.get("spec", {}).get("suspend", False)
        and due_cutoff is None
    ):
        return True
    return cronjob_recently_succeeded(cronjob, due_cutoff or cutoff)[0]


def longhorn_maintenance_check(recurring, cronjobs, cutoff):
    """Use durable schedule success rather than surviving Job/Pod history."""
    by_owner = cronjobs_by_recurring_owner(cronjobs)
    details, issues = [], []
    counts = {"backup": 0, "filesystem-trim": 0}
    expected = set()
    for job in recurring:
        task = job.get("spec", {}).get("task")
        task = "backup" if task == "backup-force" else task
        if task not in counts:
            continue
        expected.add(task)
        name = job["metadata"]["name"]
        succeeded = recurring_schedule_succeeded(job, by_owner.get(name, {}), cutoff)
        detail = {
            "namespace": "longhorn-system",
            "item": name,
            "value": int(succeeded),
            "value_name": "longhorn_recurring_job_schedule_healthy",
        }
        details.append(detail)
        if succeeded:
            counts[task] += 1
        else:
            issues.append(detail)
    details.extend(
        [
            {
                "namespace": "longhorn-system",
                "item": "recent-backups-24h",
                "value": counts["backup"],
                "value_name": "longhorn_recent_backups_24h",
            },
            {
                "namespace": "longhorn-system",
                "item": "recent-trims-24h",
                "value": counts["filesystem-trim"],
                "value_name": "longhorn_recent_trims_24h",
            },
        ]
    )
    return check(
        "longhorn_maintenance",
        len(expected) == 2 and not issues,
        f"Recurring jobs healthy for their schedules: backups={counts['backup']}, "
        f"trims={counts['filesystem-trim']}.",
        details,
        issues,
    )


def cronjob_recently_succeeded(cronjob, cutoff):
    """Require an existing unsuspended schedule with recent success."""
    if not cronjob or cronjob.get("spec", {}).get("suspend", False):
        return False, None
    last_success = parse_time(cronjob.get("status", {}).get("lastSuccessfulTime"))
    return bool(last_success and last_success >= cutoff), last_success


def monthly_occurrence(year, month, fields):
    """Return a valid UTC monthly occurrence or the report's invalid-date sentinel."""
    try:
        return datetime(
            year,
            month,
            int(fields[2]),
            int(fields[1]),
            int(fields[0]),
            tzinfo=timezone.utc,
        )
    except ValueError:
        return None


def latest_monthly_due(fields, now):
    """Check this month, then the previous month, preserving invalid-day handling."""
    due = monthly_occurrence(now.year, now.month, fields)
    if due is None or due > now:
        return monthly_occurrence(
            now.year if now.month > 1 else now.year - 1,
            now.month - 1 if now.month > 1 else 12,
            fields,
        )
    return due


def recurring_job_due_cutoff(recurring_job, cronjob, default_cutoff):
    """Skip fixed monthly schedules not yet due, with the existing 12-hour grace."""
    fields = recurring_job.get("spec", {}).get("cron", "").split()
    if len(fields) != 5 or not (
        all(value.isdigit() for value in fields[:3]) and fields[3:] == ["*", "*"]
    ):
        return default_cutoff
    now = utc_now()
    due = latest_monthly_due(fields, now)
    if due is None:
        return default_cutoff
    created = parse_time(
        cronjob.get("metadata", {}).get("creationTimestamp")
        or recurring_job.get("metadata", {}).get("creationTimestamp")
    )
    if (created and created > due) or now < due + timedelta(hours=12):
        return None
    return due
