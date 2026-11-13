# Per-Job dependency gate

Preparation only. No live CronJob, schedule, active Job or alert is changed.

The first candidate is `monitoring/logs-check`, an expensive daily report. It
checks Loki's labels API through the same gateway/network-policy path used by the
report, and Ollama's tags API. These are read-only API availability checks, not
proof that the selected model can finish inference or that log history is intact.
They do not call model generation, load models, send mail or execute the report.

The wrapper waits at most300 seconds per invocation, with individual HTTP/DNS
probe subprocesses killed after at most5 seconds. All checks must pass in one
iteration. A missing provider emits one fixed JSON `cron_dependencies/skipped`
event and exits0 without executing the original report. Configuration errors
exit2; `mode: fail` exits75 on dependency timeout. When ready, `exec` preserves
the original argv, signals and eventual exit status. No shell concatenation,
credentials, exception bodies, response bodies or endpoint URLs are logged.
Redirects and environment proxies are disabled; HTTPS keeps normal verification.

This is deliberately a **main-container wrapper**, not an init container that
exits0: a successful init would otherwise release the work despite the skip.
No additional image, RBAC or API access is needed. Existing labels, image,
service account, environment, mounts and `concurrencyPolicy: Forbid` remain.
The candidate adds a four-hour Job deadline covering waiting and work; review
that ceiling against observed report duration before rollout. The next scheduled
Job runs the checks afresh, so recovery needs no resume controller or Argo override.
An old already-running Job does not adopt a changed CronJob template.

Generate the complete candidate ConfigMap and CronJob outside active sources:

```sh
python3 tools/bootstrap/prepare_cron_gate.py > /tmp/logs-check-gated-candidate.yaml
```

The generator never writes the active `metrics/` tree or calls Kubernetes. Its
ConfigMap contains only source code and credential-free internal probe URLs.
The active report retains its own preflight checks; this wrapper is not an
ongoing dependency watchdog and cannot prevent an outage after the checks pass.

## Acceptance and rollback before rollout

1. Render/review and test locally with unavailable, recovering and healthy fake
   providers. Confirm the report command is never launched on skip. Confirm
   nonzero work exits still fail the Job and no output reveals credentials.
2. After explicit live authorization, publish only the approved source change,
   observe one new Job and verify actual provider paths and report completion.
   Do not cancel an existing Job or stop a provider to test this.
3. A skipped report must leave the previous report timestamp intact. Job success
   alone must never be described as report completion. Before production rollout,
   ensure a report-freshness signal/alert distinguishes a skipped/stale report
   from a newly generated one; the structured log alone is not a durable metric.
4. Rollback through Git by restoring the original command and removing only the
   new mount/volume/deadline. Retain the ConfigMap until no Job references it.
   No suspend/resume reconciliation or data restore is involved.

## Extending to other jobs

Do not wrap all31 CronJobs indiscriminately. Catalogue each mandatory dependency
and use its real readiness contract: authenticated SQL/Valkey for Nextcloud,
Mastodon API and Immich readiness for bookmarked media, and task-specific SMTP,
S3 or database checks for the remaining jobs. Preserve existing authentication
without printing it. This initial wrapper supports only credential-free HTTP
checks; SQL, Valkey, authenticated endpoints and multi-container early init work
need their own reviewed native adapters. Never use an unauthenticated health page
as proof that protected data access works.

**Backup/restore and safety tasks must fail on missing dependencies**, retaining
backup-freshness alerts. Do not report a skipped backup as a successful Job.
Health-report/monitoring jobs should continue reporting missing dependencies,
rather than being globally blocked by the systems they observe. Do not patch
Longhorn-generated CronJobs with this wrapper: their controller owns the template.
The selected report-only skip policy must be explicit for each future adoption.
