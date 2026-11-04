# Reviewed infrastructure guards

Current catalog: 15 selected roles across eight running Pods (33 controller/init
instances). The latest extension is reviewed in
[GPU/FRR helper hardening](../docs/gpu-frr-helper-hardening.md): 17 additional contexts
across five Pods. It includes non-root GPU config init and FRR exporters, a single
required reloader DAC capability, and explicit existing FRR seccomp. The original
controller batch below remains part of the catalog. These are runtime guards,
with separately reviewed audit classifications for existing privileged GPU actors.

## Requirements and compatibility evidence

- GPU Operator's live main process already runs UID/GID 1000 with zero effective
  capabilities and seccomp mode 2. Its CLI starts under the proposed guards.
- Longhorn's pinned [driver source](https://github.com/longhorn/longhorn-manager/blob/v1.13.0/app/driver.go)
  configures Kubernetes clients and deploys CSI resources through the API. Host
  detection runs in separately created helper workloads, not this controller.
  Its CLI starts non-root; the actual curl/HTTP wait logic passed non-root against
  a disposable loopback HTTP server. No production Kubernetes API write was made.
- The deployed deployer token is mode 0640, owner 1000:1000. Authenticated API
  reads and CSI reconciliation were verified after the preceding rollout. Explicit
  UID/GID and fsGroup 1000 provide projected-token access. The mutation requires the
  existing zero-volume/zero-mount controller contract, so this group change cannot
  silently apply to a newly added persistent volume.
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
configuration/RBAC/Job kinds. It has no Secret permissions. One narrowly scoped
ClusterRoleBinding permits only GET of the known GPU node for resource-health verification.
Its service account can get/patch exactly six named controllers; it can also list
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

103 real CEL mutation/scope/idempotence checks passed with Kyverno CLI 1.19.2.
The latest helper review records current repository/runtime/exception checks.
All 13 rendered resources passed strict Kubernetes 1.37.1 schema validation;
resource-budget and restricted-context checks passed.
Positive cases prove selected-context-only changes; negative cases cover identity,
images/commands, extra mounts/volumes, inventory changes, privileged targets and
unreviewed FRR rollout strategy. Unit tests cover least-privilege RBAC, unchanged
companions, token-volume boundary, incomplete readiness, failed preflight making
no persistent write, failed rollout stopping later targets, and storage/GPU health
failures preventing writes. Generated-bundle consistency and targeted rendering/resource/schema checks are required in CI.

Publication and live validation of this extension remain pending. It rolls five
Pods: three FRR Pods and two GPU helper Pods. Existing GPU workloads and the
MetalLB speaker are not directly restarted by this batch. After reconciliation,
verify controller API activity, certificate/webhook readiness, CSI/storage health,
LoadBalancer endpoints, GPU node/resource counts and current-Pod Kyverno reports.
The preceding three controller finding groups have already cleared; the new GPU
classifications and FRR results must still be verified after this extension.
Remaining FRR main requirements, MetalLB speaker and OpenBao OnDelete replacement
need separate review.
