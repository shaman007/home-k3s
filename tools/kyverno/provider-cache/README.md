# Kyverno reports-controller provider cache

Temporary downstream fix based on upstream Kyverno v1.19.2. Only the reports
controller binary changes; admission controllers, policies, exception objects,
background interval (1h), workers (2), and report coverage stay unchanged.

The background scanner previously built a CEL ValidatingPolicy provider for every
resource/policy pair. The patch reuses compiled providers in a process-local LRU
cache (eight entries, five-minute lifetime). It never caches resource decisions or
namespace/request state. Full policy and applicable exception objects form a
SHA-256 key, including identity, version, spec, and exception expiry state.
Compilation owns deep copies, coalesces concurrent misses, and never caches errors
or falls back to a stale revision after compilation failure. Existing exception
selection is preserved; exceptions are ordered by namespace/name/UID because informer
list ordering is unspecified. This prevents cache churn for identical sets. Other policy types use upstream behavior.

## Reproduce

Use Go 1.26.9+ and the tools documented in `build.sh`:

```sh
BUILD_DIR=/tmp/kyverno-provider-cache-build ./tools/kyverno/provider-cache/build.sh
python3 tools/kyverno/provider-cache/fixtures.py /tmp/kyverno-cache-fixtures
cd /tmp/kyverno-provider-cache-build/kyverno-1.19.2
KYVERNO_CACHE_FIXTURES=/tmp/kyverno-cache-fixtures go test ./pkg/controllers/report/utils \
  -run TestVpolProviderCacheEquivalence -v -count=1 -timeout=30m
```

The equivalence test runs the actual background scanner with cache disabled and
enabled against live policy/exception snapshots and reviewed catalog resources,
including derived Pods and deliberately introduced privileged containers. It
compares complete report results except timestamps. It does not create workloads.

The Containerfile pins the official amd64 v1.19.2 base image by digest and replaces
only `/ko-app/reports-controller`. The controller retains upstream user 65532 and
entrypoint. Publication is separate; do not put registry credentials in files.
The Argo CD image reference is pinned to the resulting custom image digest.

## Limitations and rollback

This patch deliberately preserves upstream exception semantics. In v1.19.2 the
background scanner passes expired CEL exceptions to the provider without filtering
them. Expiry changes invalidate our cache, but this does not repair upstream expiry
handling. Do not claim automatic exception expiration from cache tests.

Remove `reportsController.image` from `argocd/application-kyverno.yaml` to return to
the chart's official image. No report CRD or data migration is needed. Validate
complete scan coverage, report outcomes and CPU/allocation rates after any change.

Check upstream before future upgrades. Related CLI fix #18048 is not a reports
controller fix; image-verification-cache PR #18432 does not fix ValidatingPolicy
compilation. A weekly Codex reminder was created for Mondays at 10:00 Europe/Prague.

## Verification on 2026-11-08

- Cache unit tests and scanner/ValidatingPolicy compiler/engine suites passed
  with the Go race detector.
- The actual background scanner evaluated 212 resource cases against the five
  live policies and reviewed exceptions: 1,060 identical results (410 pass,
  162 fail, 488 skip), including deliberate violations.
- Exact-upstream evaluation: 338.839 seconds; cached: 2.179 seconds (155.47x faster).
- Additional warm-cache tests verified scoped exception matching, exception
  changes/removal, policy updates, and rejection of invalid new policy revisions.
- Published image digest:
  `sha256:0a44d24fc8aa065860c09da35f5c3c228f94628088e73e5755d9bfe8d0475b48`.

Live validation of final image `.3`:

- Completed full background scans; all 1,219 then-current production reports
  refreshed. All 1,209 reports still present from the original 1,217-report
  snapshot retained identical semantic results; differences in identity/count
  reflect controller rollout Pods/ReplicaSets and normal workload turnover.
- Live scheduling-gated Pods verified five Pass and five Fail results. A narrow
  exception changed only the intended result to Skip. Editing it to stop matching
  and deleting it both restored Fail without restarting the controller.
- At 19,735 background policy evaluations, total process CPU was 52.91 seconds;
  a 48-second interval processing exception-triggered full scans averaged 0.367 CPU
  cores and 70.7 MB/s allocated, versus the previously measured 2.856 cores and
  913.6 MB/s. This is short-run validation, not a day-long average.
- Final replica restart counts remained zero during validation; RSS was about
  420 MiB with the original 512 MiB container limit. After completing the scans,
  `kubectl top` showed 2m CPU and 337 MiB working memory on the active replica
  (the standby used 1m CPU and 39 MiB).
- Temporary fixture exception and namespace were removed after testing.


The first live validation exposed informer-order cache churn and OOM at 512 MiB.
That candidate was rolled back. The corrected candidate canonicalizes exception
ordering, caps the cache at eight entries, and adds a shuffled-order regression.
Do not deploy candidate `.1`.

Final revision `.3` also immediately drops superseded providers for the same policy
identity before compiling a replacement. Helm sets reports-controller's
`autoMemLimitRatio=0.7` to reserve more non-heap/transient headroom within the
unchanged 512 MiB container limit. Admission controllers are unaffected.

## GitOps deployment

`argocd/application-kyverno.yaml` selects the published `.3` image by immutable
digest. Argo CD's normal parent/child reconciliation deploys this selection after
publication to Git. No temporary Helm parameter overrides or parent
`skip-reconcile` pause are needed. Verify the live image digest, two ready replicas,
restart counts and a completed background scan after synchronization.
No PVC or application data migration is required.
