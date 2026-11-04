# GPU config init and FRR helper review — 2026-11-04

Prepared runtime changes affect 17 additional per-node container contexts across
five currently running Pods: two GPU DaemonSets and three FRR Pods. The complete
infrastructure catalog now contains 15 selected roles across eight Pods; already
hardened controllers do not need another restart when their specs are unchanged.
No live workload or policy was patched during this review.

## GPU config-manager init

Both live `/config` and `/available-configs` directories are root-owned mode 0777.
The config file and service-account token are mode 0644. The helper can therefore
run as UID/GID 1000 without fsGroup changes, ownership init, added capabilities,
or changes to the shared config volume. Its symlink remains readable by the
privileged device plugin/discovery processes. Main GPU processes and their mounts,
resources, runtime classes, time-slicing config and privileges are unchanged.

The pinned [source](https://github.com/NVIDIA/k8s-device-plugin/blob/v0.20.1/cmd/config-manager/main.go)
constructs a Kubernetes client, watches node labels and selects a config symlink.
Production uses ONESHOT=true and SEND_SIGNAL=false; signalling is not needed by
this init role. The mutation contract pins those flags, the config paths/default,
node label, fallback strategy and NODE_NAME field reference. A flag or path change
invalidates the runtime mutation contract instead of silently applying these guards.

The real binary passed UID-1000 one-shot default/fallback probes with zero
capabilities, no-new-privileges and default seccomp on mode-0777 storage. A separate
watch-mode fixture exercised actual node list/watch and alternate config selection
against a loopback mock API, with no production credentials or GPU devices. A
mode-0755 directory correctly fails non-root and is a boundary case, not the live
layout. No root exception is granted to config-manager-init.

The existing reviewed privileged GPU actors gain root/escalation/capability/seccomp
audit classifications tied to their already approved privileged roles. Their
non-privileged init companion must independently remain non-root, zero-capability,
no-escalation and RuntimeDefault. Companion checks also bind its image repository.
`reviewedCompanions` only adds guard constraints; it never grants an exception role
or bypasses a policy's compliance checks. Version/digest updates within the same
repository remain allowed for audit matching. All policies remain Audit/Ignore.
During reconciliation, reports can temporarily fail until the new guards are live.

## FRR helpers

Live VTY sockets are owner 100, group 102, mode 0770; frr.conf is owner 100:101,
mode 0600. Metrics/status helpers become UID 100, GID 102, non-root, drop ALL,
no escalation and RuntimeDefault. No Pod supplemental group, fsGroup or volume
ownership change is introduced. Their existing service-account token is readable
at mode 0644; the mixed-identity Pod retains that projection layout.

The reloader remains UID 0, GID 102. The controller is UID 0 with only NET_RAW and
signals the reloader by PID. Changing the reloader to UID 100 would require adding
KILL to the controller, which this batch avoids. A zero-capability UID-0 sender
successfully signalled the UID-0 fixture reloader, but could not signal UID 100.
The reloader drops ALL and retains only DAC_OVERRIDE to access owner-100 mode-0600
configuration. No SETUID, SETGID, KILL, NET_ADMIN or SYS_ADMIN is retained by it.
Its writable root and /tmp behavior are unchanged.

The real frr-reload.py syntax check and configuration application passed with only
DAC_OVERRIDE. The actual reloader shell's SIGHUP, flock, status and persistence
path passed against an isolated real bgpd socket. Dropping DAC_OVERRIDE correctly
failed access to the reproduced mode-0600 file. The fixture uses no kernel routes,
Zebra connection or BGP TCP listener and never contacts a real peer.

Real metrics/status binaries passed as UID 100/GID 102 with zero effective and
bounding capabilities, NoNewPrivs=1 and seccomp mode 2. Metrics served authenticated
HTTPS 200 through mock TokenReview/SubjectAccessReview, queried real BGP VTY data,
and the status exporter fetched its mock Pod and started API caches. Full real
cluster status publication still needs rollout verification. The fixture contains
only bgpd, so its liveness endpoint cannot represent all five production daemons.
Synthetic TLS material is temporary and removed; production credentials were not
used. Probe sources are under tools/security/test-*-guards.py.

Production FRR uses a shared PID namespace: `/proc/1` is the pause process. Runtime
checks must find the actual helper PIDs, not mistake the pause process's capabilities
for the helpers'. Live helper PIDs were UID 0 with broad default capability sets
before this change. The FRR controller, parent and routing daemons already run with
seccomp mode 2; their new explicit RuntimeDefault fields preserve that existing
profile. Their routing capabilities and identities are not changed.

## Rollout and validation

The existing guarded backfill remains sequential, with full-contract admission
previews before hook writes and stable-readiness checks between controllers.
FRR keeps maxUnavailable=1. The GPU node gate requires Ready=true and capacity plus
allocatable nvidia.com/gpu=8 before writes and after each target. Its new ClusterRole
can only GET the single known node talos-d4h-k5m; it cannot list or patch nodes.
Existing namespace-scoped controller patch permissions remain limited by name.
Longhorn storage-health gates remain in place. These gates cover hook actions,
not unrelated Argo/Helm changes.

Expect five Pod replacements: FRR on three nodes, then feature discovery and device
plugin on the GPU node. GPU resource advertisement can be transient during plugin
restart. Existing GPU workloads are not directly restarted; verify their device
access after re-registration. Do not publish another batch until these rollouts,
FRR reload/metrics/status behavior, representative LoadBalancer endpoints, storage
health and GPU allocations are verified.

Offline checks: 103 real CEL mutation/scope/idempotence cases, including critical
GPU env/field-ref changes; 140 GPU exception positive/negative cases across all five
policies; real runtime probes described above. The complete rendered policy suite
remains a CI publication gate. After deployment expect the two GPU Pods to report
Skip for reviewed privileged requirements while the config init stays compliant.
FRR escalation/seccomp results should become Pass; root/capability findings for
remaining required FRR roles stay visible. No claim of deployed clearance is made.

Repository validation: 310 tests passed, 16 skipped; all 13 rendered guard resources
passed strict Kubernetes 1.37.1 schema validation. Runtime-contract, generated-bundle,
resource-budget, restricted-context and whitespace checks passed.
