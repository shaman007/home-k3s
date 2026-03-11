import json
import subprocess
from collections import Counter
from datetime import date
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_JOBS = REPO_ROOT / "longhorn" / "recurring-jobs-proposed.yaml"
OUTPUT_MAPPING = REPO_ROOT / "longhorn" / "recurring-job-volume-policy-proposed.yaml"
NAMESPACE = "longhorn-system"


def run_json(cmd):
    return json.loads(subprocess.check_output(cmd, text=True))


def to_yaml(obj):
    return subprocess.check_output(
        ["yq", "eval", "-P", "-"],
        input=json.dumps(obj),
        text=True,
    ).strip()


def recurring_job(name, cron, retain, task, concurrency, groups=None, labels=None, parameters=None):
    return {
        "apiVersion": "longhorn.io/v1beta2",
        "kind": "RecurringJob",
        "metadata": {
            "name": name,
            "namespace": NAMESPACE,
        },
        "spec": {
            "concurrency": concurrency,
            "cron": cron,
            "groups": groups or [name],
            "labels": labels or {},
            "name": name,
            "parameters": parameters or {},
            "retain": retain,
            "task": task,
        },
    }


jobs = run_json(["kubectl", "get", "recurringjobs.longhorn.io", "-n", NAMESPACE, "-o", "json"])["items"]
volumes = run_json(["kubectl", "get", "volumes.longhorn.io", "-n", NAMESPACE, "-o", "json"])["items"]
job_by_name = {job["metadata"]["name"]: job for job in jobs}

proposed_jobs = [
    recurring_job("trim-daily-a", "5 0 * * *", 0, "filesystem-trim", 2),
    recurring_job("trim-daily-b", "25 0 * * *", 0, "filesystem-trim", 2),
    recurring_job("trim-daily-c", "45 0 * * *", 0, "filesystem-trim", 2),
    recurring_job("trim-hourly", "17 * * * *", 0, "filesystem-trim", 1),
    recurring_job("trim-15min", "*/15 * * * *", 0, "filesystem-trim", 1),
    recurring_job("backup-daily-retain31-a", "5 1 * * *", 31, "backup", 2),
    recurring_job("backup-daily-retain31-b", "5 2 * * *", 31, "backup", 2),
    recurring_job("backup-daily-retain31-c", "5 3 * * *", 31, "backup", 2),
    recurring_job("backup-daily-retain30", "35 2 * * *", 30, "backup", 1),
    recurring_job("backup-daily-retain11", "20 1 * * *", 11, "backup", 1),
    recurring_job("backup-daily-retain1", "35 1 * * *", 1, "backup", 1),
    recurring_job("snapshot-daily-retain1", "20 4 * * *", 1, "snapshot", 1),
]

trim_daily_groups = ["trim-daily-a", "trim-daily-b", "trim-daily-c"]
backup31_groups = [
    "backup-daily-retain31-a",
    "backup-daily-retain31-b",
    "backup-daily-retain31-c",
]

trim_daily_index = 0
backup31_index = 0

volume_policies = []
policy_group_counts = Counter()

for volume in sorted(
    volumes,
    key=lambda item: (
        item.get("status", {}).get("kubernetesStatus", {}).get("namespace", ""),
        item.get("status", {}).get("kubernetesStatus", {}).get("pvcName", ""),
        item["metadata"]["name"],
    ),
):
    ks = volume.get("status", {}).get("kubernetesStatus", {})
    workloads = ks.get("workloadsStatus") or []
    labels = volume.get("metadata", {}).get("labels", {})
    current_refs = sorted(
        key.split("recurring-job.longhorn.io/", 1)[1]
        for key, value in labels.items()
        if key.startswith("recurring-job.longhorn.io/") and value == "enabled"
    )
    current_jobs = [job_by_name[name] for name in current_refs if name in job_by_name]

    trim_jobs = [job for job in current_jobs if job["spec"]["task"] == "filesystem-trim"]
    backup_jobs = [job for job in current_jobs if job["spec"]["task"] == "backup"]
    snapshot_jobs = [job for job in current_jobs if job["spec"]["task"] == "snapshot"]

    proposed_groups = []
    notes = []

    if trim_jobs:
        trim_crons = sorted({job["spec"]["cron"] for job in trim_jobs})
        if "*/15 * * * *" in trim_crons:
            proposed_groups.append("trim-15min")
            notes.append("Preserves the only 15-minute filesystem-trim schedule in the cluster.")
        elif any("* * * *" in cron and cron != "*/15 * * * *" for cron in trim_crons):
            proposed_groups.append("trim-hourly")
            notes.append("Normalizes hourly filesystem-trim volumes onto a shared off-peak hourly schedule.")
        else:
            proposed_groups.append(trim_daily_groups[trim_daily_index % len(trim_daily_groups)])
            trim_daily_index += 1

    if backup_jobs:
        retain = backup_jobs[0]["spec"]["retain"]
        if retain == 31:
            proposed_groups.append(backup31_groups[backup31_index % len(backup31_groups)])
            backup31_index += 1
        elif retain == 30:
            proposed_groups.append("backup-daily-retain30")
        elif retain == 11:
            proposed_groups.append("backup-daily-retain11")
        elif retain == 1:
            proposed_groups.append("backup-daily-retain1")
        else:
            notes.append(f"Manual review: unexpected backup retention {retain}.")

    if snapshot_jobs:
        proposed_groups.append("snapshot-daily-retain1")
        notes.append("Carries forward the current snapshot policy for this volume.")

    if not current_jobs:
        notes.append("Current behavior has no recurring jobs; proposal keeps this volume unmanaged.")

    if volume.get("spec", {}).get("fromBackup"):
        notes.append("Volume was created from backup; keep restore semantics in mind before changing labels.")

    label_map = {
        f"recurring-job-group.longhorn.io/{group}": "enabled"
        for group in proposed_groups
    }

    for group in proposed_groups:
        policy_group_counts[group] += 1

    volume_policies.append(
        {
            "namespace": ks.get("namespace", ""),
            "pvcName": ks.get("pvcName", ""),
            "longhornVolume": volume["metadata"]["name"],
            "workloadKinds": sorted(
                {
                    workload.get("workloadType", "")
                    for workload in workloads
                    if workload.get("workloadType")
                }
            ),
            "fromBackup": bool(volume.get("spec", {}).get("fromBackup")),
            "restoreVolumeRecurringJob": volume.get("spec", {}).get("restoreVolumeRecurringJob", "ignored"),
            "currentRecurringJobs": current_refs,
            "currentTasks": sorted({job["spec"]["task"] for job in current_jobs}),
            "proposedRecurringJobGroups": proposed_groups,
            "proposedLonghornVolumeLabels": label_map,
            "notes": notes,
        }
    )

jobs_header = [
    "# Proposed normalized Longhorn recurring jobs.",
    "# Generated from live cluster state on %s." % date.today().isoformat(),
    "# This file is intentionally descriptive and is not wired into Argo yet.",
]
jobs_body = "\n---\n".join(to_yaml(doc) for doc in proposed_jobs)
OUTPUT_JOBS.write_text("\n".join(jobs_header) + "\n" + jobs_body + "\n", encoding="ascii")

mapping_doc = {
    "generatedAt": date.today().isoformat(),
    "sourceNamespace": NAMESPACE,
    "implementationNotes": [
        "For existing volumes, apply recurring-job-group.longhorn.io/<group>=enabled on the Longhorn Volume resource.",
        "For workload manifests, prefer PVC or volumeClaimTemplate labels and also set recurring-job.longhorn.io/source=enabled so Longhorn syncs recurring-job labels from the PVC to the Volume.",
        "StorageClass recurringJobSelector is useful for new volumes but will not retrofit existing volumes.",
    ],
    "summary": {
        "liveRecurringJobs": len(jobs),
        "liveVolumes": len(volumes),
        "proposedRecurringJobs": len(proposed_jobs),
        "policyGroupUsage": dict(sorted(policy_group_counts.items())),
    },
    "volumePolicies": volume_policies,
}
mapping_header = [
    "# Proposed recurring-job group assignments for Longhorn-backed volumes.",
    "# Use these labels on Longhorn Volume objects or the corresponding PVC/PVC template workflow once you choose an implementation path.",
]
OUTPUT_MAPPING.write_text(
    "\n".join(mapping_header) + "\n" + to_yaml(mapping_doc) + "\n",
    encoding="ascii",
)

print(f"Wrote {OUTPUT_JOBS}")
print(f"Wrote {OUTPUT_MAPPING}")
