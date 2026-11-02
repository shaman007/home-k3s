# Explicit application seccomp profiles

Prepared 2026-11-02. Set `seccompProfile.type: RuntimeDefault` on 22 application
workload templates across 15 Argo Applications. This makes the existing node
default explicit in Git. No capability, UID, privilege-escalation, image,
volume, admission-policy or namespace-security settings are changed.

## Compatibility evidence

The live kubelet configuration on all three nodes (`w386`, `talos-d4h-k5m`,
`talos-qlw-pbh`) has `seccompDefault: true`. The affected templates had no
explicit seccomp override. Read-only `/proc/1/status` checks confirmed filter
mode (`Seccomp: 2`, one filter) on 25 running application/sidecar processes.
This combination supports retaining their effective runtime default. Process
status alone does not identify a filter's exact rules. Collabora lacks `cat`,
so its evidence is the node default and absence of a template override, rather
than a process-status inspection. Completed init containers and scheduled Jobs
were not rerun merely to test this metadata change.

Profiles are set at pod level to cover regular and init containers together.
Collabora uses the pinned chart's container securityContext setting; CrowdSec
uses its agent/LAPI podSecurityContext settings. Existing container overrides
are preserved. Render checks confirmed that every container in the 22 changed
templates inherits or explicitly has RuntimeDefault, with none privileged.

## Changed workloads

- Bitwarden, Dawarich, Immich, Keycloak and Mastodon PostgreSQL StatefulSets.
- Keycloak application StatefulSet; Hister StatefulSet.
- Mail Dovecot, Postfix and Unbound Deployments.
- CrowdSec agent and LAPI Deployments.
- Minecraft, Plex, Year and WordPress PHP/nginx Deployments.
- Nextcloud web StatefulSet and Collabora Deployment.
- Your Spotify FerretDB PostgreSQL StatefulSet.
- Mastodon bookmarked-media-sync, Nextcloud cron and WordPress daily-report
  CronJobs.

Necessary root startup and permission-fixing init containers remain root;
seccomp filtering is independent of their UID requirements. See the
[non-root audit](non-root-audit.md) for those boundaries. Privileged builders,
GPU/storage/network infrastructure, Talos-managed kube-system and owner-managed
Lenka workloads remain outside this application change. Existing RuntimeDefault
settings elsewhere are unchanged. No Unconfined/Localhost override is replaced.

## Validation and rollout

All 15 Applications rendered; resource checks passed for their 79 containers
using namespace defaults. All 22 strategic-patch server dry runs were accepted.
Other Restricted-policy warnings remain (capability drops, non-root and/or
escalation settings); this change does not establish full Restricted compliance.
The repository suite passed: 247 tests run, 16 skipped. Diff whitespace checks
passed. No production controller was patched or restarted during validation.

Publication and Argo reconciliation are still required. Deployment/StatefulSet
pod templates will change and can restart single-replica applications, including
databases and mail. Monitor rollout and readiness before treating this as
complete. CronJob changes affect future Jobs; verify their next normal execution
without manually duplicating maintenance, mail or media-import side effects.
After rollout, check process filter mode where diagnostic tools exist, service
functions, Argo health/revision and new pod events. Kyverno currently audits
other security controls; this is not a claim that all of its findings clear.
