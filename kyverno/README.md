# Kyverno audit rollout

Kyverno 1.19.2 (Helm charts 3.9.2) is deployed by the `kyverno` and
`kyverno-policies` Argo CD Applications in a dedicated `kyverno` AppProject.
The applications use the official pinned Helm charts; this directory contains
operator documentation, not a separate manifest source.

## Scope and safety

- Three admission replicas, spread across nodes, with a minimum-available-two PDB.
- Two reports replicas; background scans run hourly.
- CEL ValidatingPolicies audit privileged containers, privilege escalation, and
  missing `runAsNonRoot`. They do not deny requests. `kyverno` and `kube-system`
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

The AppProject and Applications were bootstrapped directly from the matching
local manifests without committing or pushing. They reconcile official chart
releases now. Publish the three `argocd/application-*kyverno*.yaml` files and the
project test change when ready so the parent application can adopt them and
restore these definitions after disaster recovery. Until then, they are absent
from remote Git; do not treat this as a fully published GitOps change.

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

The two bootstrapped Applications and their AppProject remain outside the remote
parent application until these files are published. Argo CD may consequently
report these three definitions as orphaned resources in the shared `argocd`
namespace. They have known ownership; do not delete them to silence the warning.

## Remaining non-root workloads

See [the application audit and retained exceptions](../docs/non-root-audit.md)
for compatible application changes, runtime evidence, and remaining chart gaps.
