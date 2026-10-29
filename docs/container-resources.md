# Container resource policy

Containers must have a memory request and limit, either in their pod template or
from a namespace Container LimitRange at admission. Keep CPU requests for
scheduling and contention fairness, but do not set CPU limits or namespace CPU
ceilings. A missing Helm value does not necessarily remove a chart default:
GPU Operator's controller and Cilium's CNI installer require `limits.cpu: null`.

CI renders every Application, then runs
`python tools/ci/check-container-resources.py --rendered <directory>` to check
regular and init containers, including chart hooks. The check considers the
LimitRanges in the rendered inventory. Operator-generated pods also need review
of the operator CR/settings and verification after deployment; they are not
present in Helm output.

## Sizing evidence, 2026-10-29

Thanos query: `max by(namespace,container)
(max_over_time(container_memory_working_set_bytes{namespace=~"longhorn-system|gpu-operator|lenka",container!="",container!="POD"}[14d]))`.
These are maxima among available samples, not a guarantee about future peaks or
complete sampling over the entire window. Memory limits include headroom for
startup and maintenance. Review OOM events and actual usage after rollout.

| Component | Observed maximum | Memory request / limit |
| --- | --- | --- |
| Longhorn instance manager | 2.51 GiB | 1 GiB / 8 GiB namespace fallback |
| Longhorn manager | 330 MiB | 256 MiB / 1 GiB |
| Longhorn global manager | 70 MiB | 128 MiB / 512 MiB |
| CSI attacher/resizer/snapshotter | 67–68 MiB | 64 MiB / 256 MiB |
| CSI provisioner / Longhorn CSI plugin | 80–82 MiB | 128 MiB / 512 MiB |
| CSI registrar / liveness probe | 25–31 MiB | 32 MiB / 128 MiB |
| GPU DCGM exporter | 493 MiB | 512 MiB / 1 GiB |
| GPU device plugin / feature discovery | 36 / 55 MiB | 64 MiB / 256 MiB |
| GPU config-manager sidecars | 22 MiB | 64 MiB / 256 MiB namespace fallback |
| GPU validator | less than 1 MiB running | 32 MiB / 128 MiB; verify init stages |
| Lenka MySQL | 471 MiB | 512 MiB / 2 GiB namespace fallback |

Longhorn's fallback is deliberately generous because an OOM of an instance
manager affects multiple volumes. It also covers engine-image, share-manager,
pre-pull, driver-deployer and UI containers for which the pinned chart does not
expose individual resource settings. The 1 GiB default request conservatively
reserves additional memory for these small containers; the 8 GiB limit is a
ceiling, not an allocation. CSI resources use the native
`systemManagedCSIComponentsResourceLimits` setting. Manager/global-manager
resources use chart values. The old, excluded Longhorn LimitRange file is kept
aligned with the centrally deployed policy, rather than leaving a dangerous
512 MiB instance-manager default as reference material.

The GPU fallback applies to operator-created sidecars and init containers whose
resources are not individually exposed by the chart. Explicit exporter limits
can exceed the fallback; no namespace maximum prevents them. The unmanaged
Lenka Deployment remains outside GitOps workload ownership: the namespace policy
supplies its memory settings when its pod is recreated.

## Rollout and verification

Repository changes alone do not update running resources. This task did not
commit, push, or mutate the live cluster.

1. Review and publish the changes through the user's GitOps workflow. Ensure
   namespace-management permits GPU Operator and Lenka destinations, then sync
   namespace LimitRanges before changing operator workloads.
2. Roll GPU and Longhorn components in controlled batches. Changes to the CSI
   setting restart CSI components and can temporarily delay provisioning and
   attach/detach operations. Existing pods do not inherit a new LimitRange;
   recreate remaining unbudgeted pods under their owning controllers. Coordinate
   storage-critical instance-manager replacement with Longhorn's own lifecycle
   and volume health; do not delete all storage pods together.
3. The Cilium init-resource change changes its DaemonSet template and can restart
   agents. The known Cilium 1.20.4 restored-policy bug is still unresolved in this
   incident's checked upstream state. After each agent restart, verify realized
   policy directions and allowed/forbidden traffic. Use the separately authorized
   equivalent-policy refresh recovery if enforcement regresses; do not assume
   Ready means policies are enforced.
4. Check regular and init containers for positive memory requests/limits and
   absence of CPU limits, while preserving existing CPU requests. Inspect OOMs,
   pending pods, node reservations, all attached Longhorn volumes, GPU access,
   ExternalSecret readiness, and representative application requests.
5. Recheck Lenka MySQL and dynamically generated Longhorn/GPU pods explicitly;
   a successful Helm render does not prove admission or runtime behavior.
