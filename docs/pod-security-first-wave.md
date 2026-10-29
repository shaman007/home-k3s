# First-wave Restricted Pod Security enforcement

## Scope and defaults

On 2026-10-29 all three Talos API servers had effective PodSecurity defaults
`enforce=baseline`, `warn=restricted`, `audit=restricted`, all at `latest`.
`kube-system` was the sole namespace exemption; no username or runtime-class
exemptions were configured. Missing namespace enforcement labels inherit
Baseline; they do not mean admission is unrestricted.

Pin `enforce=restricted` and `enforce-version=v1.37` for these namespaces:

- Initial candidates: argocd, ca-scanner, cert-manager, external-secrets,
  headlamp, opensearch, searxng, stirling-pdf, unifi.
- Workloads hardened in this change: mempalace, loki, harbor, open-terminal.

Retain Restricted warning/audit at `latest`. Preserve existing ownership:
argocd and searxng use Argo managedNamespaceMetadata; headlamp and open-terminal
use their existing Namespace files; the remaining labels belong to
namespaces/namespaces.yaml. Do not introduce a second Namespace owner.

## Workload changes

- MemPalace: pod RuntimeDefault seccomp and drop ALL container capabilities.
- Open Terminal: declare its existing runtime UID/GID 1000, require non-root,
  disallow privilege escalation, drop ALL capabilities, use RuntimeDefault.
  Its writable /home/user PVC remains writable; do not force a read-only root
  filesystem as part of this change.
- Harbor: harden the wait-for-core BusyBox init container with UID/GID 65534,
  no privilege escalation, drop ALL and RuntimeDefault. Both active inline
  Helm values and the reference harbor/values.yaml are kept aligned.
- Loki: set RuntimeDefault on the Loki, gateway, canary and shared memcached
  pod contexts. The memcached context controls both cache StatefulSets. Skip
  the optional Helm test hook because this pinned chart exposes no security
  context settings for it. The active Loki canary is retained.

Storage/GPU/system exceptions and root-dependent database permission init
containers remain outside this wave. No cluster-wide defaults or exemptions
are changed.

## Connectivity exporter: deliberately pending image publication

The current image runs as root and has /app/check.py owned by root with mode
0600. Merely setting runAsNonRoot would break startup. The user authorized a
Dockerfile change in the separate Dockerfiles checkout, but deferred image
publication. The recipe now uses ADD --chmod=0644 and USER 65534:65534.
No image was built or published by this change.

Do not enforce Restricted on connectivity-exporter yet. After building,
publishing and verifying the exact new image, update the Deployment image and
integrate tools/nonroot-security-context.patch.json from the exporter folder.
That JSON patch is review material only, excluded from the Application's
non-recursive source. Its paths are guarded by a container-name test. Verify
all configured checks and the metrics output as UID 65534 before enabling
Restricted v1.37 for that namespace. Existing no-escalation, capability-drop,
seccomp and read-only-root settings are preserved.

## Verification and rollout

Render every Argo Application and run check-restricted-contexts.py. It is a
regression guard for common Linux contexts, not a complete implementation of
versioned Pod Security Standards. It includes init containers, Jobs and CronJobs,
and covers already-enforced namespaces as well as this wave.

37 rendered first-wave pod templates passed server-side create dry runs with no
Pod Security warnings. StatefulSet dry-run Pods included generated PVC references.
The transient cert-manager startup hook's service account was substituted with
its namespace's default service account for this PSA-only check, since the hook
account does not currently exist. PSA has no username or runtime-class exemptions,
so this does not alter its security-context evaluation. Dry runs do not prove
image startup, write permissions, functional behavior or a successful rollout.

Deploy and verify hardened workload templates first, then enable enforcement
namespace by namespace. Existing pods are not evicted by namespace relabeling,
but replacement pods will be rejected if their templates still violate policy.
If GitOps reconciles applications concurrently, transient FailedCreate events
can occur until matching workload changes arrive; stage the workload and
namespace updates deliberately during deployment.

For each namespace, check replacement-pod readiness and logs, application
requests, storage writes where applicable, Job/CronJob paths and admission
warnings. Explicitly test Harbor jobservice startup, Loki log ingestion/query
and canary, MemPalace MCP access, and Open Terminal command execution and PVC
writes. No live workload or namespace mutation was performed by this repository
preparation. Commit/push and live rollout require user authorization.

References:
- https://kubernetes.io/docs/concepts/security/pod-security-admission/
- https://kubernetes.io/docs/concepts/security/pod-security-standards/
