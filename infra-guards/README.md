# Reviewed infrastructure guards

The original catalog selected five roles across four controller identities: GPU Operator, Longhorn
CSI driver deployer and its wait init, and the GPU feature-discovery/device-plugin
config-manager init containers. The latter complete as UID/GID 1000 with drop ALL,
no escalation and RuntimeDefault. Their privileged companion processes retain
separately reviewed audit exceptions.

The active BGP FRR DaemonSet and statuscleaner are restored as reviewed targets
in the local [warning follow-up](../docs/kyverno-warning-review.md). Their ten
selected roles bring the catalog to fifteen roles across six controller identities.
Current FRR images are pinned separately from the earlier L2-only retirement.
Publication replaces routing Pods and requires the maintenance verification in
that review; no deployed clearance is claimed here.

## Requirements and compatibility

GPU Operator's main process already runs UID/GID 1000 with zero capabilities.
The Longhorn driver deployer configures CSI resources through the API; host
inspection happens in separate helpers. Its controller CLI and curl wait init
passed isolated non-root checks. Its projected token is readable by UID/GID 1000,
and fsGroup is limited to the reviewed zero-volume/zero-mount workload contract.
No PVC ownership change is introduced.

GPU config init compatibility was verified with actual directory modes, real
one-shot and watch-mode config selection, and zero-capability/NNP/seccomp probes.
The deployed UID-1000 init containers exited zero, both DaemonSets became ready,
and GPU access remained available in Plex, Immich, NLLB and both Ollama workloads.

```sh
python3 tools/security/test_infra_guard_runtime.py
python3 tools/security/test_gpu_config_init_guards.py
python3 tools/security/generate_infra_guards.py --check
python3 tools/security/test_infra_guard_policy.py --kyverno /path/to/kyverno
```

## Persistence and scope

The infra-guards Argo Application manages the native fail-open mutation policy
and PostSync hook. Exact namespace/kind/name, service account, labels, image,
command, arguments, complete container/init inventory, mounts, volume declarations
and reviewed DaemonSet rollout strategy must match before mutation. Only selected
securityContext fields and the reviewed deployer Pod context change. Runtime
image pins intentionally require review on upgrades; audit exceptions separately
match exact repositories across versions.

The hook can GET/PATCH exactly six named controllers. It can list Longhorn
volume/node health and GET only the known GPU node for capacity checks. It has no
Secret access, namespace-wide patch access or broad MetalLB permissions; GET/PATCH access there is limited to the two named FRR controllers. GPU node Ready,
capacity and allocatable must remain eight. Longhorn volumes/nodes/disks must be
healthy before and between writes.

Every target passes contract, readiness and server admission preview checks
before the first persistent write. ResourceVersion-guarded metadata patches then
trigger admission one controller at a time, with at least 15 seconds of stable
readiness. A mismatch or failure stops later targets. Failed hooks are retained;
successful hooks are removed. The hook itself is non-root, drop ALL, no escalation,
RuntimeDefault and read-only-root, with a memory limit and no CPU limit.

Unit and actual CEL cases cover scope, idempotence, unchanged companions, extra
mounts/volumes, privileged targets, critical config-init environment/field refs,
rollout strategy, failed preflight, failed rollout, and unhealthy storage/GPU gates.
Generated consistency and repository CI checks remain required. Render/schema
validation alone does not prove controller API activity, CSI health or GPU access.
