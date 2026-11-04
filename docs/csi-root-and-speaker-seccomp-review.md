# CSI root exceptions and MetalLB speaker seccomp — 2026-11-04

Prepared local GitOps changes cover 15 running Pods: four Longhorn CSI controller
Deployments with three replicas each, and three MetalLB speaker Pods. No live
workload or exception was patched during this batch.

## Longhorn: retain the verified socket-access requirement

Fresh inspection of the driver container found `/csi` and `/csi/csi.sock` owned by
0:0 with mode 0755. Existing controller mounts use this same driver hostPath.
Unix-domain socket clients need write permission to connect; changing clients to
non-root without a separate socket-permission design would break storage control.
The four client images are distroless and lack shell/stat tools; the inspection
used the existing driver container rather than introducing a diagnostic Pod.
See `longhorn/component-security.md` for the existing runtime and socket probes.

Live sanitized Deployment inspection confirmed all four clients already declare
UID/GID 0, privileged=false, no escalation, drop ALL without additions, and
RuntimeDefault. New root exceptions require these guards to remain intact,
along with exact container image, workload/controller identity, namespace,
service account and labels. Unexpected root sidecars and ephemeral containers
are not approved. These are root exceptions only; capability, escalation,
privileged and seccomp policies remain independently active. Image strings remain
tag-based and changing their contents is an existing trust limitation.

Covered Deployments: csi-attacher, csi-provisioner, csi-resizer, csi-snapshotter.
After publication their twelve Pod root results should become Skip, not Pass.
No CSI rollout, socket ownership change or storage-operation test is needed for
an audit-only exception. Provisioning/attach/resize/snapshot operations were not
triggered in production during this review.

## MetalLB: make existing default seccomp explicit

Pinned chart 0.16.1 renders `speaker.securityContext` at Pod level. All three
speaker Pods are Ready, non-privileged and lack seccomp overrides. Read-only
kubelet configz inspection confirmed seccompDefault=true on all three nodes.
They therefore already inherit RuntimeDefault; the explicit value records that
same behavior and closes the declaration finding. The speaker keeps hostNetwork,
NET_RAW, drop ALL, read-only root and no escalation. FRR helpers are untouched.

Helm before/after comparison proved the speaker DaemonSet changes only by adding
Pod-level seccompProfile.type=RuntimeDefault. This template change rolls three
speaker Pods when published; verify Ready status, service advertisements and
representative LoadBalancer endpoints after Argo reconciliation. The rendered
FRR configurations and capabilities are not changed.

## Verification and publication

Kyverno CLI 1.19.2 passed 56 positive/negative CSI exception cases, including
changed images/identities, extra capabilities, missing drop, escalation,
Unconfined, privileged mode, changed UID/GID, noncompliant sidecars and ephemeral
containers. Existing full-policy fixtures now exercise required companion guards.
Fixture hashes use a letter prefix to avoid the CLI YAML converter interpreting
scientific-looking hashes as numbers; policy identity rules are unchanged.

MetalLB chart rendering passed; all four rendered Deployment/DaemonSet resources
passed strict Kubernetes 1.37.1 schema validation. Runtime-contract validation,
generated-exception consistency and whitespace checks passed. Repository tests:
287 run, 16 skipped, successful. The full rendered-policy CLI suite remains a CI
publication gate; only the focused 56-case CEL suite was rerun for this batch.

At the start of this turn local prior commit 6b973a4b was absent from GitHub's
commit API, Argo kyverno-exceptions still used a8bfc45d, and the prior six capability
findings remained Fail. No claim is made that those exceptions have deployed.
Current main CI was still running Kyverno tests. Both batches need publication
and live report verification; do not infer deployment from a local clean tree.
