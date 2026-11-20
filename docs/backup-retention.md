# Backup retention

The policy is **20 newest completed copies per source**, including manual and
monthly copies. A Longhorn source is the `(backup target, volume name)` pair;
each retained old PostgreSQL PVC remains its own source. Talos is the encrypted
`talos-etcd/home-k8s/` object prefix. Sources with fewer copies keep all of them.

Longhorn's eight native backup RecurringJobs retain 20 each. Historical names
such as `backup-daily-retain31-a` remain assignment identifiers, not the policy.
Schedules and PVC assignments remain unchanged. A separate 15-minute retention
CronJob combines all job labels and on-demand backups before retaining the newest
20 per source. This is necessary because native recurring-job cleanup filters
by its own job label. Local snapshots and filesystem trim are separate tasks;
their retention and schedules are unchanged.

`longhorn/backup-retention.yaml` grants its consumer only get/list/delete on
Longhorn Backup objects in `longhorn-system`. It validates every completed
backup's identity, timestamp and deletion preconditions before issuing any
delete; incomplete copies never displace completed copies. Kubernetes UID and
resource-version preconditions reject concurrent changes. Existing pending
deletions block new requests. Each run deletes at most 25 copies sequentially,
waiting up to 60 seconds for each remote deletion; a stall fails the Job instead
of queuing more work. Deleting a Backup CR
asks Longhorn to remove the remote backup; it does not delete a PVC or live data.

`talos-backup/backup-retention.yaml` uses the existing OpenBao-sourced
`talos-backup-config` credentials only inside the consumer. AWS CLI lists all
pages before sorting globally, accepts only nonempty encrypted snapshot objects
in the exact cluster prefix, and uses ETag-conditional deletion. Listing errors,
future timestamps, an empty prefix or no successful upload within two hours
stop cleanup. The existing 30-day bucket lifecycle must be removed once using
the existing S3 administrator; the recurring task does not receive administrator
credentials. Otherwise an age rule could eventually remove the last 20 copies.
With hourly Talos backups, 20 copies usually cover about 20 hours, not 20 days.

The limit is reconciled every 15 minutes: a new upload can temporarily increase
the count. Previously stored copies beyond the newest 20 are intentionally
deleted. Cleanup errors fail the Job for existing Kubernetes job-failure alerts.

Sources and generated consumers:

```sh
python3 tools/generate_backup_retention.py
python3 -m unittest tests.test_backup_retention
```

For a read-only execution, create a one-off Job from the consumer template with
`RETENTION_APPLY=false`; do not run its production `true` default as a diagnostic.
Verify exact GitOps revision, terminal Job success and the remote inventory after
the first real cleanup. A configuration check alone does not prove deletion or
backup recoverability.
