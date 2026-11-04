# Longhorn component hardening

This change covers five CSI client containers, the UI and the global manager, with exact
image references and workload contracts recorded in
`component-security-catalog.json`. It does not modify the privileged CSI driver,
node-driver registrar, node managers, engines, or volume ownership.

## Reviewed requirements

The live CSI socket is `/csi/csi.sock`, backed by
`/var/lib/kubelet/plugins/driver.longhorn.io/csi.sock`. Inspection found UID/GID
0:0, mode 0755, with a 0755 parent directory. Unix socket clients need write
permission on the socket to connect. UID 1000 cannot connect; adding only a
non-root guard would break the CSI clients. Changing socket ownership or mode
would require a separate driver-side design.

The four controller sidecars and the node liveness probe therefore retain UID/GID
0:0 and an explicit `runAsNonRoot: false`. They receive `privileged: false`,
`allowPrivilegeEscalation: false`, `capabilities.drop: [ALL]`, and container-level
`seccompProfile.type: RuntimeDefault`. Their root audit findings intentionally
remain visible until the separately reviewed, audit-only root exceptions in
[the follow-up review](../docs/csi-root-and-speaker-seccomp-review.md) are published.

The UI already runs as UID 499/GID 486. Its image startup script generates nginx
configuration in `/var/config/nginx`, uses the chart's writable emptyDir mounts,
and listens on unprivileged port 8000. It receives the same guards with UID 499,
GID 486 and `runAsNonRoot: true`. No fsGroup or ownership changes are needed.

Reviewed images:

| Workload | Container/image |
|---|---|
| Deployment/csi-attacher | `docker.io/longhornio/csi-attacher:v4.13.0` |
| Deployment/csi-provisioner | `docker.io/longhornio/csi-provisioner:v6.3.0` |
| Deployment/csi-resizer | `docker.io/longhornio/csi-resizer:v2.2.1` |
| Deployment/csi-snapshotter | `docker.io/longhornio/csi-snapshotter:v8.6.0` |
| DaemonSet/longhorn-csi-plugin | `docker.io/longhornio/livenessprobe:v2.20.0` only |
| Deployment/longhorn-ui | `docker.io/longhornio/longhorn-ui:v1.13.0` |
| Deployment/longhorn-global-manager | `docker.io/longhornio/longhorn-manager:v1.13.0` |

Declared image references are exact string matches, not digest verification.
Changes to images, container order/count, command, arguments or service account
fall outside the reviewed contract and require updating the catalog and tests.

The global manager runs only cluster-wide Pod/PV controllers, leader election
and its port-9505 health listener. It has no host or persistent-volume mounts.
It receives the same guards as the UI with UID/GID 1000:1000 and
`runAsNonRoot: true`. Its projected service-account token and CA files were
verified mode 0644; credential contents were not read. The controller identity
and Kubernetes RBAC stay unchanged. Catalog-driven UID/GID/index maps preserve
the existing UI and CSI settings while adding this distinct non-root identity.

## Persistence and rollout

Chart 1.13.0 exposes no UI container securityContext value, and the manager's
CSI Deployment generator supplies no security contexts for these clients.
`policy-component-security.yaml` uses a fail-open native Kubernetes
MutatingAdmissionPolicy, independently of the five Audit/Ignore Kyverno policies.
It matches only the seven reviewed workload identities in `longhorn-system`,
application labels, service accounts, exact container images, commands and
arguments. The node DaemonSet also requires the two privileged companion images
and their privileged flags to match. Only the selected container's security
context changes; all other fields and containers remain intact.

The Longhorn chart Application enables admission-aware server-side diff so
Argo CD compares the UI against its injected security context without repeatedly
trying to remove it. This does not add a broad ignoreDifferences rule.

A PostSync hook uses get/patch permission restricted to the six Deployment
names and one DaemonSet name. It first verifies every target's reviewed contract
and fully healthy state, and server-dry-runs annotation patches for all seven.
Each preview must change exactly the intended security fields. It then refetches
each workload, guards against concurrent edits with a resourceVersion test,
applies only an annotation patch, and waits for updated-generation/full-replica
rollout completion before changing the next target. Later targets are left alone
on failure. Failed hooks are retained; successful hooks are deleted.

Updating liveness necessarily rolls the CSI driver Pods. The existing
DaemonSet strategy remains `maxUnavailable: 1`, `maxSurge: 0`; the driver and
registrar security contexts are preserved. The hook checks that strategy before
writing. No engines, volumes, PVCs, mounts or ownership are modified. The final
hook checks HTTP 200 from the UI static page and its manager API proxy.

## Validation evidence and limits

- Previous recurring-job rollout at `8fa5463`: all 14 templates have the intended
  guards, all 14 CronJobs pass all five Kyverno policies, and newly scheduled trim
  jobs completed successfully. CI passed. Snapshot/backup completion is still
  subject to their normal schedules; this work does not manually trigger them.
- Exact UI image tested locally as UID/GID 499:486, drop ALL, no-new-privileges and
  default seccomp. Static content and a local mock API proxy both returned 200.
  Process state confirmed UID/GID, zero effective capabilities, NNP 1, seccomp 2.
- Exact CSI images tested against an isolated mock gRPC driver socket with
  production-equivalent owner/mode: UID 1000 was denied; UID 0 with drop ALL,
  no-new-privileges and default seccomp completed CSI identity/capability RPCs.
  The local host's SELinux peer labeling blocked even the root test initially;
  labeling was disabled only on mock-test containers to isolate DAC/syscall
  behavior. Production SELinux configuration is unchanged and is not validated
  by that local probe. No production API credentials or host CSI socket were used.
- The global-manager image was run as UID/GID 1000:1000 with drop ALL and
  no-new-privileges against synthetic local Kubernetes APIs. Informer caches
  synchronized, the mock leader Lease was acquired, both global controllers
  started, and `/v1/healthz` returned 200. Process checks confirmed UID/GID 1000,
  zero effective capabilities, NNP 1 and seccomp 2. All API objects were synthetic;
  no production tokens, PVs or Pods were used by the test. This is startup and
  leader-election compatibility evidence, not real PV/Pod reconciliation proof.
- The earlier CSI/UI rollout at `20dac450` completed successfully, both hooks
  succeeded, UI static/proxy checks returned 200, and the guards were confirmed
  in running CSI and UI processes. Current UI reports pass all five audits;
  the four CSI controller Deployments retain only their reviewed root findings.
  The node-plugin report still includes findings from its privileged companions.
- Native policy CEL/API schemas pass server-side dry-run. The same expressions
  and JSONPatch are evaluated offline through a temporary Kyverno MutatingPolicy
  wrapper: 79 positive/negative-scope cases, plus 14 idempotence checks. Whole-spec
  comparisons prove unrelated fields and privileged companions are preserved.
- Repository tests cover exact RBAC scope, preflight-before-write, generation and
  replica rollout gates, Argo diff settings, and deterministic generated files.

Local mocks do not prove real attach, provision, resize or snapshot operations.
After pushing, verify CI, policy activation, PostSync success, seven healthy
workloads, process guards, UI HTTP/proxy behavior, sidecar logs/leadership and
Kyverno results. Verify the global-manager Lease holder and controller cache/leadership logs,
then observe normal storage operations; do not provoke production
storage changes merely to clear reports. Historical ReplicaSets, Pods and Jobs
retain their previous templates until ordinary cleanup.

Generate and test:

```sh
python3 tools/longhorn/generate-component-security.py --check
python3 tools/longhorn/test-component-security-policy.py --kyverno /path/to/kyverno-1.19.2
# Manual isolated startup test: requires Podman, the pinned image and free local port 9505.
python3 tools/longhorn/test-global-manager-startup.py
```

To roll back, disable/remove this policy's binding first, then restore only the
selected container security contexts from the reviewed fixtures. Removing the
policy alone does not revert an already changed template. Do not delete running
Jobs, engines or storage resources. A failed rollout needs inspection before
retrying; subsequent syncs create a new hook and retain the failed one.

Sources: [pinned CSI generation](https://github.com/longhorn/longhorn-manager/blob/v1.13.0/csi/deployment_util.go),
[pinned socket creation](https://github.com/longhorn/longhorn-manager/blob/v1.13.0/csi/server.go),
[pinned global command](https://github.com/longhorn/longhorn-manager/blob/v1.13.0/app/global.go),
[pinned global controllers](https://github.com/longhorn/longhorn-manager/blob/v1.13.0/controller/controller_manager.go),
[pinned UI startup script](https://github.com/longhorn/longhorn-ui/blob/v1.13.0/scripts/start-nginx.sh),
[Argo admission-aware diff](https://argo-cd.readthedocs.io/en/latest/user-guide/diff-strategies/#mutation-webhooks).
