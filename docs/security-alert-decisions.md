# Security alert decisions

This ledger distinguishes source fixes, reviewed exceptions and findings that
still need investigation. A local fix is not evidence that GitHub has closed an
alert. Do not dismiss an entire scanner's results as false positives.

## Inventory observed on 2026-11-11

GitHub's main-branch code-scanning UI reported 3,850 open alerts after the TLS
and workflow-action pinning changes. The authenticated CLI could not read the
alert API (HTTP 403), so this is a UI inventory, not an exhaustive API export.

After the user updated the CLI token, the complete API inventory confirmed that
baseline. A later API refresh reported **3,635 open alerts**. Reviewed dispositions
were recorded on 84 specific false positives: CodeQL 2 and 3, 80 obsolete-Python
analyzer reports, Bandit 1395 and Opengrep 3402. The rest of the reduction is from
scanner updates, including the earlier operational-assertion fixes.

The user explicitly chose to keep and fix the 2,319 legacy Pylint convention and
refactoring findings. No bulk style dismissal was applied. Their rule inventory
is in [security-legacy-lint-review.md](security-legacy-lint-review.md).

| Scanner | Open findings | Decision/status |
| --- | ---: | --- |
| CodeQL | 2 | Review the reported source-to-sink paths individually. |
| Bandit | 572 | Fix removable operational safety checks first; review remaining rules by use site. |
| Opengrep | 60 | Review subprocess argument provenance, TLS exceptions and Kubernetes contexts individually. |
| Shellcheck | 12 | Fix shell defects or document precise source/quoting exceptions. |
| Pylint | 1,433 | Legacy configuration; last scan shown as October 29. Separate style findings from correctness findings before disposition. |
| Pylintpython3 | 1,066 | Legacy configuration; overlaps Pylint. Do not count duplicate reports as separate defects. |
| Prospector | 176 | Legacy configuration; overlaps Python linters. Needs rule-level disposition. |
| Remark-lint | 488 | Legacy Markdown lint results; needs rule-level disposition. |
| Rubocop | 31 | Legacy Ruby lint results; needs rule-level disposition. |
| Tsqllint | 6 | Legacy SQL lint results; needs rule-level disposition. |
| Psscriptanalyzer | 4 | Legacy PowerShell lint results; needs rule-level disposition. |

The current Codacy workflow runs Bandit, Opengrep and Shellcheck. Stopping a
scanner does not establish that its previous alerts were fixed. Preserve their
history; do not delete old analyses simply to reduce the displayed count.

## Operational assertions: fix

Bandit B101 is actionable when `assert` controls a security generator, admission
preflight, workload identity check, storage-health gate or deployment review.
Python optimization removes those checks and can allow a tool to proceed with
unreviewed inputs or without verifying admission/read-back results.

Replaced 133 assertions with explicit conditional `AssertionError` failures in:

- `tools/kyverno/generate-exceptions.py`
- `tools/kyverno/benchmark-audit-policies.py`
- `tools/longhorn/backfill-component-security.py`
- `tools/longhorn/backfill-recurring-security.py`
- `tools/longhorn/generate-component-security.py`
- `tools/security/infra_guard_backfill.py`
- `tools/security/generate-infra-guards.py`
- `tools/security/review-metallb-l2.py`

The exception type is retained because backfill clients retry `AssertionError`
during admission-cache convergence. Predicates, messages, evaluation order and
surrounding statements are preserved. Updated the embedded programs in
`infra-guards/resources.yaml`, `longhorn/component-security-backfill.yaml` and
`longhorn/recurring-job-security-backfill.yaml` as well.

`tests/test_security_optimized_guards.py` runs the existing malformed-catalog,
changed-workload, unhealthy-storage and missing-admission-mutation regression
suites with optimization enabled. The generated-file checks must also pass.

Status: recorded in commit `601c8982`; deployment remains unverified. Assertions
in other scripts and tests still require review; this decision does not blanket
suppress B101.

## CodeQL alert 2: reviewed false positive

Rule: `py/clear-text-logging-sensitive-data` in
`tools/ci/validate-runtime-contracts.py`. The UI's displayed source path starts at
the call to `check_external_secret_targets()`, continues through its returned
diagnostic list and ends at the diagnostic print loop. That function returns
fixed messages with a repository path and document index; it does not return
Secret data, target names, tokens or credentials.

Decision: retain useful validation diagnostics; this specific data-flow report
is a false positive. `tests/test_runtime_contract_diagnostics.py` verifies that
credential-like values in ExternalSecret, SecretStore, ClusterSecretStore and
Secret documents are not included in the relevant diagnostics. GitHub now records
the false-positive dismissal with an explanatory comment.

The separate YAML parse-error path had a real disclosure risk: parser exceptions
can quote source snippets. It now reports only path, line and column and suppresses
the original exception chain. A regression checks the complete formatted traceback
for a malformed synthetic Secret, including the absence of its credential value.

## Further verified false positives

- CodeQL 3 checks exact membership in a ClusterRole `apiGroups` list. There is no
  URL or hostname sanitization in that unit test. Retain the RBAC regression.
- All 74 legacy Pylint E1136 locations were checked in their original reported
  commits: each is a built-in generic type annotation supported by Python 3.9+.
  Three E0611 reports concern postponed annotations, one E1123 concerns the
  supported subprocess `text=` keyword, one E0001 concerns valid modern function
  annotations, and one E1101 concerns `str.removeprefix`. Current Pylint 4.1.3 on
  Python 3.15 reproduces none of these 80 errors. Each alert has a specific comment;
  valid modern Python code is retained instead of rewritten for an obsolete engine.
- Bandit 1395 uses a custom subclass of `yaml.SafeLoader`, not an unsafe loader.
  Regression tests verify both parser entry points reject Python-object
  constructors and retain duplicate-key detection.
- Opengrep 3402 calls `chmod(0o700)` on the private render directory. That grants
  access only to its owner. A regression verifies a pre-existing 0755 directory is
  restricted to 0700 and rendered Secret files are 0600.

## Removed unused tooling

The user authorized removal of unused `.specify` scaffolding and `synapse/tools`.
No CI, runtime or application references use these trees. The ten repository-local
Spec Kit skills were removed with their `.specify` dependency. The substantive
hardening specification and checklist under `specs/` are preserved because
`docs/non-root-audit.md` links to the specification.

The removed trees account for 514 open findings in the later API snapshot.
Removal is a source change, not a claim that a retired scanner has closed those
alerts. No database, homeserver, cluster resource or persistent data was removed.

## Current source fixes and validation

- Five CI modules were reformatted at a 100-character line length. Formatting
  was verified to preserve their AST; long diagnostic strings were then wrapped
  without changing their text. Style findings remain remediation work, not
  accepted debt.
- The remaining reviewed shell scripts use ASCII quoting in the retired PKI
  entry point and document the intentionally remote variable expansion in the
  snapshot rehearsal. Both pass ShellCheck.
- The disposable mail TLS fixture now trusts its own temporary certificate and
  verifies the loopback IP against a certificate SAN instead of disabling TLS
  verification. Certificate trust/hostname configuration was checked locally;
  the full container smoke test has not been rerun.
- After unused-tool removal, the full local suite passed: 384 tests, 21 skips.
  No changes in this batch were committed or pushed by the agent.

## Further source remediation

- Documented 28 public CI functions with their actual contracts, removed an unused
  import and moved JSON imports to module scope. The five selected CI modules pass
  current Pylint checks for missing module/class/function documentation, line
  length, statement layout, import placement and unused imports/locals. Other
  rule families, including filename conventions and complexity, remain work.
- Removed `specs/001-cluster-hardening-backlog/plan.md`: it was an unfilled
  `[FEATURE]` template with placeholder architecture choices, not an implementation
  plan. The substantive specification and checklist remain; no repository document
  links to the removed placeholder.
- Converted 12 plain documentation URLs to explicit Markdown autolinks without
  changing their destinations, including historical archive documentation.
- Prepared explicit snapshot-controller hardening for Opengrep alert 3434:
  no privilege escalation, read-only root filesystem, drop ALL capabilities and
  RuntimeDefault seccomp. Read-only inspection found three ready replicas with no
  restarts, only projected service-account mounts and an upstream image declaring
  UID 0. The patch preserves that identity rather than inventing an untested UID.
  All eight built-in application resources pass kubeconform; all three CRDs pass
  the repository's separate CRD checks. Live rollout is not yet verified.

The standalone `mastodon/tools/list_bookmarked_media_s3.rb` was an unused older
copy exporting a plain URL list. Removed it rather than maintain a second version.
The active CronJob mounts `bookmarked-media-sync-scripts` and uses the Ruby script
embedded in that ConfigMap, which exports JSONL with descriptions and S3 existence
checks. That canonical workflow is retained. The obsolete file accounts for all
31 historical RuboCop alerts; their scanner closure remains to be verified.

The next formatting pass covers all 28 retained test files associated with 312
historical line-length, spacing, indentation and multiple-statement reports.
Ruff formatting plus explicit literal wrapping preserves every executable AST,
including the exact fixture strings. All 28 now pass current Pylint C0301/C0321
checks. The full suite passed with 384 tests and 21 skips. These are source fixes;
the legacy alert configurations still require matching rescans before closure can
be claimed. No style alerts were dismissed.

The retained-tool formatting pass covers 13 files associated with 845 historical
formatting reports, including the previously formatted CI files. Eight additional
tools were reformatted. Literal wrapping was checked to preserve executable ASTs
and exact emitted strings; the network-report imports were then split and a module
description added. All 13 pass current Pylint C0301/C0321/C0410 checks. The full
suite passed with 384 tests and 21 skips after these source changes.

## CodeQL language configuration after Ruby removal

Removing the final standalone `.rb` file exposed a stale Ruby entry in GitHub's
default CodeQL setup: the Ruby job failed with `No Ruby code found`. Updated the
saved default setup through GitHub's interface to select GitHub Actions, Go and
Python only; verified the persisted configuration lists those three languages.
The query suite, runner, threat model and triggers are unchanged. This is a live
GitHub settings change, not a repository commit. The historical failed run remains
in Actions history. The next analysis,
[run 43001909513](https://github.com/shaman007/home-k3s/actions/runs/43001909513),
completed successfully with Actions, Go and Python jobs and no Ruby job.

## Standalone smoke-test checks

Converted the remaining 189 `assert` statements in 23 standalone smoke-test tools
to unconditional conditional failures. Original predicates, error messages and
surrounding executable ASTs were compared against the mechanical expansion; all
compile in optimized mode. Bandit B101 now reports no issues anywhere under
`tools/`. This fixes the checks instead of suppressing test findings.

An additional regression compiles the actual mail smoke-test helper normally and
with optimization, verifies its valid read-only command arguments, and checks that
privilege escalation, a writable root filesystem and excess capabilities are each
rejected before a subprocess can execute. The full suite passed: 386 tests, 21 skips.
The full container smoke probes were not run as part of this source-only change.

Six subprocess calls now explicitly set `check=False` where callers inspect return
codes themselves or intentionally test failure paths. This preserves their previous
default behavior and resolves current Pylint W1510 diagnostics in those files.

CodeQL recreated the previously reviewed RBAC false positive as alert 4019 after
source reformatting changed its fingerprint. The regression now validates that
RBAC fields are lists and checks a set of `(API group, resource, verb)` tuples.
This also rejects malformed string fields that substring membership could accept;
matching rescan verification is pending rather than another repeated dismissal.

## Legacy rescan requirement

The legacy Pylint analysis category is
`.github/workflows/codacy.yml:codacy-security-scan`, with an empty matrix environment.
It still reports historical results because the current workflow selects only
Bandit, Opengrep and Shellcheck. Matching genuine legacy analyses must be refreshed
before claiming closure of their source fixes. No empty substitute reports or bulk
dismissals have been used to manufacture a reduction.

## Remaining dispositions

Router TLS verification, subprocess audit findings and remaining lint/correctness
findings still need source-level review and fixes.
An unverified TLS exception is an accepted risk, not a false positive. A
subprocess call using `shell=False` is not automatically safe: validate the
executable and whether untrusted values can become command options or executable
code. Each retained exception must identify its scope, evidence, rationale and
condition for revisiting it.

## NetworkPolicy tool documentation

Added descriptive docstrings to 43 functions, one class, and the renderer module in
`tools/networkpolicy/`. These address the missing-documentation lint rules without
suppression. Removing docstrings from the before/after ASTs gives identical
executable trees. Both modules pass current Pylint's module/class/function
documentation checks; the common-policy catalog passes its generated-output check.
Empty and multi-namespace SVG fixtures are byte-identical before and after the
change with a fixed timestamp, and both parse as XML. Historical alert closure is
still pending matching genuine lint rescans.

## Genuine historical Markdown rescan

[Remark run 43006242302](https://github.com/shaman007/home-k3s/actions/runs/43006242302)
on commit `6b30e257` completed successfully and uploaded 16 findings in the original
category. The open-alert API then showed 16 Remark findings, down from 488 before
the rescan. This confirms that genuine matching rescans reconcile the historical
category despite the new matrix environment.

All remaining findings identify `[x]` task markers in the dated specification
quality checklist as undefined reference links. Converted the completed review to
ordinary bullets and explicitly retained its historical completion status and
current-state revalidation caveat. No checklist content or acceptance criterion
was removed. Closure of those final 16 findings requires a rescan of this edit.

## Refreshed Python lint and remaining formatting

[Python 3 lint run 43006628295](https://github.com/shaman007/home-k3s/actions/runs/43006628295)
on `6b30e257` completed successfully, including the parser safeguard and upload.
The genuine rescan found 2,357 current open findings versus the stale inventory's
1,023; the broader current coverage is retained rather than dismissed. Thirteen
E5110 findings say Django was not configured for the analyzer's Django plugin;
these require a tool-configuration decision, not application Django changes.

Formatted 13 files carrying 232 current multiple-statement findings. Before/after
ASTs, including literal values, are identical; current Pylint reports no remaining
multiple statements in those files. Refreshed embedded copies in infrastructure
and Longhorn backfill ConfigMaps. Parsed manifest fields and embedded executable
ASTs remain identical, and both available generators pass their consistency checks.

Documented the Argo CD project-boundary and Traefik plugin test modules, their two
classes, and 20 functions without changing executable ASTs. Removed an unused
network-report import/local value and named an unused retry counter `_`.
The removed `summarize()` local port set had no readers; expected-port membership
checks remain in preclassification and verdict handling. New regressions verify
that unlisted ports remain actionable and configured nondefault ports receive the
expected-service exception. Full suite: 392 tests passed, 21 skipped. Container
smoke probes and live cluster changes were not performed.

## Explicit subprocess status and analyzer-visible interfaces

Made `check=False` explicit in 38 subprocess calls across 26 test/benchmark files.
These calls retain their existing manual status handling, including intentional
failure probes. Before/after executable ASTs differ only by that explicit default;
current Pylint's subprocess-status check passes for the complete file set.

The component backfill now collects Longhorn responses by resource name and calls
`storage_healthy(volumes, nodes)` explicitly. This preserves request order and
health checks while removing two spurious missing-argument diagnostics caused by
unpacking an incrementally built list. Regenerated both embedded copies. The
optimized mail helper test now accesses dynamically compiled symbols through its
execution namespace, resolving five no-member findings without weakening its
normal/optimized rejection cases. Removed seven further unreferenced imports.

Full suite passed: 392 tests, 21 skips. Longhorn preflight still rejects unhealthy
storage before any PATCH; optimized checks still reject unsafe contexts. Container
smoke probes and live deployment were not performed. GitHub reconciliation of this
batch remains pending a matching rescan after publication.

## Guard parentheses, loop bindings, and migration diagnostics

Simplified negated guard syntax across 31 files carrying 230 current superfluous-
parenthesis findings. Exact executable ASTs and literal values were compared before
and after editing/formatting; all match. Current Pylint reports no remaining
superfluous parentheses in that complete file set. Embedded infrastructure and
Longhorn copies are synchronized; parsed manifest fields and embedded executable
ASTs remain unchanged, and generator consistency checks pass.

Bound loop callback values explicitly in the NetworkPolicy graph ordering,
Restricted-context diagnostics, and Kyverno fixture generation. Current Pylint's
loop-capture and mutable-default checks pass. Graph ordering matches HEAD across
100 deterministic fixtures; diagnostics retain each container's own name. Existing
Kyverno sharding and exception-scope tests remain in the full suite.

Three flagged reads now declare UTF-8 explicitly. Four migration CLI exception
translations explicitly suppress their underlying exception chains. Regression
tests compile the actual entry-point handlers with a failing main substitute,
perform no migration/API operations, and verify that generic formatted diagnostics
exclude sensitive command/response sentinels while retaining operational guidance.
The targeted encoding and exception-chaining lint checks pass.

Full suite: 394 tests passed, 21 skipped. No live workload or database changes and
no container smoke probes were performed. Alert closure awaits a matching rescan
of the published source changes.
