# Rolling Talos cluster upgrade

This is the default home-k8s upgrade procedure. Keep ordinary applications running,
stop GPU consumers, Nextcloud and Photon, and upgrade one node at a time. Let
Longhorn synchronize replicas between maintenance steps. A full application
shutdown with all volumes detached is a separate procedure, used only when the
user explicitly chooses it. A Talos upgrade does not authorize a Kubernetes upgrade.

Live maintenance requires authorization for the target and scope. Follow
[AGENTS.md](../AGENTS.md), including its prohibited commands. This runbook does not
authorize deleting data, forcing storage detachment, bypassing PDBs or repairing
partition tables. Preparation, staging an image, activation, application recovery
and storage redundancy are separate outcomes.

## 1. Establish the baseline and recovery route

- Run `python3 tools/ops/verify.py argocd`, `backups` and `baseline` separately.
  Investigate failures and record existing problems. These reports establish
  neither backup restorability nor application functionality.
- Discover current node names, addresses, roles, scheduling state, running Talos
  and Kubernetes versions. Verify etcd membership, leader, applied indexes and
  health. Keep a working Kubernetes/Talos endpoint on another node during reboot.
- Plan memory headroom for restoring GPU workloads. CPU services rescheduled
  during drains can fill the only GPU node even while GPU consumers are stopped.
  Preserve their aggregate requests in the capacity plan; if necessary, move
  selected movable CPU caches/services to non-GPU nodes with graceful targeted
  eviction, respecting their data placement. Restore scheduling immediately after
  assignment; do not drain the whole GPU node again or change application limits
  merely to make Pending pods fit.
- Verify fresh completed etcd/PVC backups and access to recovery material. Confirm
  the user can unseal each restarted OpenBao pod before starting the next node;
  do not print, request in chat or persist an unseal key. Use the existing desktop
  OpenBao profiles; do not recover credentials from shell files or history.
- Use a compatible `talosctl`. A release binary in a temporary directory is enough
  for maintenance; verify its published checksum. Record permanent host tool
  changes in dotfiles.
- Inspect live per-node Image Factory schematics, NVIDIA/storage extensions,
  Secure Boot mode, install selectors, actual system-disk discovery, physical disk
  serials, EFI/META/STATE/EPHEMERAL locations and Longhorn/storage mounts. Preserve
  the per-node schematic and extensions. NVMe numbering can change after reboot;
  verify serials and mounted volumes, not `/dev/nvme0n1` by assumption. Stop on an
  ambiguous system disk or conflicting old META/STATE discovery.

Before any live change, save a non-secret restoration snapshot outside Git. Include
context, resource kind/namespace/name/UID, original replica counts, scheduling
state, StatefulSet PVC retention, changed CronJob/Job suspension, HPA/operator and
Argo controls, placement/strategy changes, and maintenance silence IDs/expiry.
Keep the original immutable; record progress separately so interruption is
recoverable. Exclude Secrets, complete machine configurations, environment dumps,
credentials and raw secret-bearing specs. Retain original zero counts.

## 2. Mute notifications, then stop selected workloads

Create a time-limited Alertmanager silence covering all alerts **before** stopping
workloads or draining the first node. This is the user's standing upgrade-specific
exception in AGENTS.md. Record its ID, reason and expiry; three hours is an initial
bound, not permission to leave notifications muted afterward. Renew only while
maintenance continues and remove it after verification or rollback. Keep
Alertmanager and alert evaluation running and inspect failures throughout.

Pause `argocd-application-controller` and `argocd-applicationset-controller`, preserving
their counts, and confirm they stopped. Identify other reconcilers/autoscalers that
could undo maintenance changes. Do not disable unrelated controls by default.

Stop these groups, preserving exact original counts:

| Group | Discovery and shutdown |
| --- | --- |
| GPU consumers | Inspect requests/limits, runtime class, placement and actual GPU use, including Jobs and other controllers. Current consumers include Immich server/ML, Ollama variants, NLLB and Plex; rediscover rather than relying only on names. |
| Nextcloud | Suspend its scheduled/active work, stop web/Collabora consumers, wait for termination, then stop its database/cache. Retain PVCs. |
| Photon | Scale `dawarich/photon` to zero and wait for its large data volume to detach, avoiding repeated relocation/rebuilds. |

Stop Photon before the first node reboot, while its redundant copies are healthy.
If it is stopped during an incomplete rebuild, Longhorn can discard the incomplete
replica and leave the detached volume with a single surviving copy. Do not assume
that stopping a large workload automatically preserves its storage redundancy.

ComfyUI configured with `--cpu` is not a GPU consumer. Do not change its execution
mode as part of an OS upgrade. Leave other applications and infrastructure running.
Suspend only relevant scheduled/active work or explicitly selected storage-heavy
jobs, with original settings recorded; do not copy the full-shutdown procedure's
blanket suspension into this rolling procedure.

Before scaling StatefulSets down, verify `whenScaled: Retain` and preserve the
original retention policy. Never remove PVCs or replica data to accelerate work.

## 3. Choose node order and prepare Harbor and Atlas

Prefer GPU node first, other ordinary nodes next, and the node currently running
RIPE Atlas last. Choose from live placement and storage dependencies. Stage images
with `talosctl upgrade --no-reboot` when useful; successful staging is not evidence
that a node is running the target version.

### Harbor must work away from the node about to reboot

Inspect Harbor core/nginx/portal, registry/registryctl, database, Redis, jobservice,
Trivy, their PVCs and ingress dependencies. Ready frontends on other nodes are not
enough if their database, registry storage or only healthy replica remains on the
target node.

Before its host is rebooted:

1. Cordon that node without disturbing Atlas if it is still there. Ensure healthy
   usable storage copies and scheduling capacity on the remaining nodes.
2. Relocate Harbor dependencies gracefully in dependency order. Temporary extra
   stateless core/nginx/portal replicas can reduce disruption; record and later
   restore their original counts. Do not scale a single-writer database or RWO
   registry to multiple independent writers. A single-instance dependency can have
   a brief migration interruption; report it honestly.
   For large PVCs, prefer a destination that already has a healthy replica and
   inspect data-locality behavior before migration. Scheduling registry on a node
   without a local copy can trigger another full rebuild and occupy its rebuild
   slot ahead of small recovery-critical volumes. Record any temporary placement
   control and restore it afterward; do not repeatedly move the volume or bypass
   replica protection to undo an in-progress copy.
3. Wait for Harbor pods, their engines/attachments and all required ingress/auth
   dependencies to work on nodes that will remain online. Confirm no required
   Harbor pod or storage engine is still on the target.
4. Check `/api/v2.0/health` and a real registry read: fetch a representative manifest
   and image content, or perform a representative image pull on a remaining node.
   Include a needed proxy-cache/private image where relevant, using the existing
   scoped consumer profile. Do not print registry credentials or bearer tokens.
   A `200` from the homepage or health endpoint alone is insufficient.

Do not reboot until these checks pass. Keep the selected registry read observable
through the node reboot and verify it again afterward.

### Preserve Atlas measurements

Keep the existing Atlas pod running while the other nodes are upgraded and
Longhorn synchronizes. Check the actual measurement/scheduler/controller processes,
connection activity and fresh working timestamps; a Running pod alone is not proof
of measurements. Record the original pod UID and the observation times.

Before its node is drained, confirm both Atlas volumes have healthy usable copies
on other nodes and the destination has the required IPv4/IPv6 connectivity. Move
Atlas once, gracefully, as late as possible, and verify it has reconnected and
resumed measurements on an upgraded node **before** rebooting the old host. Preserve
the identity/config and spool volumes. Never run two probes with the same identity
or increase replicas to simulate HA. With one probe, a short stop/reconnect during
migration is unavoidable; record the actual gap and do not promise zero downtime.
Use an initial ten-minute reconnect/recovery deadline. Require fresh measurement
results/transfer activity in addition to process/heartbeat evidence. If recovery
fails, do not reboot the old host: gracefully stop the destination instance,
confirm it terminated, return the same PVCs/identity to the still-running original
host and verify measurements before reconsidering maintenance. Never overlap the
two instances during rollback.

## 4. Drain and reboot one node

Before each drain/reboot, verify etcd/OpenBao quorum and application/storage health.
For every attached volume affected by taking the node offline, identify a healthy
running replica outside that node and confirm it is usable by the engine (RW, not
an incomplete rebuilding/WO copy). Inspect live replica placement, failed/healthy
timestamps and engine state. `robustness: degraded` alone neither proves safety nor
proves that a different node cannot be rebooted. Existing unrelated rebuilds may
continue only if the next node cannot remove the last usable copy. Prefer waiting
for full healthy redundancy; stop if any affected volume has no healthy outside copy.

Include detached volumes in this gate. Check surviving healthy replica records,
their data-owning nodes/disks and protection by another instance-manager PDB even
though engines are stopped and robustness may be unknown. With offline rebuilding
disabled, an incomplete second copy will not automatically recover while the
workload stays at zero. A sole detached copy on the target must block maintenance
by default. Do not force eviction or manually delete its PDB. Prepare a scoped
per-volume offline rebuild, preserve its
original `offlineRebuilding` setting and restore it afterward. Obtain a decision
when the extra copy materially changes time/cost or conflicts with the user's
instruction to avoid moving a large dataset; keep the workload stopped. Do not
enable rebuilding globally for all detached volumes as a workaround.

An explicit user-approved exception can accept a sole stopped copy without an
extra rebuild: verify the exact replica is both desired/stored `stopped`, has no
engine, and its data disk is preserved by the OS upgrade; verify every other volume
has a healthy outside copy. Save the original drain policy, temporarily use the
supported `allow-if-replica-is-stopped` policy, let Longhorn itself release the PDB,
and restore the original policy immediately after completed drain, before reboot.
Do not use `always-allow`, manually remove PDBs, or treat accepted workload downtime
as implicit acceptance of the single-copy risk. Record the scope and user decision.

Use normal Kubernetes eviction with PDB enforcement, for example:

```sh
kubectl drain NODE --ignore-daemonsets --delete-emptydir-data --timeout=25m
```

Review ephemeral-data consequences first. Do not use `--force` or
`--disable-eviction` to bypass an unexplained blocker. Check pinned workloads,
topology constraints, singleton dependencies and capacity before drain. Preserve
critical multi-replica services on remaining nodes. External Secrets webhook should
be spread across nodes, with no hostname pin; repair legacy live drift rather than
restoring an obsolete single-node placement.

Inventory hostPath and local-PV data before evacuation. Preserve binding to the
host that owns the data; preferred affinity alone is insufficient if another node
would expose an empty or different directory. Accept a short reboot interruption
on the correct host or use a separately verified shared-storage migration. Do not
relax data placement to imitate HA. This differs from removing the obsolete
hostname selector of a stateless webhook.

Longhorn `node-drain-policy: block-if-contains-last-replica` protects data. Wait for
graceful application termination, volume detach/relocation and instance-manager PDB
release. Check actual engine/replica processes and replicas on other nodes when a
PDB blocks drain; do not delete the PDB or data-bearing manager to proceed.

After successful drain, activate the staged image with a graceful `talosctl reboot`
through another healthy endpoint. Alternatively use a supported upgrade flow that
performs the same completed drain before reboot. Do not run concurrent reboot
clients or reboot multiple control-plane members together.

If `talosctl` stalls acquiring kubeconfig or reporting progress, distinguish client
delay, image download, installation, drain and reboot using live state. Cancel a
known local waiter before retrying; never blindly submit concurrent mutations.
Separate image staging, verified `kubectl drain` and reboot when needed.

## 5. Verify each node before advancing

- Verify actual server Talos/kernel version, Ready state, etcd quorum/applied
  indexes and intended extensions. Check physical disk serials, system volumes,
  storage paths and Longhorn disk UUID/readiness after NVMe renumbering.
- Verify Cilium, CoreDNS, CSI registration, Longhorn managers/instance managers and
  disk readiness. Restore the node's original scheduling state, allowing recovery.
  A Ready node does not prove usable CSI or volume mounts.
- Recover each OpenBao pod and verify unsealed readiness and quorum before
  disrupting another member. The user can run `kubectl exec -n openbao -it POD --
  bao operator unseal`, entering the key only at the hidden prompt.
- Wait for rescheduled applications and volume attachments. Follow logs/events
  for pull failures, mount errors and readiness failures; do not force detachment
  or discard data. Verify required image pulls through Harbor.
- Compare Cilium's realized ingress/egress enforcement against current policy
  selectors. Healthy agents alone do not establish enforcement. After a confirmed
  OOM during cold BPF compilation, verify agent recovery and endpoint policies;
  do not restart all agents or permanently change limits without diagnosis.
- Check Longhorn rebuild progress, errors and usable copies before the next node.
  Keep ordinary services available while synchronization runs. Pause advancement
  for a failed gate; do not hide unexpected failures behind the notification mute.

## 6. Restore selected workloads and finish

After all nodes run the target release and infrastructure works, restore saved
database/cache counts before consumers, then Nextcloud/Collabora, Photon and GPU
consumers. Preserve originally stopped workloads. Verify GPU access in an actual
GPU-configured workload and representative application requests; scheduling a GPU
resource alone is insufficient.

Restore temporary Harbor replica counts after relocation is verified; ensure
scaling down retains usable frontend endpoints. Restore changed Job/CronJob and
autoscaler controls when dependencies work, then restore Argo reconciliation last.
Do not undo deliberately corrected obsolete placement such as the webhook hostname
pin. Reconcile live state with the intended Git state and verify webhook replicas
are distributed across nodes.

Rerun `argocd`, `backups` and `baseline`; compare replica/control restoration against
the original snapshot. Verify representative ingress/OIDC/registry reads, application
functionality, Atlas measurements and Cilium policy enforcement. Wait for attached
volumes to regain intended healthy redundancy, or explicitly report ongoing routine
rebuilds and their usable copies separately from node/application recovery.

Remove maintenance silences after verification or rollback and confirm normal
notification processing is restored. Record running versions, actual interruptions
(especially Atlas), Harbor pull evidence, Longhorn redundancy, Argo state, snapshot
location and unresolved issues. Save a concise non-secret project checkpoint.
