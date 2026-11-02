# Remaining application non-root audit

Audit date: 2026-11-02. Scope: harden compatible applications and retain necessary
root exceptions, as requested. Changes are prepared in Git; production rollout
and final Kyverno report clearance require publication and reconciliation.
No admission enforcement, mutation policies, blanket exemptions, namespace
security labels, credentials, or persistent-data ownership were changed.

## Prepared application changes

| Workload | Identity and change | Verification |
| --- | --- | --- |
| Connectivity exporter | UID/GID 65534; require non-root | Published image already runs as 65534; isolated probe read code and mounted configuration |
| Year | UID/GID 101, fsGroup 101; require non-root | Isolated startup with emptyDir writable paths served HTTP successfully |
| WordPress daily report | UID/GID 65534; require non-root | Probe parsed report script and checked CA trust and service-account token readability; report/email not executed |
| Nextcloud cron | UID/GID 33; require non-root; prohibit escalation; execute PHP directly instead of sudo | Probe checked PHP syntax, config readability and config/data directory write access on existing PVC; cron not executed |
| Your Spotify FerretDB PostgreSQL | UID/GID 999; require non-root; retain existing fsGroup | Production postmaster already runs as 999 and data/socket directories have matching ownership; isolated emptyDir instance started and passed SELECT 1 |
| Collabora | Require non-root through chart container securityContext | Running container identity and published image metadata confirm UID/GID 1001; chart render confirms guard reaches container |

All six Argo Applications rendered successfully. Their 24 rendered containers
passed resource-budget checks with namespace defaults. All six proposed changes
passed API-server strategic-patch dry runs. Admission still reports unrelated
Restricted warnings for missing capability drops/seccomp on several workloads,
and Collabora's escalation setting; this is a non-root wave, not full Restricted
compliance. Runtime probes were removed after verification; completed probe Jobs
use a short TTL. No production application deployment was changed directly.

## Retained root startup dependencies

These remain visible audit findings. They are documented operational boundaries,
not Kyverno PolicyExceptions or evidence that a rootless redesign is impossible.

| Workload/source | Current dependency | Review trigger |
| --- | --- | --- |
| backup-rsync | Root SSH master and multi-user privilege separation | Dedicated rootless backup transport/image |
| CrowdSec agent/LAPI and agent registration init | Current entrypoint stages system configuration and adjusts database ownership | Rootless entrypoint plus volume migration plan |
| Mail Dovecot/Postfix, Postfix queue init | Master processes manage separate users and queue ownership | Vendor-supported rootless mail architecture |
| Mail Unbound | Current image startup/config ownership and privileged DNS bind lifecycle | Verified rootless image and bind configuration |
| Mail rspamd-spam-trainer | Starts private Dovecot master/auth services before mailbox operations | Separate privilege-safe training architecture; do not test by modifying mailboxes |
| Plex | Linuxserver s6 startup fixes ownership and drops to configured application user | Supported rootless image lifecycle |
| RIPE Atlas and prepare-atlas-runtime | Root bootstrap owns runtime directories, then drops to ripe-atlas with NET_RAW | Image/bootstrap redesign preserving raw-socket operation |
| Mastodon bookmarked-media-sync, both containers | Runtime apk/global npm installation in current stock images | Prebuilt tooling image, published and verified separately |

## Retained permission init containers

Application containers retain their existing non-root guards. Root is retained
only for the existing initialization role where applicable; no recursive chown
or data migration was introduced by this change. Revisit when storage is
provisioned with the required ownership or an image supports group-writable
startup without these helpers.

- Bitwarden `prepare-permissions`; Dawarich `prepare-writable-volumes`.
- ComfyUI `prepare-runtime-directories`; ConvertX `prepare-data`.
- Immich ML `prepare-cache`, server `prepare-library`, Valkey `prepare-data`.
- Karakeep `init-writable-paths`; Meilisearch `init-meili-data`.
- Rspamd `fix-perms`; Matrix `fix-permissions`; Hister `fix-data-permissions`.
- Prometheus `fix-perms`; Thanos compactor/store-gateway `volume-mount-hack`.
- NLLB `prepare-model-cache`; both Ollama deployments `prepare-ollama-data`.
- Open WebUI `prepare-data`; SeaweedFS `prepare-data-and-tmp`.
- PostgreSQL `volume-permissions` helpers for Bitwarden, Dawarich, Immich,
  Mastodon and Keycloak.

## Infrastructure and ownership boundaries

GPU device plugins, feature discovery, DCGM, MIG, validators and associated init
containers; Longhorn manager/engines/CSI and recurring jobs; MetalLB speaker/FRR
and helper init containers; and privileged image-builder build/checkout remain
vendor or infrastructure exceptions. A guard must not disable host-device,
network, storage or build operations without a component-specific redesign.

Two vendor-managed workloads already run non-root but still lack an explicit
guard: GPU Operator controller UID/GID 1000 (chart v26.7.2), and Longhorn UI
UID 499/GID 486 (chart 1.13.0). The inspected pinned-chart defaults expose no
securityContext setting for those components. Leave these findings visible;
review upstream chart support before adding an ownership override or mutation.
They are guard gaps, not root-runtime dependencies.

Kube-system remains outside the existing audit-policy scope and under Talos/
bootstrap ownership; CoreDNS and kube-state-metrics already run non-root.
Lenka MySQL has no application manifest in this repository and remains an
owner-managed playground, explicitly outside the hardening feature in
[the specification](../specs/001-cluster-hardening-backlog/spec.md).

Reports were compared against current controller identities. Historical
ReplicaSets/Pods may retain findings after a controller is fixed; do not delete
resources merely to force aggregate counts to zero.

## Rollout follow-up

After publication, check Argo revision and health, replacement pod readiness,
actual identities and current-controller policy results for all six changes.
Year, exporter, Collabora and FerretDB templates cause replacement pods; monitor
FerretDB startup against its existing PVC without deleting or reinitializing it.
CronJob template changes affect future Jobs, so verify the next scheduled
WordPress report and Nextcloud cron separately. The safety probes deliberately
did not send report mail or execute production maintenance.

An accepted admission dry run or a successful isolated probe does not prove a
production rollout or all application functions. Check exporter metrics/checks,
Collabora document handling, Year HTTP, and Your Spotify database connectivity
following reconciliation. Remaining documented exceptions will continue to
produce non-root audit findings.
