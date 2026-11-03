# Kyverno audit rollout

Kyverno 1.19.2 (Helm charts 3.9.2) is deployed by the `kyverno` and
`kyverno-policies` Argo CD Applications in a dedicated `kyverno` AppProject.
The controller and upstream policies use pinned official Helm charts. The
`kyverno-exceptions` Application reads the reviewed exceptions and the custom
capability audit from this directory.

## Scope and safety

- Three admission replicas, spread across nodes, with a minimum-available-two PDB.
- Two reports replicas; background scans run hourly.
- CEL ValidatingPolicies audit privileged containers, privilege escalation,
  missing `runAsNonRoot`, explicit capability drops, and seccomp profiles. They do not deny requests. `kyverno` and `kube-system`
  are excluded from these policies.
- Policies use `failurePolicy: Ignore`; the admission controller also forces
  fail-open behavior for validation policies. Kyverno's internal policy-validation
  and generated-resource protection webhooks retain their upstream behavior; the
  latter only selects resources carrying Kyverno generation labels. Native
  ValidatingAdmissionPolicy generation and default image-registry mutation are
  disabled.
- Background mutation/generation and cleanup controllers are disabled because
  this rollout only validates and reports. No mutation/image-signature policy
  is installed.
- The namespace enforces Restricted Pod Security. Containers have memory budgets
  and no CPU limits. Ingress permits Kyverno and monitoring namespaces; a CiliumNetworkPolicy in
  the policy chart additionally permits API-server/node identities on TCP 9443.
  The network policy syncs before the validating policies to avoid bootstrap
  deadlock and avoids hard-coded node IP addresses.
  These chart policies do not restrict egress.
- Argo CD uses server-side diff to compare API-defaulted CRDs without broad
  ignore rules. CEL CRDs receive explicit instance labels through the
  `kyverno-api` subchart for Argo CD tracking.

## Compatibility and GitOps bootstrap

The operator explicitly approved this audit-only deployment on Kubernetes
1.37.1, outside Kyverno 1.19's published tested range (1.33–1.35). Runtime
verification is required; successful deployment does not establish upstream
support. Recheck compatibility before upgrades or enabling enforcement.

The initial controller and policy Applications were bootstrapped directly and
subsequently managed through Git. New exception configuration is prepared in
Git for normal parent-Application reconciliation; do not apply it manually.

## Reviewed exceptions and additional audits

The reviewed [catalog](exception-catalog.json) contains 66 policy-specific
exceptions for 48 workload identities. Each entry records its reason, evidence,
service account, stable labels, approved container role/name and exact declared
image reference. These are explicit reviewed entries, not an import of every
current failure. Mutable image references remain string matches; they are not
resolved to immutable digests by the exception.

Scope includes retained permission-fixing init containers, root startup services,
Collabora's sandbox helper, RIPE Atlas's setuid helper, and verified privileged
GPU, Longhorn and image-builder containers. Four operator-created Longhorn Pods
also pin the owner UID and exact Pod name; replacements intentionally need review.
Vendor sidecars and missing guard fields without evidence of a root requirement
remain findings. CrowdSec receives no exception.

Exceptions reference only the existing root, escalation or privileged policy,
with one policy per exception. They check namespace, workload/controller identity,
service account, labels, container role, name and image. All other regular, init
and ephemeral containers must comply with that policy; ephemeral containers are
never exempt. A repaired workload reports Pass rather than Skip. Controller and
Pod ownership checks depend on the existing RBAC/GitOps trust boundary; labels
and owner references are not an independent authorization mechanism.

[CEL PolicyExceptions](https://kyverno.io/docs/guides/exceptions/) are enabled
only in the existing `kyverno` namespace, without granting application service
accounts write access there. Exceptions report Skip and expire on
2027-02-01. Review them when an image, chart, startup contract or ownership changes.
The pinned CLI currently ignores `expiresAt` in offline tests, so offline results
do not prove expiration. Verify an expired exception against the running
controller after rollout before relying on this field operationally.

Two additional policies remain strictly Audit/Ignore:

- `require-drop-all-capabilities` requires explicit `drop: [ALL]` on every
  regular, init and ephemeral container, allowing only `NET_BIND_SERVICE` adds.
  The chart's strict-capabilities template accepts absent capabilities/drop
  fields, so this repository supplies the explicit check instead.
- `restrict-seccomp-strict` requires an effective `RuntimeDefault` or `Localhost`
  profile, including init and ephemeral containers. Pod-level inheritance works;
  a container-level `Unconfined` override is reported.

Neither new audit has exceptions yet. Legitimate capability additions or seccomp
requirements will appear as findings for separate review. Existing namespace
exclusions remain `kyverno` and `kube-system`. This change does not mutate or
restart application workloads and does not enable denial.

## Validation and rollout

Generate and check the deterministic exception bundle with:

```sh
python tools/kyverno/generate-exceptions.py --check
python tools/ci/render-applications.py --output /tmp/rendered-applications
python tools/kyverno/test-audit-policies.py --rendered /tmp/rendered-applications
```

CI installs the checksum-pinned Kyverno 1.19.2 CLI and evaluates the actual
rendered policies with approved fixtures and negative cases: changed images,
owners, namespaces, service accounts, unexpected containers, repaired workloads,
and missing capability/seccomp fields. Fixtures omit credentials and are never
submitted to the cluster. Operator-created workloads use reviewed sanitized
snapshots when they are absent from Git-rendered application sources.

After publication, verify the following before closing the rollout:

1. All three Applications are Healthy/Synced and admission/report controller
   replicas are Ready with exception support restricted to namespace `kyverno`.
2. All five ValidatingPolicies are Ready and retain Audit/Ignore. Confirm report
   evaluation has no errors and the two additional audits produce findings.
3. Approved current workloads report Skip, repaired workloads Pass, and unreviewed
   containers remain Fail. Allow the hourly background scan to refresh reports.
4. Verify exception expiry and admission/background matching against safe
   unscheduled test fixtures; offline CLI expiry is not runtime proof.

## Inspect

```sh
kubectl get applications -n argocd kyverno kyverno-policies
kubectl get deployments,pods -n kyverno
kubectl get validatingpolicies.policies.kyverno.io
kubectl get policyreports.wgpolicyk8s.io -A
kubectl get clusterpolicyreports.wgpolicyk8s.io
```

Review report results by policy, namespace, resource, and rule before hardening
individual workloads. GPU, storage, and builder exceptions require deliberate
review; audit failures do not mean those services should be changed blindly.
Do not switch policies to `Deny`/enforcement as part of routine reconciliation.

## Initial verification

The three policies became Ready and generated pass/fail reports with no
evaluation errors. Temporary zero-replica Deployments produced three passes for
the compliant case and three failures for the violating case; no privileged
containers were run. Both cases were accepted, and the temporary Deployments
were removed. All five controller pods were Ready, both Kyverno Applications
were Healthy/Synced, and the full repository suite passed (247 tests, 16 skipped).
The initial background scan recorded 939 failures and zero evaluation errors;
counts include controllers and Pods and are not counts of distinct security
issues. API-server/node access to webhook readiness was tested directly
from all three nodes after correcting Cilium ingress. Server-side dry-run admission checks completed
without webhook timeouts after that correction.

## Remaining non-root workloads

See [the application audit and retained exceptions](../docs/non-root-audit.md)
for compatible application changes, runtime evidence, and remaining chart gaps.
