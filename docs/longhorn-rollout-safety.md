# Longhorn rollout safety and stable audit image scope — 2026-11-04

## Current verified state

All three Longhorn manager Pods completed the prepull rollout and are Available.
Read-only process checks in each sidecar confirmed UID/GID 65534, zero effective
and bounding capabilities, NoNewPrivs=1 and Seccomp=2. Each manager Pod reports
Skip for all five policies because the main manager retains its reviewed
privileged requirement; the sidecar independently has its guards.

Storage checks after rollout found 66 healthy attached volumes, 66 running engines
with only RW replica modes, 132 running replicas and zero failed replicas. One
OONI volume is idle/detached, with its engine and two replicas stopped. Nodes and
disks are Ready and Schedulable. No production write test or data modification
was performed. CI on the pushed commit was still running at the latest check.

Latest current-Pod snapshot: 17 failing Pods and 42 Fail results: capability 13,
non-root 11, escalation 10, seccomp 8, privileged 0. These overlap. Remaining Pod
groups: GPU Operator 3, Longhorn 4, MetalLB/FRR 7, OpenBao 3. Controller and old
Pod reports are excluded; the 31 deliberately excluded namespace Pods remain
outside this audit's report coverage.

## Prepared rolling-update and backfill safety

Pinned chart 1.13.0 exposes longhornManager.updateStrategy. Its default permits
100% unavailability. The proposed value limits same-version guard rollouts to
one manager Pod at a time. Helm before/after comparison proved that the manager
DaemonSet changes only its updateStrategy, with no Pod-template or image change.
The component fixture is kept consistent with that strategy.

Longhorn's chart documents its 100% default as part of upgrade sequencing.
Consequently the catalog records this review for chart 1.13.0, and CI rejects a
chart-version change until that rollout contract is reviewed again. This is not
a promise that mixed-version manager upgrades are supported.

The existing backfill hook gains read-only list permission for namespace-scoped
Longhorn volumes and nodes. When its catalog includes the manager, it checks
volume/node/disk health before hook writes and before/after each component's
rollout. Attached volumes must be healthy and stable with no restore required.
An idle detached volume may report unknown health. Missing status, active
attachment transitions, restoration, degradation, failed nodes or unschedulable
disks stop further hook changes. These gates cover this hook's actions, not
unrelated Argo/Helm mutations or external administrative changes.

## CSI escalation classification

The CSI node driver and registrar already have reviewed privileged requirements.
Kubernetes necessarily permits escalation for privileged containers. Their new
escalation exception reuses those exact approved roles and images, identity and
companion guard checks; the non-privileged liveness probe must keep its no-escalation
guard. No container privilege is increased. This should classify the three
remaining CSI escalation findings as Skip after publication and scan refresh.

## Image updates in audit exceptions

At the user's explicit request, all audit exception expressions now match exact
registry/repository identity rather than exact versions. Tags, SHA-256 digests,
and tag-plus-digest forms within the same repository remain eligible. Other
registries, similar repository prefixes and child repositories are rejected.
Catalog image versions remain review snapshots. Runtime mutation-policy pins
are unchanged and still require compatibility review.

Workload names, owner UIDs, identity labels, service accounts and every required
guard remain scoped as before. An upgrade which replaces a tightly bound direct
Pod identity or version-derived controller name can still need identity review;
repository matching does not silently follow new objects. New-image compatibility
with application data or guards must still be checked during normal rollout.

## Validation

The new storage gate accepted sanitized live volume/node/disk status. Tests cover
healthy attached plus idle detached storage, degraded/faulted/restoring/transitional
volumes, missing state, unhealthy nodes/disks, and zero writes on failed preflight.
Chart render comparison, 92 native mutation/scope checks and 16 idempotence checks
passed. Eleven real CEL cases cover the new CSI escalation exception.
Forty repository-image CEL cases passed across all five audit policies, allowing version/digest
updates while rejecting registry/repository substitutions and new noncompliant
companions. The seccomp negative companion fixture was corrected to explicitly
use Unconfined; a RuntimeDefault fixture was compliant with that policy.

Repository unit tests passed: 297 run, 16 skipped. Generated-bundle consistency,
runtime-contract and whitespace checks passed. Full rendered policy CI remains a publication gate.
All changes described as prepared remain local; no live resources were patched.
