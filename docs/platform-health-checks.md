# Longhorn report checks

Backup coverage is evaluated for every Longhorn Volume selected by a backup or
backup-force RecurringJob, directly or through a recurring-job group. Named
`backup-*` selectors also remain expected if their job definition disappears.
Volumes with only trim/snapshot policies are intentionally outside backup coverage.
The report requires a Completed backup for the same volume and backup target
created within the last 24 hours. It uses `backupCreatedAt`, never the controller's
`lastSyncedAt`; missing backups have age -1. Historical failed backups do not mask
or invalidate a newer completed backup. No expected volumes is not a passing check.

Maintenance checks use each backup/trim RecurringJob's generated CronJob
`status.lastSuccessfulTime`, linked through its owner reference. Missing,
suspended or stale CronJobs fail individually. Successful Pod retention and Pod
garbage collection do not affect the result. Existing recent-backup/trim metrics
now count recurring job definitions with a success in the last 24 hours, rather
than surviving completed Pods. The 24-hour window assumes the current daily or
more frequent schedules; revisit it if weekly policies are added.

The platform-health ClusterRole includes read-only access to Longhorn Volumes.
Argo's existing platform-health source includes both the script ConfigMap and
role, so they reconcile together. An existing running Job still uses its mounted
configuration/process state; verify a new scheduled run after sync. Newly visible
stale coverage needs investigation, rather than suppressing the check.
