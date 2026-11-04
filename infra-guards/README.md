# Reviewed infrastructure guards

Prepared batch: eight selected container roles across six currently running Pods
(16 controller/init instances, counting four FRR init roles on each of three nodes).
This is runtime hardening, not additional Kyverno exceptions. The five audit
policies and repository-scoped audit exception matching remain unchanged.

| Workload | Selected roles | Identity |
| --- | --- | --- |
| gpu-operator/gpu-operator | gpu-operator | UID/GID 1000, matching current process |
| longhorn-system/longhorn-driver-deployer | longhorn-driver-deployer, wait-longhorn-manager | UID/GID 1000; no host or data mounts |
| metallb-system/metallb-frr-k8s-statuscleaner | frr-k8s-statuscleaner | UID/GID 1000; API client and port 19443 |
| metallb-system/metallb-frr-k8s | cp-frr-files | Existing UID/GID 100:101 retained |
| metallb-system/metallb-frr-k8s | cp-reloader, cp-metrics, cp-frr-status | Root retained only for existing root-owned emptyDir destinations |

Selected roles receive privileged=false, drop ALL, no escalation and RuntimeDefault,
plus explicit identities/non-root flags. The FRR daemons, reloader, metrics/status
companions, NVIDIA privileged device plugin/discovery/validator processes and all
GPU allocation/device/runtime settings are untouched. The FRR parent Pods still
have remaining findings; hardening the copy helpers alone does not clear every
policy for those Pods.

## Requirements and compatibility evidence

- GPU Operator's live main process already runs UID/GID 1000 with zero effective
  capabilities and seccomp mode 2. Its CLI starts under the proposed guards.
- Longhorn's pinned [driver source](https://github.com/longhorn/longhorn-manager/blob/v1.13.0/app/driver.go)
  configures Kubernetes clients and deploys CSI resources through the API. Host
  detection runs in separately created helper workloads, not this controller.
  Its CLI starts non-root; the actual curl/HTTP wait logic passed non-root against
  a disposable loopback HTTP server. No production Kubernetes API write was made.
- The current deployer token is root-owned 0600. The replacement Pod gets explicit
  UID/GID and fsGroup 1000 for projected-token access. The mutation requires the
  existing zero-volume/zero-mount controller contract, so this group change cannot
  silently apply to a newly added persistent volume. Token ownership/readability
  and authenticated controller activity must still be verified after rollout.
- Status cleaner already drops capabilities, disables escalation and uses a
  read-only root. Its binary starts as UID/GID 1000. Its certificate Secret uses
  mode 0644 and its listener is above 1024; no certificate values were read.
- Real FRR copy commands passed on disposable tmpfs destinations, including the
  non-root UID/GID 100:101 cp helper. Commands do not preserve/chown ownership.
  Runtime probes confirmed zero capabilities, NoNewPrivs=1 and seccomp mode 2.
- Three nodes already use kubelet-default seccomp. FRR's existing rolling strategy
  permits one unavailable Pod. There are currently no MetalLB BGP peers or BGP
  advertisements; the speaker/L2 configuration is unchanged.

Reproduce isolated compatibility checks with:

```
python3 tools/security/test-infra-guard-runtime.py
```

These checks establish CLI, file-copy, token-layout requirements and HTTP-wait
compatibility. They do not substitute for authenticated controller function,
webhook behavior, real CSI reconciliation or LoadBalancer reachability after rollout.
No production secrets, mounts, GPU devices or data were used by the probes.

## Persistence, scope and rollout

A separate `infra-guards` Argo Application/AppProject manages the policy and hook.
It grants only the required cluster-native mutation kinds and specific namespaced
configuration/RBAC/Job kinds. It has no Secret permissions or ClusterRoleBinding.
Its service account can get/patch exactly four named controllers; it can also list
Longhorn volume/node health in longhorn-system. No namespace-wide patch permission
is granted. The existing kyverno namespace hosts the hook, not new Kyverno policy
behavior. Existing namespace network policy selectors do not restrict this hook.

The native MutatingAdmissionPolicy uses failurePolicy=Ignore and matches exact
namespace/kind/name, service account, labels, complete container/init inventory,
image/command/args, mounts and volume declarations. The FRR rolling strategy must
remain exactly reviewed. No selected target may already be privileged. It patches
only selected context fields and the deployer's reviewed Pod context. Other
fields and privileged companions remain byte-for-byte unchanged in spec previews.
Image/command pins are retained here because this policy changes runtime guards;
future versions require review and catalog regeneration. An unknown contract is
not mutated, and the backfill refuses to proceed; audit exception version handling
is separate and remains repository-scoped.

The PostSync hook checks every contract, readiness and server admission dry run
before its first persistent write. It then uses resourceVersion-guarded metadata
patches to trigger admission, rolls one controller at a time and waits at least
15 seconds of stable readiness. FRR itself rolls one node at a time. Longhorn
volume/node/disk health gates run before hook writes and between targets. These
checks gate hook actions, not unrelated Argo/Helm activity. Failed Jobs are retained;
successful hooks are removed. Readiness or exact-spec failure stops later targets.

GPU Operator and MetalLB Applications use admission-aware server-side diff to
avoid fighting the injected contexts; Longhorn already has that setting. The
hook is itself non-root, drop ALL, no escalation, RuntimeDefault and read-only-root.
It has a memory limit and no CPU limit.

## Validation and operational boundaries

57 real CEL mutation/scope/idempotence checks passed with Kyverno CLI 1.19.2.
The full repository suite passed: 306 tests run, 16 skipped. All 11 rendered
resources passed strict Kubernetes 1.37.1 schema validation; resource-budget and
restricted-context checks passed.
Positive cases prove selected-context-only changes; negative cases cover identity,
images/commands, extra mounts/volumes, inventory changes, privileged targets and
unreviewed FRR rollout strategy. Unit tests cover least-privilege RBAC, unchanged
companions, token-volume boundary, incomplete readiness, failed preflight making
no persistent write, failed rollout stopping later targets, and unhealthy storage preventing writes. Generated-bundle
consistency and targeted rendering/resource/schema checks are required in CI.

Publication and live validation remain pending. Publishing rolls six Pods, including
three FRR Pods and the GPU Operator controller; existing GPU workloads and the
MetalLB speaker are not directly restarted by this batch. After reconciliation,
verify controller API activity, certificate/webhook readiness, CSI/storage health,
LoadBalancer endpoints, GPU node/resource counts and current-Pod Kyverno reports.
Do not claim the expected three controller finding groups are cleared until those
live checks pass. The remaining privileged GPU helpers, FRR main containers,
MetalLB speaker and OpenBao OnDelete replacement need separate review.
