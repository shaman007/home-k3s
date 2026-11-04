# Longhorn image-prepull sidecar hardening — 2026-11-04

The existing manager DaemonSet has a second, non-privileged container solely to
cache the share-manager image. Its entire command is
`sh -c 'echo share-manager image pulled && sleep infinity'`. It has no host,
persistent-data or application volume mounts. It needs neither root nor Linux
capabilities. The separate privileged storage-manager container keeps its existing
image, command, mounts and privileges.

The component catalog now selects only index 1 of this exact two-container
DaemonSet, requiring the exact sidecar image/command/service account and the
existing main manager image/name/privileged flag. It assigns UID/GID 65534,
runAsNonRoot=true, privileged=false, no escalation, drop ALL and RuntimeDefault.
DaemonSet companion validation was generalized to every other container index;
existing CSI companion checks remain equivalent. The guarded backfill hook
retains its preflight/dry-run/exact-diff and readiness checks before writes.

A disposable rootless Podman test used the exact deployed share-manager image
index digest sha256:53950f78b7af38b8a943c298cd3020622191a4661a13036f69d83c154cc8690d
with network=none and no production mounts. Only the echo/sleep command ran;
the share-manager server was never started. It stayed Running as UID/GID 65534,
printed the expected message, had zero effective/permitted/bounding capabilities,
NoNewPrivs=1 and Seccomp=2. The fixture was removed. Reproduce with
`python3 tools/security/test-longhorn-prepull-guards.py`.

The manager's existing reviewed privileged requirement gains matching root,
escalation, capability and seccomp audit exceptions. These only approve the main
privileged container, exact image and existing declarations/guards. The prepull
sidecar must independently comply with all four policies. Until its guards are
deployed, the new workload exceptions cannot excuse the unguarded sidecar.
They report Skip, preserve the current expiry and leave Audit/Ignore unchanged.

This is a prepared GitOps change. Publishing rolls all three manager Pods, even
though only the sidecar context changes. Observe manager readiness, Longhorn
volume health and representative storage I/O after reconciliation. No live
workload, storage data or policy was patched during preparation. The root
filesystem remains at its current setting; this batch does not add a read-only
root. GPU, MetalLB and other infrastructure guards are unchanged.

Verification: 92 real native mutation/scope cases plus 16 idempotence checks
passed using Kyverno CLI 1.19.2. Repository tests passed: 291 run, 16 skipped.
Generated manifests, runtime-contract validation and whitespace checks passed.
Focused exception CEL validation passed all 194 expectations for current
contracts and guard regressions, including the new manager exceptions. The full
rendered CI suite remains the publication gate.

Live verification of the preceding batches completed during this turn: all 12
CSI controller root results are Skip; all 24 capability/seccomp results across the
12 approved privileged infrastructure Pods are Skip. All 118 live exception specs
matched pushed Git exactly. A 56-case test using the fetched live CSI exceptions
passed positive and changed-guard/identity cases. Current main CI remained running.


## Rendered admission/audit CI regression

Run 41826691990 tested the raw manager Helm manifest before its native prepull
mutation and incorrectly expected four guarded exceptions to match. The audit
harness now evaluates the real native policy with Kyverno 1.19.2 first, then audits
that admitted DaemonSet. It never substitutes the catalog snapshot or blindly
copies guards. An unmatched runtime contract remains raw and fails the audit.

`tools/longhorn/test-manager-admission-audit.py --rendered <render-directory>`
checks the actual chart through both stages: raw output reproduces the four Fail
results, admitted output yields all five Skip results, an unreviewed image remains
unmodified/failing, and adding SYS_ADMIN to the admitted helper still fails. Its
20 real CEL expectations run before the full audit suite in CI. The existing
native mutation scope/idempotence suite continues to validate the mutation itself.
No production policy or exception is relaxed for this test correction.
