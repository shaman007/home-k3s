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

# Argo CD application checks

The health email also reads all Argo CD Applications. Every application must be
Healthy and Synced, with auto-sync enabled and reconciliation unpaused. Any
application condition (including warnings), deletion, pending/running/terminating
sync, or latest Failed/Error operation requires review. Running or terminating
operations older than 30 minutes are additionally marked stalled. Progressing,
Suspended, Degraded, Missing and Unknown health states fail immediately; a daily
snapshot cannot prove that a Progressing state persisted between runs.

Self-healing is expected for all applications except `argocd/lenka`, the existing
exception documented in `argocd/README.md` for its user-managed playground.
Lenka still receives every other check. An absent automated policy or explicit
`enabled: false` disables auto-sync; an empty automated object or omitted/null
`enabled` enables it. No application policies are changed by the report.

An empty inventory or API/RBAC collection error fails the Argo check, while
allowing the rest of the email to run. The report's ClusterRole grants read-only
Application access. Issue reasons appear in text and HTML; application issue
metrics use stable application names. The text email lists the first five review
items per check; HTML includes all affected applications. Sync-window scheduling
is not evaluated. Verify a newly scheduled report after GitOps deployment.

# Retained OpenBao trim exception

The three legacy `openbao/data-openbao-{0,1,2}` PVCs retain sealed Raft data
following the 2026-11-16 recovery. The trim guard and coverage report exempt only
the original, explicitly listed Longhorn bindings while their volumes are
`detached` and the PVC has `openbao-recovery-generation: legacy-20261116`.
Backup assignments remain unchanged. The report lists these as retained recovery
exceptions, not as successfully trimmed PVCs. Attached volumes, replacement
bindings and the active `data-openbao-20261116-*` PVCs require normal trim coverage.

Publish both `longhorn/trim-coverage-guard.yaml` and
`metrics/config-map-platform-health-report-scripts.yaml` through GitOps. After
Argo sync, remove any trim labels restored by the old guard from the three legacy
PVCs, let Longhorn propagate the labels, and verify a new guard run leaves them
absent. Keep the legacy StatefulSet at zero replicas; its immutable claim template
still contains historical labels and must be reviewed before recovery/recreation.
Do not remove its PVCs or backup assignments.
