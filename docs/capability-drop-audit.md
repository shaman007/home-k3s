# Application capability-drop follow-up

Prepared 2026-11-02 after the explicit RuntimeDefault seccomp wave. Add
`capabilities.drop: [ALL]` to 19 regular containers in 15 workload templates.
All selected containers already have `allowPrivilegeEscalation: false`, an
explicit non-root identity/guard and effective RuntimeDefault seccomp.
No image, UID, volume, credential or application setting is changed.

## Scope

- ClamAV Deployment: clamd and freshclam.
- Minecraft Deployment: mnecraft (existing container spelling retained).
- WordPress Deployment: PHP and nginx.
- Year Deployment: year.
- Bitwarden, Dawarich, Immich, Keycloak and Mastodon PostgreSQL StatefulSets:
  postgres only; existing exporter controls remain unchanged.
- Your Spotify FerretDB PostgreSQL StatefulSet: postgres.
- Hister StatefulSet: hister.
- Keycloak StatefulSet: keycloak.
- Nextcloud web StatefulSet: PHP, nginx and Alloy.
- Nextcloud CronJob: previews.
- WordPress daily-report CronJob: report.

## Evidence and limits

Read-only checks on all 17 selected long-running application processes confirmed
non-root UIDs, zero permitted/effective/ambient capabilities and
`NoNewPrivs: 1`. WordPress and Dawarich were sampled after their replacement
pods became available during the preceding seccomp rollout. The capability
change removes the remaining bounding set; it does not remove a capability
currently held by these observed processes. Existing no-new-privileges settings
also prevent gaining capabilities through privileged executables.

The two CronJobs use the previously verified direct PHP and Python entrypoints
under UID 33 and UID 65534 respectively. Neither needs privileged filesystem,
network or user-management operations. They were not executed manually: doing so
would duplicate production maintenance/report side effects. A running-process
snapshot is not a complete functional or startup test of the new bounding set.

Root permission-fixing init containers and their current capabilities are
unchanged. Root-dependent mail, backup, CrowdSec, Plex and media-tooling startup,
Collabora sandboxing, RIPE Atlas raw sockets, OpenBao and privileged
infrastructure are outside this wave. Those require component-specific review;
no blanket capability removal or policy exemption is introduced.

## Verification

- All 12 affected Argo Applications rendered successfully.
- Effective non-root, no-escalation, RuntimeDefault and drop-ALL settings were
  checked on all 19 changed rendered containers.
- Resource checks passed for all 65 rendered containers with namespace defaults.
- All 15 strategic-patch API-server dry runs were accepted. Eleven still emit
  other Restricted warnings, including retained root/init-container exceptions;
  this is not full Restricted compliance.
- Repository tests passed: 247 run, 16 skipped. Diff whitespace checks passed.
- No production controller was patched or restarted by this validation.

## Publication and follow-up

Changes remain prepared in Git until published. Reconciliation changes pod
templates and can restart single-replica services and databases. Verify Argo
revision/health, replacement-pod readiness and startup events, zero effective
and bounding capabilities on changed containers, plus application functions.
Retain existing PostgreSQL volumes and permission-init behavior. Verify the next
scheduled Nextcloud cron and WordPress report rather than duplicating them.
Production startup with the new bounding sets and end-to-end service behavior
remain unverified until rollout.
