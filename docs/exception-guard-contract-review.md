# Exception guard contract review — 2026-11-04

This batch narrows existing audit exceptions across 52 currently deployed workload
identities and 70 approved container roles. It does not grant a new role, change
application images or privileges, restart Pods, or change Audit/Ignore behavior.
The expected outcome is preserved Skip classification for unchanged reviewed
contracts and Fail when a protected guard regresses while an exception is needed.

## Review and compatibility boundary

Sanitized live Deployment, StatefulSet, DaemonSet, CronJob and Pod metadata and
security contexts were compared with the existing exception catalog. Every role
in a selected workload had to match its already approved container name and image.
Missing workloads and changed/unreviewed image roles were left unchanged; this
batch does not broaden image approvals to make exceptions match. Credentials,
environment values, volume data and Secret contents were not read or exported.

Each selected role now pins its existing declared UID/GID, non-root flag,
no-escalation, read-only root, seccomp and capability guards where present.
Non-privileged mode is protected even where its false value was previously implicit.
Existing Pod-level identity/seccomp inheritance is separately pinned. Existing
privileged roles remain privileged exceptions; no claim is made that their
capability or seccomp declarations constrain privileged runtime behavior.

Capability additions/drops are compared as sets with matching cardinality, so
ordering changes remain accepted. Removing declared guards or changing reviewed
values prevents an exception matching; even stronger configuration changes may
require review under this deliberately exact contract. A fully compliant policy
still reports Pass without requiring an exception. New noncompliant sidecars or
ephemeral containers remain unapproved. Every exception retains its existing
namespace, identity, owner, labels, service-account, image and expiry checks.
This complements prior per-policy deviation checks instead of replacing them.

Sanitized snapshots were refreshed for the matching workloads so offline tests
exercise their actual current companion containers and guard inheritance.
Raw full Pod specifications and credentials were not retained.

## Verification

The maintained policy suite includes companion guard regressions. Kyverno CLI
1.19.2 passed all 190 expectations covering the 52 current contracts and applicable
no-escalation/read-only-root regressions on 38 workloads. Repository tests passed:
291 run, 16 skipped. Runtime-contract validation, generated-bundle consistency
and whitespace checks passed. Container-level overrides of inherited identity
and seccomp settings are checked against the reviewed effective Pod defaults.
The full rendered-policy CI suite remains required after publication.

## Deployment checks from this turn

MetalLB speaker RuntimeDefault is deployed; three of three speakers are updated
and Ready. Their seccomp findings have cleared. Latest main validation was still
running and pre-commit succeeded. Argo advanced to 78be72ac with the privileged
exception bundle present, but existing CSI/privileged Pod report results remained
Fail at the latest read. Treat report convergence as unverified; do not assert
Skip from Argo sync or offline results alone. No Pod was restarted or report
removed to force rescan. Prior six application capability findings remain separate.

## Reviewed workloads

| Namespace | Kind | Workload |
| --- | --- | --- |
| `bitwarden` | Deployment | `bitwarden` |
| `comfyui` | Deployment | `comfyui` |
| `convertx` | Deployment | `convertx` |
| `dawarich` | Deployment | `dawarich` |
| `immich` | Deployment | `immich-machine-learning` |
| `immich` | Deployment | `immich-server` |
| `karakeep` | Deployment | `karakeep` |
| `mail` | Deployment | `rspamd` |
| `matrix` | Deployment | `matrix` |
| `monitoring` | Deployment | `prometheus-deployment` |
| `monitoring` | Deployment | `thanos-compactor` |
| `monitoring` | Deployment | `thanos-store-gateway` |
| `nllb` | Deployment | `nllb` |
| `ollama` | Deployment | `ollama` |
| `ollama` | Deployment | `ollama-small` |
| `open-webui` | Deployment | `open-webui` |
| `seaweedfs` | Deployment | `seaweedfs-s3` |
| `hister` | StatefulSet | `hister` |
| `immich` | StatefulSet | `immich-valkey` |
| `karakeep` | StatefulSet | `meilisearch` |
| `bitwarden` | StatefulSet | `bitwarden-postgres` |
| `dawarich` | StatefulSet | `dawarich-postgres` |
| `immich` | StatefulSet | `immich-postgres` |
| `keycloak` | StatefulSet | `keycloak-postgres` |
| `mastodon` | StatefulSet | `mastodon-postgres` |
| `backup-rsync` | Deployment | `backup-rsync` |
| `mail` | Deployment | `dovecot` |
| `mail` | Deployment | `postfix` |
| `mail` | Deployment | `unbound` |
| `mail` | CronJob | `rspamd-spam-trainer` |
| `plex` | Deployment | `plex` |
| `ripe-atlas` | Deployment | `ripe-atlas` |
| `mastodon` | CronJob | `bookmarked-media-sync` |
| `nextcloud` | Deployment | `collabora-collabora-online` |
| `gpu-operator` | DaemonSet | `gpu-feature-discovery` |
| `gpu-operator` | DaemonSet | `nvidia-dcgm-exporter` |
| `gpu-operator` | DaemonSet | `nvidia-device-plugin-daemonset` |
| `gpu-operator` | DaemonSet | `nvidia-device-plugin-mps-control-daemon` |
| `gpu-operator` | DaemonSet | `nvidia-mig-manager` |
| `gpu-operator` | DaemonSet | `nvidia-operator-validator` |
| `longhorn-system` | DaemonSet | `engine-image-ei-2f3240cb` |
| `longhorn-system` | DaemonSet | `longhorn-csi-plugin` |
| `longhorn-system` | DaemonSet | `longhorn-manager` |
| `image-builder` | CronJob | `podman-builder` |
| `longhorn-system` | Pod | `instance-manager-1b9c214d13f58139d930b8e2dd3fbd07` |
| `longhorn-system` | Pod | `instance-manager-8e7770903fa89374fe9364ff07c7111b` |
| `longhorn-system` | Pod | `instance-manager-f6f6704cc5ac55f4ab63af5be03a4196` |
| `longhorn-system` | Pod | `share-manager-pvc-ebe1aab2-d3fa-4710-9e78-5dcf04c5a1d0` |
| `longhorn-system` | Deployment | `csi-attacher` |
| `longhorn-system` | Deployment | `csi-provisioner` |
| `longhorn-system` | Deployment | `csi-resizer` |
| `longhorn-system` | Deployment | `csi-snapshotter` |
