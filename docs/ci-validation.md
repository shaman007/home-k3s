# Deployment validation

`Validate Kubernetes` runs policy tests, runtime-contract checks and generated
NetworkPolicy checks, then renders every Application in `argocd/` from the current
checkout. Helm uses the application's pinned chart, destination namespace,
release name, `$values` files, inline values and parameter overrides. Kustomize
sources are built with `kubectl kustomize`; directory sources honor include,
exclude and recurse settings. Unsupported source options fail explicitly.

The GitHub chart-download fallback accepts HTTPS origins and HTTPS redirects only.
Signed release-asset redirects remain supported, and the downloaded archive must
match the SHA-256 digest from the pinned chart index before Helm can use it.

`tools/ci/validation-config.yaml` pins the target Kubernetes version. Update it
and the workflow's kubectl version with cluster upgrades. The kubeconform archive
is checked against the reviewed release SHA-256 before extraction; update both
its version and checksum when upgrading it.

Runtime-contract validation rejects deprecated Service `externalIPs` and
`loadBalancerIP` fields. Use a NodePort endpoint or the load balancer provider's
address annotation. Ingress class tests reject the legacy class annotation.

All rendered manifests and tracked raw Kubernetes manifests are validated.
Talos machine configuration is excluded from Kubernetes manifest discovery. Kustomization
configuration is consumed by rendering, rather than passed to Kubernetes schema
validation. Built-in resources use strict kubeconform validation for the configured
Kubernetes version. Custom resources use schemas from the rendered controller
CRDs. CiliumNetworkPolicy's CRD is fetched from the Cilium application version
because Cilium installs its CRDs at runtime. Missing schemas fail validation.
CRD definitions receive explicit group/name, scope, version, storage-version and
OpenAPI schema-shape checks because kubeconform does not publish their schema.
OpenAPI nullable and int-or-string fields are translated to JSON Schema, and
Kubernetes Unicode regular-expression categories are supported, and
unknown properties are rejected except in maps or explicitly preserved fields.
Admission webhooks, CEL rules, cluster capabilities and runtime connectivity
still require deployment verification.

Local reproduction (Python with PyYAML, jsonschema and regex, Helm, kubectl, curl and
kubeconform required):

```sh
python -m unittest discover -s tests
python tools/ci/render_applications.py --output /tmp/home-k3s-rendered
python tools/ci/validate_rendered.py --rendered /tmp/home-k3s-rendered
```

Use an empty output directory. Rendered files can contain generated chart Secrets;
the directory is private and CI does not publish it as an artifact. Validation
errors show resource identities and failing constraint paths, not values. For
Helm diagnostics, reproduce the failing source locally and keep output private.
`--application NAME` supports isolated rendering; full validation requires the
complete application inventory.

Container memory budgets and the absence of CPU limits are checked after
rendering with `tools/ci/check_container_resources.py`. Namespace LimitRanges
are considered for admission defaults. See [container resource policy](container-resources.md)
for operator-generated pods, sizing evidence and rollout requirements.

## Kyverno CEL audit tests

The audit fixture generator still checks the complete rendered policy inventory
and the Audit/Ignore settings, normalizes the real Longhorn manager through its
native mutation, and creates all positive, negative and repaired-resource cases.
It partitions assertions by policy before running the pinned Kyverno 1.19.2 CLI.
Each policy is further split into balanced shards of at most 256 expectations.
The capabilities policy has four shards (238/238/238/237); the non-root policy
has three (238/238/237). Together with the three smaller policies, CI runs ten
independent shards. Round-robin assignment spreads separate Pod variants among
the shards. `--max-cases-per-shard N` changes the cap for local experiments.
Every exception referring to that policy remains loaded, including exceptions
for other workloads and namespaces. This preserves negative tests for exceptions
that accidentally match too broadly. Pod variants sharing an identity remain
in separate test folders.

Prepare and run the complete suite locally:

```sh
python tools/kyverno/test_audit_policies.py --rendered /tmp/home-k3s-rendered
```

To retain sanitized fixtures instead of immediately evaluating them:

```sh
python tools/kyverno/test_audit_policies.py --rendered /tmp/home-k3s-rendered \
  --output /tmp/home-k3s-audit-cases
kyverno test /tmp/home-k3s-audit-cases --fail-only --remove-color --require-tests
```

The output directory must not already exist. CI shares only these sanitized
fixtures with its policy matrix; full rendered applications stay private. The
matrix comes from generated `counts.json`, rather than a separately maintained
shard list. `fail-fast: false` lets every shard finish even if another fails.
The existing `validate-manifests` required check succeeds only after both the
input validations and all policy matrix jobs succeed. Superseded workflow runs
on the same branch or pull request are canceled.

`tools/kyverno/benchmark_audit_policies.py` compares two retained fixture trees.
Before timing anything it requires an exact multiset match of the complete input
resource, policy name and expected result for every assertion, plus identical
policy contents and applicable exception scope. It then runs the
same deterministic subset sequentially against both layouts, retaining each
layout's policies and exception scope. Use `--sample-every 1` for a full-suite
comparison; sampling is only a local benchmark option and is never used in CI.

```sh
python tools/kyverno/benchmark_audit_policies.py \
  --baseline /tmp/legacy-audit-cases --optimized /tmp/home-k3s-audit-cases \
  --output /tmp/audit-comparison --sample-every 20
```

The new benchmark output directory contains sanitized sampled fixtures, CLI logs
and `report.json` with assertion counts, a full-coverage fingerprint, elapsed
times and exit statuses. Both variants use the same `GOMAXPROCS` budget (default
2). Legacy fixtures must be retained from the original generator before changing
layouts; they must use the same rendered application inputs. Do not compare
fixtures from different checkouts or renderings.

### Benchmark, 2026-11-10

The legacy generator at `c9c195d94469cb7931a200d9fa6ff711d4114fcb` and the new
generator consumed the same freshly rendered 93 applications. All **2,223**
explicit expectations had identical resource content and expected outcomes;
all five policies and their complete applicable exception lists also matched.
The full-coverage fingerprint was
`c7e87ffab6e23840466434e1003673009a8fc50b6a743dba09d457319521a3e4`.

A deterministic sample of **112** expectations (`--sample-every 20`) ran
sequentially using the checksum-verified Kyverno 1.19.2 release CLI and
`GOMAXPROCS=2` for both layouts on the same 24-logical-CPU workstation. Both
sample runs shared the machine with the same two exhaustive validation shards:

| Layout | CLI time | Result |
| --- | ---: | --- |
| Legacy, all policies for each resource | 211.89 s | Passed |
| Policy-grouped fixtures, sequential | 64.70 s | Passed |

This is **3.27× faster** for the sampled evaluation alone, before CI matrix
parallelism. It is a sample comparison, not a measured full-suite speedup on
GitHub-hosted runners. An exploratory exhaustive legacy local run was stopped;
its incomplete timing is excluded. The previous successful GitHub run's audit
suite took 67m 1s ([run 42708482854](https://github.com/shaman007/home-k3s/actions/runs/42708482854)).

The exhaustive optimized run passed **all 2,223 expectations** in five concurrent
local shards (`GOMAXPROCS=2` per shard), with **686.83 s / 11m 27s** wall time:

| Policy | Expectations | CLI time |
| --- | ---: | ---: |
| disallow-privilege-escalation | 186 | 43.88 s |
| disallow-privileged-containers | 170 | 38.89 s |
| require-drop-all-capabilities | 951 | 686.83 s |
| require-run-as-nonroot | 713 | 464.75 s |
| restrict-seccomp-strict | 203 | 45.94 s |

These shard timings exclude rendering/preparation and runner/artifact setup.
The sampled comparison ran alongside the two larger shards. All remaining
Longhorn manager, recurring-job, component, and infrastructure guard CLI suites,
generated-file checks and runtime contracts passed. Repository unit tests passed
(369 run, 21 skipped); `actionlint` and composite installer shell syntax passed.
A deliberately incorrect expectation and an empty fixture directory both caused
the real CLI to fail. The modified GitHub workflow has not yet been executed.

### Follow-up: bounded capabilities and non-root shards

The default 256-expectation cap produces four capabilities shards and three
non-root shards, plus the three smaller policies: ten jobs in total. The same
93 rendered applications were reused. Comparing against both the five-shard
fixtures and the original legacy fixtures confirmed the exact same **2,223**
resource/policy/expected-result assertions and unchanged policies and complete
applicable exception lists. The coverage fingerprint remains unchanged.

The complete ten-shard run used Kyverno 1.19.2, `GOMAXPROCS=2` per shard and ten
concurrent local workers on the same workstation:

| Layout | Full-suite wall time | Result |
| --- | ---: | --- |
| Previous five concurrent policy groups | 686.83 s / 11m 27s | Passed |
| Ten balanced shards | 234.70 s / 3m 55s | All ten CLI commands passed |

This is **2.93× faster wall time** than the recorded five-shard run. The slowest
capabilities shard took 234.70 s (previous single group: 686.83 s); the slowest
non-root shard took 213.26 s (previous single group: 464.75 s). The comparison
measures increased parallelism, not reduced total CPU cost. It excludes fixture
preparation and GitHub runner/artifact setup; GitHub-hosted timing is unverified.

All ten CLI processes exited successfully with zero failed results. Kyverno
reported **2,224 summary rows for 2,223 explicit expectations**, including 239
rows for the 238 expectations in non-root shard 1. The benchmark wrapper's final
exact-row-count assertion therefore failed; this did not come from a failing CEL
case. Coverage is verified by the exact fixture multiset and policy/exception
scope comparison, independently of the CLI's row count. The retained benchmark
report records both counts. Regression tests also verify the shard cap,
balancing, complete exception lists and separate duplicate Pod identities.
Repository tests passed (370 run, 21 skipped), along with workflow linting.
