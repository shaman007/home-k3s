# Privileged runtime audit exceptions — 2026-11-04

Follow-up: image checks now match exact registry/repository across tag/digest
updates; version pins described below record the original review. CSI driver and
registrar escalation requirements are also covered, while liveness must keep its
no-escalation guard. See [rollout safety review](longhorn-rollout-safety.md).

This batch classifies verified infrastructure requirements. It changes no workload
privileges, guards, images, GPU allocations, storage ownership or networking. All
five audit policies remain Audit/Ignore. Exceptions report Skip, retain the
existing expiry, and do not represent application compliance or reduced privilege.

Kubernetes gives privileged containers all capabilities and runs them with
unconfined seccomp regardless of declarations. Adding drop ALL or RuntimeDefault
would not provide those protections while privileged mode is retained. Source:
https://kubernetes.io/docs/concepts/security/linux-kernel-security-constraints/

## Scope and prior requirements

Only eight workload identities with existing reviewed privileged exceptions gain
capability/seccomp exceptions (twelve currently running Pods):

- Longhorn engine-image DaemonSet: three Pods, installs engine binaries on nodes.
- Three exact Longhorn instance-manager Pods: existing owner UID and node bindings.
- One exact Longhorn share-manager Pod: existing owner UID and volume binding.
- Longhorn CSI node DaemonSet: three Pods, device access and bidirectional mounts.
- NVIDIA DCGM exporter and operator validator: one Pod each on the GPU node,
  including their existing privileged validation init containers.

Fresh sanitized workload inspection confirmed exact declared images and privileged
roles against the existing catalog. Existing reviewed host/device/storage needs
are retained; this batch does not claim privilege elimination was tested. No
benchmark, new storage operation or GPU measurement was triggered.

The CSI liveness probe remains non-privileged, UID/GID 0, drop ALL, no escalation
and RuntimeDefault. Its root exception now requires all those guards. The driver
and registrar root roles must remain privileged to match their separate reviewed
root requirements. Root-owned 0755 CSI socket access remains the documented reason.

## Narrow matching and negative tests

Each new capability/seccomp exception requires the existing privileged-role
approval for the same container and exact image. The generated expression also
requires privileged=true and pins capability and seccomp declaration maps to the
reviewed current values, along with existing namespace, owner/name, labels and
service-account checks. Existing direct Pod exceptions retain owner UID bindings.
Non-privileged companions must independently comply; no ephemeral roles are
approved. Disabling privileged mode, changing declarations or images, or adding
noncompliant companions makes the exception stop matching.

Kyverno CLI 1.19.2 passed 176 cases across all eight identities and both policies:
approved, changed image/namespace/owner/account/labels, changed capability/seccomp
maps, disabled privileged mode, and new noncompliant sidecars/ephemeral containers.
The maintained full policy suite now exercises the new policy type and roles.
Repository tests passed: 289 run, 16 skipped. Generated-bundle consistency,
runtime-contract and whitespace checks passed. The complete rendered
policy suite still runs in CI after publication.

The unchanged four non-privileged CSI controller root exceptions and three-speaker
seccomp patch from the prior batch are separate. During this turn all six
application capability findings were verified Skip after Argo synced 59d000ef.
The twelve CSI controller root reports were still awaiting scan updates, and the
MetalLB Application still lacked the new speaker value despite main containing it.
Do not call those rollouts complete until the Application and reports converge.

This batch is local only. After publication expect up to 24 capability/seccomp
Fail results and three CSI root Fail results to become Skip on these twelve Pods.
Verify actual reports and workload health; controller and historical reports can
duplicate Pod findings. GPU Operator controller, mixed GFD/device-plugin init
roles, MetalLB FRR, and OpenBao OnDelete replacement remain separate work.
