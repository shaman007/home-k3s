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

## Monitoring tool formatting and log-test documentation

Formatted the dashboard generator, UniFi BGP exporter, and log-analysis regression
suite, including splitting long string literals while preserving their values.
These files carried 151 long-line findings in the refreshed Python inventory.
Current Pylint reports no long-line or multiple-statement findings in the three
files with a 100-column limit. Executable ASTs and literal values were compared
before and after formatting and match exactly.

Executed both dashboard-generator versions in separate temporary output trees:
all 14 emitted dashboard ConfigMaps are byte-identical, including PromQL queries.
Regenerated the UniFi exporter ConfigMap; parsed manifest fields and the embedded
executable AST match the previous version. No dashboard or cluster was deployed.

Added descriptive documentation to the log-analysis test module, class and 38
methods while preserving the executable AST. Missing-docstring checks pass.
The 34 log-analysis tests and 13 UniFi exporter tests pass. Full-suite verification
is recorded below; matching GitHub lint reconciliation remains pending publication
and rescan.
Full suite passed: 394 tests, 21 skipped. The full container smoke probes were not run.

## Repository-wide Python formatting completion

A fresh current-Pylint scan of all 127 repository Python files found 183 remaining
long-line/multiple-statement findings across 45 files. Formatted those files and
split long text/byte literals at source level without changing their values.
The final full-repository scan reports zero findings for both rules at 100 columns.

Compared each changed file's executable AST and non-docstring literal values with
starting revision `ee0e7055`; all match. The sole docstring wording adjustment
wraps the Sync storage probe's CLI description. Infrastructure, component-security,
UniFi exporter and Kyverno exception generator consistency checks pass; their
committed outputs require no changes. Full suite passed: 394 tests, 21 skips.
No live deployment, migration, container smoke probe, or alert dismissal occurred.
Matching GitHub lint reconciliation remains pending a published rescan.

## Non-Django plugin configuration disposition and recurring Python lint

Individually verified and dismissed exactly 13 `PyLintPython3_E5110` findings as
false positives: 6749, 6730, 6626, 6575, 6518, 6413, 6224, 5863, 5153, 5017,
4813, 4750 and 4655. Every finding had the exact Django-not-configured message,
and an AST audit of all 127 Python files found no Django imports; a repository
Python-source text search also found no Django references.

The [upstream wrapper](https://github.com/codacy/codacy-pylint-python3/blob/master/src/codacy_pylint.py)
forces `pylint_django` in `runPylintWith` and divides files into groups of ten in
`runTool`, explaining the repeated framework-configuration diagnostic. Inventing
Django application settings would not repair these utility/test scripts. Each
GitHub dismissal records that evidence and says to reopen if Django application
code is added. No style/correctness rules were disabled and no other alerts were
dismissed in this batch.

Added Python 3 Pylint to normal Codacy workflow dispatch defaults, pushes, pull
requests and scheduled scans. Its existing successful genuine manual analysis
validated tool availability and upload. The job keeps the historical category,
all default lint rules, failure-on-incomplete behavior and parser-error safeguard,
so source fixes can reconcile automatically after publication. Legacy Pylint,
Prospector, Remark and PowerShell remain available as targeted manual rescans.

Actionlint/ShellCheck workflow validation and all 14 SARIF adapter tests pass.
The new automatic matrix configuration still needs a published Actions run;
this source change does not establish that GitHub has rescanned current fixes.

## Missing Python module documentation completion

A current-Pylint inventory found 44 modules without module docstrings. Added a
specific purpose statement to each, including the retained archived Hypermind
regression module. Removed only the newly inserted module-docstring node from
each after-edit AST and compared it with the original tree: executable ASTs and
all pre-existing literal values match exactly.

A full scan of all 127 repository Python files now reports zero missing-module-
docstring, long-line or multiple-statement findings at the 100-column limit.
Full regression suite passed: 394 tests, 21 skipped. The archived regression suite
was not executed; its executable AST is unchanged. No live cluster/API operations
or generated manifest changes were performed. Matching GitHub reconciliation still
requires publication and the normal Python lint rescan.

## Missing class documentation completion and remote progress

A fresh inventory found 95 missing class docstrings across 64 Python files.
Added specific descriptions for test suites, synthetic API fixtures, response
handlers, YAML loaders/dumpers, and runtime helpers. After removing class-docstring
nodes, before/after ASTs and pre-existing literal values match exactly.
Synchronized the embedded UniFi exporter; its executable AST and other manifest
fields remain unchanged. All 127 Python files now pass missing-module-docstring,
missing-class-docstring, long-line and multiple-statement checks. Full suite passed:
394 tests, 21 skips. Archived tests were not executed; their executable ASTs match.

[Automatic run 43010251271](https://github.com/shaman007/home-k3s/actions/runs/43010251271)
on `4692b6b6` passed all four jobs, including Python 3 Pylint. This verifies the
normal automatic lint matrix introduced in `6fd86d5e`. A subsequent open-alert API
count showed 2,955 total open findings and 1,020 Python 3 Pylint findings, compared
with 2,357 in the first genuine refreshed Python 3 analysis. Those remote counts
precede this class-documentation batch; its alert closure awaits publication and
rescan. Legacy Pylint and other remaining findings still require further work.

## Legacy parser diagnosis and operational function contracts

The genuine manual legacy Pylint run
[43011027851](https://github.com/shaman007/home-k3s/actions/runs/43011027851)
on `f381f0a3` completed analysis but failed the parser safeguard before upload.
The exact preparation error says the linter could not parse source files and
refuses to replace historical results with an incomplete scan. All 127 current
Python sources compile under the current interpreter. The normal Python 3 lint
[run 43010923234](https://github.com/shaman007/home-k3s/actions/runs/43010923234)
passed on the same revision, along with the other three scanners.

Removed the incompatible `pylint` manual-dispatch choice and kept `pylintpython3`
and the parser safeguard. Existing legacy findings remain open; this decision
neither dismisses them nor substitutes an empty analysis. Their remaining source
issues and overlap with modern findings still need review. Expected preparation
ValueErrors now become concise CLI errors rather than tracebacks. The parser-error
CLI regression verifies nonzero failure, no output report, no source sentinel and
no traceback. Actionlint/ShellCheck and all 14 adapter tests pass.

Documented 24 functions in the UniFi BGP exporter, synthetic FRR API and guarded
Firefox Sync migration helper. After removing function-docstring nodes, executable
ASTs and prior literal values match. Regenerated the embedded UniFi source.
Targeted function documentation checks pass; full suite passed with 394 tests and
21 skips. No live router, database or cluster changes were made.

## SQL fingerprint boundary and escaping-only XML import

A fresh Bandit 1.9.4 scan of `tools/` and `tests/` reported 245 findings. Strengthened
`fingerprint()` in the Firefox Sync migration helper so direct callers, as well
as `verify()`, must use an allowlisted application schema and a nonempty ASCII
alphanumeric/underscore table identifier before any SQL metadata lookup or process.
This closes the gap between the existing caller guard and the SQL-building boundary.

New regressions reject foreign schemas, injected names, empty names, non-ASCII
homoglyphs and nonstring table names before any database call. Positive cases keep
both reviewed schemas and existing table naming conventions supported. A mocked
successful fingerprint also verifies metadata scoping and backtick escaping for
column identifiers. No live database or cluster commands were executed.

The two B608 interpolation reports are now explicitly annotated at their exact
source sites: metadata literals are constrained by `validate_table`, and row-hash
expressions contain fixed SQL plus `quote()`-escaped identifiers. No global Bandit
rule was disabled. These scoped exceptions rely on the executable boundary guards
and regression tests; they must be revisited if query construction changes.

Replaced SAX text escaping in the NetworkPolicy SVG renderer with `html.escape`
using matching quote behavior. The module never parsed XML. Output matches the
previous implementation for special characters, a range of Unicode characters,
pre-escaped text and nonstring values, removing B406 without changing SVG output.

The full Bandit scan now reports 242 findings, zero B608/B406 findings and no
analysis errors. Other subprocess and security audit findings remain open for
individual review. Full suite passed: 397 tests, 21 skips. Targeted lint checks
pass; documented the remaining 12 migration test methods without executable changes.
Matching GitHub closure remains pending publication and the normal scan.

## Approved completed-migration tooling cleanup

The user approved removing the five identified groups rather than continuing to
maintain their one-off code. Removed these ten files:

- `tools/certificates/inventory-sso.py` and `migrate-sso.py`: completed domain/SSO migration.
- `tools/firefox-sync/migrate-mariadb.py`: completed transfer; the old MySQL source is retired.
- Five YAML files in `tools/nextcloud/`: old PVC-copy jobs and migration-only suspend/resume patches.
- `tools/longhorn/generate-recurring-job-proposal.py`: initial proposal scaffolding.
- `tools/security/review-metallb-l2.py`: chart-0.16.1 L2 retirement audit, superseded by BGP/FRR.

Also removed `tests/test_firefox_sync_mariadb.py` and
`tests/test_migration_cli_errors.py`, which exclusively exercised the removed
helpers. Historical migration and MetalLB records remain, with links to the last
retained source revision `254e90b51bc7dd86345987619bc91358d1f0d97c` instead of
commands targeting nonexistent local scripts. Historical inventory snapshots and
the MetalLB retirement inventory remain as records, not current desired state.

Active Longhorn recurring jobs and generated policies, reusable Firefox bootstrap
and storage verification, active CI/generators, security probes and runtime
backfill hooks are unchanged. No live cluster objects, PVCs, databases or data
were changed. No alert was dismissed to implement this cleanup.

Validation: no references to the removed paths remain in CI, Argo applications,
tools or surviving tests; active application manifests/workflows/generated
configuration have no diff. Runtime-contract validation and component-security,
infrastructure-guard, UniFi exporter and Kyverno exception generator checks pass.
The remaining 380 tests pass, with 21 skips; the test count fell by the 17 tests
specific to removed one-off helpers. Local Bandit findings decreased from 242 to
225 with no analysis errors. Remote reconciliation awaits publication and rescan;
the incompatible legacy Pylint analysis is still retained for separate review.

## Retained administrative HTTP client boundary

Reviewed the retained Traefik prerequisite provisioner after removing the one-off
SSO migration tools. The local standard urllib redirect implementation preserves
headers other than content headers when constructing a redirected request. The
provisioner's Bearer/Vault-token reads therefore needed an explicit redirect
policy rather than generic `urlopen` behavior.

Both administrative JSON requests and the Keycloak password grant now use one
reviewed transport. It accepts only the configured Keycloak/OpenBao HTTPS hosts
on the default port, rejects URL credentials/fragments and malformed ports, and
requires Authorization/Vault-token headers to match their respective service.
All redirects fail before a follow-up request. HTTP error responses are closed;
existing optional-404 behavior and sanitized path/status diagnostics are retained.
No secret values or query values are included in those diagnostics.

Six focused tests cover invalid origins before transport, crossed credential
headers, normal JSON/method/header/timeout behavior, optional missing/error
responses, and password-grant use of the guarded transport. Twenty redirect
scenarios exercise real urllib redirect processing with an in-memory HTTPS
handler and no sockets. A negative control replacing the guard with the standard
redirect handler is detected in 16 scenarios. No real credentials, services or
cluster operations were used. Targeted Pylint errors/warnings and documentation/
format checks pass. Full suite: 386 tests, 21 skips.

Local Bandit findings decreased from 225 to 223, with no analysis errors and no
remaining B310 report in this helper. No rule was disabled to achieve this change.
Live administrative endpoint compatibility and GitHub reconciliation remain to
be verified after publication; no provisioning or deployment was performed.

### Larger retained-test documentation batch (2026-11-11)

Added 152 missing function docstrings across eight retained test modules covering
rendered-resource validation, platform health, infrastructure backfill, trim
coverage, Kyverno exceptions, Longhorn reporting and component security, and
Codacy SARIF preparation. This fixes the documentation findings in source;
no lint rules or security findings were suppressed.

Validation: all eight modules pass targeted Pylint checks for missing module,
class, and function docstrings, 100-character line length, and multiple
statements. Comparing parsed source with function docstrings removed confirms
that executable ASTs are identical to HEAD. One full unittest run passed
(386 tests, 21 skipped), and `git diff --check` passed. GitHub alert closure
remains dependent on a subsequent scan of the published changes.

### Complete retained-test function documentation (2026-11-11)

Extended the documentation cleanup by another 258 missing function docstrings
across 47 retained test modules. Combined with the preceding 152-finding batch,
this documents 410 functions across 55 modules. All repository test modules now
pass the targeted Pylint checks for missing module, class, and function
docstrings, 100-character line length, and multiple statements. No findings
were dismissed and no rules were disabled.

Verified executable AST equivalence to HEAD for all 55 changed test modules,
with function docstrings removed from the comparison. The full suite ran once
for this extended batch: 386 tests passed, with 21 skipped. Final documentation
wording refinements also pass targeted lint. Live-dependent skipped tests and
GitHub alert closure after publication remain unverified; this local cleanup
does not establish either result. Changes remain unstaged and uncommitted.

### Finish repository Python function documentation (2026-11-11)

Documented the remaining 139 functions across 47 operational, CI, generator,
probe, and archived-test modules. All 121 repository Python modules now pass
targeted Pylint checks for missing module/class/function documentation,
100-character line length, and multiple statements. No rule was disabled and
no alert was dismissed.

Synchronized the embedded backfill sources in `infra-guards/resources.yaml`,
`longhorn/component-security-backfill.yaml`, and
`longhorn/recurring-job-security-backfill.yaml`. Parsed manifest comparison
confirms that only Python docstrings changed in the embedded `backfill.py` and
`storage_guard.py` values; all other resource fields remain identical to HEAD.
Executable AST comparisons also pass for all 47 changed Python source modules.
Component-security, infrastructure-guard, and Kyverno exception generation
checks pass. One full unittest run passed (386 tests, 21 skipped), as did
`git diff --check`. Runtime probes requiring live services or containers were
not executed for this documentation-only change. GitHub counts still require
a published-source rescan; this batch remains unstaged and uncommitted.

### Retire app-local one-off migration and recovery artifacts (2026-11-11)

Following the requested preference for cleanup over repairing unused one-off
jobs, removed 16 artifacts:

- The Bitwarden, Dawarich, Keycloak, and Mastodon PostgreSQL migration Jobs.
  Their active application manifests already select their app-local PostgreSQL
  services rather than the Jobs' former shared source database.
- The old MySQL migration helper and Nextcloud/WordPress wrappers, plus the
  manually deployed MySQL and PostgreSQL CLI bundles. No current GitOps source
  selects these tools.
- The obsolete Mastodon environment patch and the applied connectivity-exporter
  non-root review patch.
- The Vault-specific snapshot rehearsal helper for the completed OpenBao cutover.
  The migration document now identifies the procedure as historical and links
  to the retained helper revision in Git history.
- The manual Hister reindex Job and three archived one-off artifacts: Mastodon
  migration Pod, Firefox-to-Hister import Job, and Immich tag-today Job.

Retained the Hister disposable startup/import/search/reindex/restart probe.
Its isolated reindex client now uses the active server's image and reviewed
security settings with the same reindex command as before; those image,
identity, guard, and command equivalences were checked before removing the Job.
The permission-helper probe still checks the active Hister deployment's init
container. Removed only the duplicate check of the retired Job. Active backups,
CronJobs, database workloads, PVC manifests, reusable maintenance tools, and CI
security probes remain in place.

Validation: checked all 76 local GitOps sources using the renderer's directory
matching rules; none select any removed artifact. Surviving source references
were checked, preserving historical changelog/inventory evidence. Both modified
probes parse and pass targeted Pylint error/documentation/format checks. One full
unittest run passed (386 tests, 21 skipped), and `git diff --check` passed.
Live workload inspection was unavailable, and container runtime probes were not
executed. No live resources or data were changed; no alerts were dismissed.
GitHub alert reductions require publication and rescan. Changes remain unstaged
and uncommitted.

### Retained Python maintenance batch (2026-11-11)

Reduced full-repository local Pylint findings from 386 to 316. The batch removes
11 redundant negations, 23 delayed imports, 10 unused keyword-dictionary
bindings, four unused local bindings, three assigned lambdas, five dictionary
constructor calls, two redundant class pass statements, and two inconsistent
return paths. Callback keyword dictionaries still accept the same arbitrary
keywords. Membership and comparison guards remain executable, including the
FRR and Plex security checks. No checks or lint rules were disabled.

Two Longhorn policy probes now materialize the YAML document sequence before
unpacking its policy and binding. This resolves seven incorrect generator-type
diagnostics while retaining exact-two-document validation. The hostile-YAML
regression invokes the renderer's actual imported loader functions, resolving
its artificial local import-path diagnostic. Complexity counters also decrease
slightly; Pylint detects one additional duplicate-code block in the now-similar
policy probe setup, which remains open for later consolidation.

Validation: one full unittest run passed (386 tests, 21 skipped). Final import
ordering passes Pylint, and component-security, infrastructure-guard, and
Kyverno exception generation checks produce identical existing artifacts.
`git diff --check` passes. Container-dependent security probes were not run.

The local full scan reports an unresolved `storage_guard` import in
`tools/security/infra_guard_backfill.py`. Its runtime module is explicitly
supplied as `storage_guard.py` by `tools/security/generate-infra-guards.py`,
using the reviewed Longhorn backfill source. The infrastructure unit tests
exercise this module via the same source under that name. This is a local
analysis packaging limitation; the finding remains unsuppressed and has not
been dismissed. Remote alert counts require publication and rescan. Changes
remain unstaged and uncommitted.


### Remove verified retired database and archived stacks (2026-11-11)

Current GitHub inventory contained 2,208 open alerts before the individual
false-positive decision below: 306 modern Pylint, 1,396 legacy Pylint, 226
Bandit, 47 Opengrep, and 233 from other historical analyzers. This snapshot
is evidence of progress, not a claim that the overall goal is complete.

Removed 94 files (3,828 lines) from the retired shared `postgres/` deployment
and nine unused archived stacks: `DEPRECATED/wazuh`, `camera`, `rsyslog`,
`rancher`, `unifi`, `cron`, `mysql`, `minio-single`, and `promtail`.
The sources remain available in [Git history](https://github.com/shaman007/home-k3s/tree/1ca52307dc0f55ef58aad73d30629595ae8a872f).
Historical changelog and migration inventories were retained.

Evidence: read-only live inspection found no matching Deployment, StatefulSet,
DaemonSet, CronJob, or Job for any of the 23 archived workload identities.
The `db` namespace has no Deployment or StatefulSet, no live Argo application
selects `postgres/` or `mysql/`, and the Bitwarden, Dawarich, Keycloak, and
Mastodon application-local PostgreSQL StatefulSets each have a ready replica.
Checking all 76 repository-local GitOps sources with the renderer's selection
rules found no selected files in this deletion batch. No nonhistorical exact
source-path references remain. This cleanup changes repository files only;
it does not delete live PVCs, snapshots, secrets, or any other cluster resource.

The removed paths contain 19 currently open alerts (4391, 4390, 4389, 4388, 4387, 4385, 4383, 4380, 4379, 4377, 4375, 4374, 4373, 4370, 4369, 4366, 4363, 4361, 4360).
These alerts were not dismissed; a scan of the published deletion must close
them normally. One full unittest run passed (386 tests, 21 skipped), and
`git diff --check` passed. Changes remain unstaged and uncommitted.

Individually dismissed Opengrep alert #4378 as a verified false positive.
At its exact [scanned revision](https://github.com/shaman007/home-k3s/blob/e17d946c5e5838b3b8e203a4fbd164baec33dd84/wordpress/stateful-set-valkey.yaml),
`redis-exporter` inherits `&securityContext` through `<<: *securityContext`.
Parsing that source resolves `allowPrivilegeEscalation: false` for both Valkey
and the exporter; the finding incorrectly flags the merge site. The GitHub
API confirmed state `dismissed`, reason `false positive`, with a comment
recording the scanned commit and requiring reopening if the anchor or merge
changes. No blanket YAML-rule suppression was added.


### Complete requested retired-platform cleanup and protect Sync HTTP (2026-11-11)

Removed 25 more files (671 lines): the remaining `DEPRECATED/omni/`, `ttrss/`,
and `dashboard/` trees; Wazuh's archived Argo application, Vault policy, and
Harbor/Loki network policies; the archived TTRSS PostgreSQL configuration; and
six obsolete Argo declarations for the already retired PostgreSQL/exporter,
Rancher, Promtail, MySQL, and single-instance MinIO sources. Updated the archive
index. No Wazuh, TTRSS, Omni, or dashboard-named files remain under DEPRECATED.
All 25 files are recoverable from revision `dc03cd06d86136be907309fcbce97f955c11c360` in Git history.
None are selected by the 76 current local GitOps sources. Active applications,
cluster resources, and persistent data were not changed.

Added a shared origin-bound HTTP transport for Firefox Sync secret bootstrap
and storage verification. Bootstrap is restricted to the reviewed OpenBao
HTTPS origin; the verifier accepts only the reviewed Sync HTTPS origin or its
explicit loopback HTTP tunnel. Requests cannot change origin, and all 301,
302, 303, 307, and 308 redirects are refused before forwarding. Invalid ports,
userinfo, fragments, whitespace and non-origin base URLs fail validation before
secret access. HTTP error responses are closed, preserving optional bootstrap
404 handling and sanitized error reporting. Timeout remains 15 seconds.

Factored the existing socket-free HTTP fixture for reuse by administrative and
Sync client regressions. Eight additional tests cover origin validation,
cross-origin rejection, preserved request transport, redirect handling, error
closure, and pre-secret validation. Actual urllib redirect dispatch was
exercised across 120 combinations of origin, status, method and destination.
Replacing the redirect guard with the standard handler causes 72 failures,
confirming detection of credential forwarding. No real credentials, endpoints,
OpenBao writes, or storage-probe writes were used.

Validation: final full suite passes (394 tests, 21 skipped). New transport and
fixture/test modules pass full Pylint; all touched Python files pass targeted
error, documentation, and formatting checks. Both CLI import paths work in
plan/help mode. Bandit decreased from 223 to 221 findings with zero analysis
errors, resolving both Sync tools' B310 findings without suppression. GitHub
counts require publication and rescan. `git diff --check` passes. Changes
remain unstaged and uncommitted.

### Larger Bandit, naming, and unused-argument batch (2026-11-11)

Reduced local Bandit findings from 221 to 215, with zero analysis errors:

- Both benchmark clients now validate explicit HTTP/HTTPS service URLs before
  secret lookup, reject every redirect before replaying credential-bearing
  requests, close responses, and sanitize HTTP/transport failures. Explicit
  local/cluster HTTP endpoints remain supported. Provider payloads, streaming
  completion/usage data, timeout settings, and partial deadline results remain
  covered by regressions.
- Chart fallback downloads now require HTTPS for initial URLs and every redirect.
  Signed cross-host HTTPS downloads remain supported. The archive still must
  match its pinned index SHA-256 before Helm can use it. Failure messages do not
  expose signed URLs.
- Plex identity/preferences parsing now uses defusedxml with DTDs, entities and
  external resources forbidden, a 1 MiB document limit, and sanitized errors.
  The pinned defusedxml dependency is recorded in tools/security/requirements.txt
  and installed by CI. This resolves B405 and both B314 findings; the HTTP changes
  resolve three B310 findings. No Bandit rules were disabled.

Renamed 54 Python CLI/source filenames to snake_case and updated active code,
workflow, hook, operator-documentation, service-unit and generator references.
Historical migration inventories, changelog entries and immutable Git links
were preserved. The generated artifacts were synchronized. External callers
must use the new underscore filenames; no installed scripts or live workloads
were updated by this task.

Resolved all 71 naming findings: filenames, constant/function names, and twelve
HTTP method implementations. Framework-required do_GET/do_POST/do_PUT/do_PATCH/
do_HEAD names remain explicit aliases of snake_case implementations. AST
comparison verifies identical signatures and bodies for all twelve callbacks.
Canonical executable AST comparison verifies the naming-only changes in 48
renamed modules; six modules with intentional HTTP/XML hardening or preceding
HTTP changes were excluded from that equivalence claim.

Removed two unused internal report parameters, marked genuinely ignored callback
arguments explicitly, and strengthened the trim fixture to require a patch on
its write path. All ten remaining unused-argument findings are resolved. No
runtime security predicates were removed.

Final full-repository Pylint scan: 235 findings, down from 316. All 129 Python
modules now have zero invalid-name, unused-variable, unused-argument,
unused-import, missing-module/class/function-docstring, line-too-long, and
multiple-statements findings. The line-length gate is 100 characters. Legacy
GitHub scanner counts may remain stale; these source checks do not dismiss them.
The existing storage_guard local-import analysis limitation remains documented.

Validation: the full suite passed (407 tests, 21 skipped). After regrouping two
URL-validation conditions without changing their predicates, the ten benchmark
and chart HTTP tests passed again. All five generators with check modes pass;
all three modified workflows pass actionlint with ShellCheck. Canonical parsed
comparison confirms unchanged resource semantics in the five modified Kubernetes
YAML artifacts, including embedded Python callback aliases. No nonhistorical
references to old Python filenames remain. Selected CLI help/plan entry points
work under their new names. git diff --check passes. No real credentials,
provisioning operations, container-runtime probes, or live deployments were used.
GitHub alert closure still requires publication and rescan. Changes remain
unstaged and uncommitted.

### Frequency-ranked probe subprocess batch (2026-11-11)

Pulled 2,056 open GitHub findings and ranked them by scanner/rule frequency.
The largest groups were legacy Pylint missing docstrings (440), long lines
(334), and whitespace (261), all from commit 2ff670f9b304. Current-source
Pylint checks for those rules are clean, and a full Ruff E2 spacing sweep
reports zero findings. Retired scanner results are handled by the separately
approved exact stale-alert list, rather than by disabling current checks.

For the largest retained security groups, consolidated 26 subprocess calls
across 13 isolated security probes through tools/security/probe_commands.py.
The runner requires explicit nonempty text argv, rejects relative executable
paths and process overrides, resolves bare programs only through /usr/bin:/bin,
uses shell=False, and requires finite positive timeouts. Existing explicit
capture/text/check options and timeouts are preserved; formerly unbounded host
calls now default to 90 seconds. Explicit absolute executables remain supported.
No production workloads, devices, credentials or data were used for verification.

Canonical AST comparison proves the thirteen probe bodies and command vectors
are otherwise identical to revision 6b24168a1d17. Regression tests cover all
thirteen wrappers' success/error modes, intentionally inspected failed processes,
argument boundaries, hostile PATH entries, finite timeouts, subprocess exception
propagation, and literal metacharacter round trips through a real Python child.
The optimized precondition tests still reject unsafe contexts under -O/-OO.

Validation: final full suite passed (418 tests, 21 skipped). An initial combined
run identified a test loader missing the normal CLI sibling-import path; that
fixture setup was corrected before the successful run. Bandit decreased from
215 to 161 findings with zero analysis errors: subprocess-call audit sites fell
from 88 to 63, subprocess import audits from 51 to 41, and partial-executable
findings from 43 to 24. The remaining centralized subprocess audit is intentional;
no rules were suppressed. The helper passes full Pylint, and git diff --check
passes. No container-runtime probes or live deployments were executed.

### Verified current CodeQL false positive and Markdown refresh (2026-11-11)

Individually dismissed CodeQL alert #7610 as false positive after tracing the
exact SARIF flows in analysis 2143960020 at commit 6b24168a1d17. The sources are
fixed ExternalSecret diagnostic messages and the non-secret refresh constants
15m and 900; those values were heuristically classified as credentials. The
sink excludes resource values and parser source snippets. A new main-level
logging regression passes invalid Secret/ExternalSecret/SecretStore documents
with sensitive markers through the actual output path and proves those markers
never reach output. The API confirmed the false-positive disposition and its
explanatory comment. Reopen if diagnostics begin including resource values.

Manually dispatched the retained Remark-lint scanner against published commit
6b24168a1d17. Run https://github.com/shaman007/home-k3s/actions/runs/43029701629
completed successfully, including SARIF preparation and upload. All sixteen
historical checklist alerts (#4418 through #4433) were independently verified
as fixed by the API at 2026-11-11T13:30:53Z. They were not dismissed. The current
checklist uses plain bullets and retains the original historical-review meaning.


### Approved stale dispositions completed (2026-11-11)

The user explicitly approved the exact 1,440 IDs in the
[historical review snapshot](https://github.com/shaman007/home-k3s/blob/16e7083d90253082880085ffc93a48352dce5164/docs/security-stale-alerts.json),
superseding the earlier request to keep legacy findings open. Completed 1,396
retired Pylint, 31 retired Ruby, six retired SQL and seven deleted-source
historical dispositions as won't fix. Every API response was checked for the
reason, explanatory comment, scanner identity and unchanged historical commit.
A final independent open-alert inventory confirms none of the selected IDs
remains open. Analysis history and active scanners were retained. The initial
automatic approval rejection was resolved by the user's count-specific approval;
no alternate route was used to bypass the review.

GitHub open findings fell from 2,056 to 599 after these dispositions, the sixteen
Markdown fixes verified by rescan, and the separately reviewed CodeQL false
positive. The remaining list was ranked by rule frequency for the review.
After the Django-plugin review below, the independently verified final open count
is 586. This does not establish that all remaining findings are resolved.

The thirteen current PyLintPython3_E5110 findings were individually re-reviewed:
all report forced pylint-django configuration on a repository with no Django
imports across 131 Python modules. The missing Django framework/settings warning
is not a defect in these non-Django tools. Each exact alert instance and commit
was checked before dismissal as false positive, with a comment requiring review
if Django source/settings are introduced. These are a separate verified decision,
not an expansion of the approved stale-alert ID set. Current real findings stay
open, and no lint or security rule was disabled.

Executable resolution hardening constrains top-level host commands; child
process environments are otherwise inherited normally. The source changes,
regression tests and decision records remain uncommitted and unpushed.


### Final verified remaining priorities (2026-11-11)
GitHub now reports **586 open findings**, down from 2,056 at the
start of this batch: 1,440 approved stale dispositions, sixteen fixes verified
by Markdown rescan, and fourteen individually supported false-positive decisions.
The table below records the highest-frequency rules from that API snapshot.
The generated findings export and completed dismissal JSON were removed from the
current tree at the user's request as one-off artifacts. Regenerate live inventories
from GitHub when continuing remediation; snapshots do not prove current state.
The approved IDs and comments remain available in the historical review snapshot
linked above, and GitHub retains the individual alert histories.

| Count | Scanner | Rule |
| ---: | --- | --- |
| 90 | Bandit | `Bandit_B603` |
| 90 | Prospector | `Prospector_pylint` |
| 73 | Prospector | `Prospector_pep8` |
| 52 | Bandit | `Bandit_B404` |
| 45 | Pylintpython3 | `PyLintPython3_R0914` |
| 43 | Bandit | `Bandit_B607` |
| 32 | Pylintpython3 | `PyLintPython3_R0912` |
| 26 | Pylintpython3 | `PyLintPython3_R0915` |

The probe hardening reduces local Bandit findings from 215 to 161;
that source reduction is not yet reflected in these GitHub counts. All 131
Python modules pass the current naming, unused-variable/argument/import,
missing-docstring, line-length and statement checks, and Ruff E2 spacing is
clean. The overall goal remains active: the retained findings still require
source fixes, refreshed analyses, or individually evidenced decisions.


### CI validation and private build outputs (2026-11-11)

Split the SARIF adapter and rendered-manifest validator into focused functions,
removing six excessive-locals/branches/statements diagnostics without disabling
checks. Both CI modules and the webhook build generator pass full Pylint.
Five hundred generated mixed-tool, multi-batch SARIF cases produce exactly the
previous adapter's output and leave their inputs unchanged.

Prospector's retained report includes `invalid syntax ... (syntax-error)` under
its aggregate `Prospector_pylint` rule. The adapter now recognizes that format,
including rule-index-only reports, and rejects it before creating upload output.
It also rejects explicit failed SARIF invocations for every scanner, including
empty security reports. Other Prospector diagnostics remain uploadable; findings
are not filtered. No Prospector refresh has been claimed or uploaded here.

Additional CRD downloads validate their HTTPS endpoint and restrict curl's initial
and redirect protocols to HTTPS. The explicit system curl path removes implicit
PATH resolution. The original 15-second connect, 120-second total-transfer and
130-second process limits remain intact. Complete application inventory, raw
manifest discovery, CRD failure gates, custom/built-in failure exit status,
private temporary files and value-free diagnostics have regression coverage.

The webhook build generator now allocates a new exclusive 0600 temporary file
instead of overwriting a predictable /tmp path. Repeated generation preserves
prior review files and produces identical source archives and Job identity.
No build Job was submitted, image built or pushed, or live resources changed.

The user's linked Validate Kubernetes job 130570081385 in run 43034568266 checked
out 5bd93c1d successfully, then failed installing ripgrep because the runner could
not resolve Ubuntu's package mirror. The requested retry, job 130573860496,
failed with the identical mirror DNS error and exit 100. No further retry of the
unchanged commit was requested. The prepared workflow instead downloads official
ripgrep 15.2.0 from its GitHub
release, verifies the pinned SHA-256 before extracting the exact binary, and
cleans the temporary archive. The downloaded binary's digest and PCRE2 support
were verified locally, and the complete repository suite passes using that binary.

Validation: 426 unit tests passed, 21 skipped; the opt-in live runtime checks
remain unexecuted. Workflow actionlint/ShellCheck, Ruff E2 spacing and diff checks
pass. Local Bandit is 159 findings with zero analysis errors, down from 161 at
this batch's start. GitHub reconciliation still requires publication and scans;
no commits or pushes were performed by the agent.


A subsequent live API refresh after the user published probe hardening and the
inventory cleanup confirms **542 open GitHub findings**: Bandit 164, modern
Pylint 179, Opengrep 26, Prospector 169 and PowerShell 4. The current scanner
instances reference 5bd93c1d; 173 historical Prospector/PowerShell results remain
at 2ff670f9b304. This is a net reduction of 44 from the preceding 586 snapshot,
including 54 fewer Bandit reports. The new CI/build fixes above remain local and
are not included in that remote reduction. All 132 current Python modules still
pass naming, unused-value/import, missing-docstring, 100-character line-length
and multiple-statement checks; Ruff E2 spacing remains clean.


### Refreshed retained findings and equivalent style fixes (2026-11-11)

A fresh complete open-alert inventory found no genuinely deleted source files.
The 119 missing-path alerts had twelve verified snake_case counterparts; these
were retained-code renames, so they were not dismissed as removed tooling.
The guarded Prospector rescan
[43038123577](https://github.com/shaman007/home-k3s/actions/runs/43038123577)
completed successfully at 8e9c748e, including preparation and upload. Every open
Prospector instance now references that revision. Its total fell from 169 to 155;
this was genuine scanner reconciliation, not a dismissal or empty report.

Twelve newly emitted E5110 warnings were individually re-reviewed and dismissed
as false positives. Codacy's
[official wrapper](https://github.com/codacy/codacy-pylint-python3/blob/master/src/codacy_pylint.py#L225-L236)
forcibly loads pylint_django, while AST inspection of all 132 repository Python
files finds no Django imports. Each unchanged alert instance was checked before
PATCH, and each response confirmed the exact reason and explanatory comment.
Revisit these decisions if Django is introduced. No source checks were disabled.
Reviewed IDs: 7807, 7806, 7805, 7804, 7803, 7802, 7801, 7800, 7799, 7798, 7797, 7793.

The refreshed Prospector report also flagged twelve required HTTP handler
aliases as mixedCase variables (N815). Each is a direct class-body alias from
one of do_GET/do_POST/do_PUT/do_PATCH/do_HEAD to its snake_case implementation in
a BaseHTTPRequestHandler subclass. CPython's handle_one_request constructs
"do_" plus the request method and dispatches through that attribute, so the
protocol spelling must remain. These exact cases were individually classified
as false positives, with per-hook explanatory comments and instance guards.
Reviewed IDs: 7946, 7930, 7929, 7928, 7927, 7911, 7910, 7894, 7892, 7891, 7832, 7831.

Fixed 54 E713/E714 membership/identity spellings across 22 source files,
including the 34 E713 findings surfaced by the refreshed scan. Canonical AST
comparison proves the predicates are unchanged. Regenerated the two ConfigMaps
that embed the storage guard; parsed-bundle comparison confirms their only
changes are equivalent Python negation spelling. Generator consistency checks
pass for Longhorn components, infrastructure guards and Kyverno exceptions.

Separated chart lookup, values precedence, release fallback and directory
rendering into focused functions. A frozen RenderContext groups the source root,
private scratch path and Kubernetes version. Full Pylint on the renderer falls
from nine diagnostics to zero: three excessive-locals, two excessive-branches,
two excessive-arguments and two excessive-positional-arguments findings.
Comparisons across all 97 current Argo application sources produce exactly the
same outputs, argv, working directories, values files and error behavior, with
no source rejections. Existing digest, path, fallback and option checks remain.

The full suite passes: 426 tests, 21 opt-in runtime checks skipped. Ruff E2,
E713 and E714 checks and git diff --check pass. All twelve jobs of published
Validate Kubernetes run 43036783957 now pass, verifying the earlier ripgrep
installation fix and its downstream checks. The renderer/comparison cleanup is
still local; its eventual alert closure needs publication and fresh scans.


Final independent API and UI checks confirm **500 open alerts**: modern Pylint
165, Bandit 162, Prospector 143, Opengrep 26 and PowerShell 4. Every open source
path now exists locally. This turn's 24 false-positive dispositions comprise the
twelve forced-Django warnings and twelve required HTTP aliases described above.
The remaining decrease follows published source fixes and genuine rescans;
no current-source finding was dismissed on the basis of a missing renamed path.
All 132 Python modules also pass the selected naming, unused-value/import,
missing-docstring, line-length and multiple-statement checks. Changes remain
uncommitted and unpushed by the agent; no one-off alert JSON was added to the tree.


### PowerShell retirement by user decision (2026-11-11)

The user explicitly requested removal of all PowerShell tooling because Windows
is no longer used. Removed the Longhorn recurring-job exporter and the Grafana
live-dashboard exporter/vendor-sync script. This also removes the unused Grafana
exporter's insecure-TLS default rather than maintaining an obsolete client.
No replacement exporter, PowerShell runtime or new tool dependency was added.
The temporary runtime downloaded before this scope correction was removed.

Removed PSScriptAnalyzer from manual dispatch choices and the tool matrix.
Converted the Karakeep and NetworkPolicy command examples to Bash, including the
Meilisearch authenticated requests and historical dump example. The examples pass
bearer headers through stdin, keep the key out of argv, and use fail-fast pipeline
handling. Removed current dashboard instructions for the deleted scripts.
Historical security-review entries and migration inventory records remain history.

The four historical PSScriptAnalyzer findings (#1880, #1881, #1882 and #1883)
were retired as won't fix with per-alert comments describing the explicit user
decision. Their old source paths and historical revision were checked before
mutation; responses confirmed the exact reason and comment. This is a retirement
decision, not a claim of a successful PowerShell rescan. Source deletion and the
workflow change still require publication by the user.

Validation: no PowerShell source files or active PowerShell invocation references
remain in the repository tooling/workflows or updated runbooks. Workflow
Actionlint/ShellCheck and git diff --check pass; twelve Bash documentation blocks
parse successfully. The recurring-job snapshot's parsed resources are identical
before and after its obsolete provenance comment was replaced. Dashboard data,
JSON snapshots, Longhorn resources and live cluster state were not changed.

An independent API refresh confirms zero open PowerShell findings and 487 open
findings overall after the user published the preceding renderer batch. The
PowerShell source removal above remains uncommitted at this verification.


### Network report evidence-preserving refactor (2026-11-11)

Separated telemetry-window collection, client/flow accounting, final-flow
correlation, incident grouping, monitoring health and baseline comparison into
focused functions. Shared the existing reputation/public-service predicates
between preclassification and final verdict handling. The configured public
ports, inbound direction, fewer-than-20-flow and below-64-KiB limits remain;
substantive corroboration still blocks the background exception. No guard was
removed, relaxed or disabled. The deployed tool remains self-contained.

Full Pylint findings on this module decrease from twelve to one: four excessive
locals, three excessive boolean expressions, two excessive branches and two
excessive statements are resolved. The remaining broad exception boundary is
intentional: unexpected model/transport/schema failures must retain incomplete
analysis rather than produce an all-clear, and the process ultimately exits
with the error. The warning remains open and is not suppressed or dismissed.

Removed an unused pre-batch model schema; the actual bounded per-batch schemas
and complete evidence-ID checks remain. Model TLS requests now close connections
on every exit, including certificate-pin, connect, response-read and HTTP errors.
The reviewed CA/pin checks still precede sending any telemetry. SMTP keeps EHLO,
STARTTLS, EHLO and message submission in that order; failed TLS prevents delivery.

Validation: 120 deterministic mixed plain/gzip telemetry fixtures produce exactly
the previous implementation's evidence, assessments and input mutations against
revision 23897eba. Ten added regression tests cover final-flow evidence beyond
the window, probe thresholds, malformed/boundary records, custom public ports,
corroboration, monitoring failure order, model TLS cleanup, incomplete streams,
bounded/complete model batches and SMTP TLS failure. The full suite passes
(436 tests, 21 opt-in checks skipped), and the final eighteen network-specific
tests and full Pylint on their test module pass. No sensor, model, SMTP or cluster
endpoint was contacted. Deployment and GitHub reconciliation require publication;
the commit is local only and must not be pushed by the agent.


### Policy harness complexity and reviewed constants (2026-11-11)

Separated fixture mutation, case generation and result checking in the Longhorn
component/recurring-job harnesses and infrastructure guard harness. Nine Pylint
complexity diagnostics are removed: one excessive-locals, branches and statements
finding per harness. Each module passes full Pylint when analyzed individually.
The combined analysis retains the same three cross-file duplicate-code advisories
as the original source; no checks were suppressed to hide them.

Independent extraction of the original main functions at 4a6ac9c8 confirms that
all 92 component and 36 recurring-job fixture/expectation tuples are identical,
without modifying their input catalogs. Expanding the new infrastructure helper
bodies reproduces the complete original per-entry check AST. Required environment
values/field references, extra-container/volume/mount rejections, DaemonSet order,
exact mutation and idempotence checks remain intact.

Verified the official Kyverno 1.19.2 archive against the same SHA-256 pinned by
CI, then ran the real offline CEL engine: 92 component mutation/scope cases plus
16 idempotence checks, 36 recurring-job cases plus 28 idempotence checks, and 74
infrastructure mutation/scope/idempotence checks pass. The full repository suite
passes (436 tests, 21 opt-in checks skipped). Ruff E2/E713/E714 and diff checks
pass. No Kubernetes API, production workloads or persistent data were touched.

Individually reviewed and dismissed three exact false positives with comments:
Bandit #7516 and Prospector #7808 mistake the public 15m refresh cadence constant
for a credential; its related store interval is 900 seconds. Existing logging
regressions verify Secret values are excluded from diagnostics. Opengrep #7621
misclassifies mode 0700 as broadly permissive: group/other bits are zero and the
private render directory is owner-only; output files are 0600. The existing
regression verifies an inherited 0755 directory is restricted to 0700. Each
scanner, source path and current instance revision was checked before PATCH,
and each response confirmed the precise false-positive reason and comment.
Analysis history and all source checks remain enabled. These decisions do not
classify other subprocess, TLS or Kubernetes-context findings as false positives.


### Published-source reconciliation and bounded import/path reviews (2026-11-11)

Confirmed published main was c4dde04d and manually dispatched the guarded
Prospector scanner against it. Run
[43047060854](https://github.com/shaman007/home-k3s/actions/runs/43047060854)
completed successfully, including preparation and upload. Its open total fell
from 142 to 80; every remaining Prospector instance now references c4dde04d.
All 34 historical E713 membership findings are absent after the genuine rescan.
The normal four-tool run 43046926219 also passed every job and reconciled the
preceding policy complexity fixes. No fake or incomplete analysis was uploaded.

Reviewed four B404 imports whose complete AST references to subprocess are only
CalledProcessError, CompletedProcess or TimeoutExpired data types. No process
launch function is referenced through those imports. These exact warnings were
dismissed with type-specific comments and a requirement to reopen if a launch
API is introduced; separate process-launch audits remain open.
Reviewed IDs: 7791, 7776, 7775, 4340.

Individually reviewed eleven B108 temporary-path reports in their exact published
revision and AST context. Four literals are search strings rewritten into unique
private test directories, one is an absolute executable test input under a
mocked subprocess.run, one is the parent of a secure TemporaryDirectory allocator,
two are mode-1777 tmpfs mounts inside disposable network-isolated containers,
two refer to generated transcode output accessed through podman exec, and one
only stats /tmp inside a disposable Dovecot fixture. None creates a predictable
host temporary file. Local allocator verification confirmed mode 0700; container
mount and exec argument boundaries were inspected directly. No container runtime
probe or production data was used for this review.
Reviewed IDs: 7585, 7584, 7574, 7573, 7508, 7476, 4346, 4345, 4341, 4296, 4211.

All fifteen exact dispositions were confirmed with explanatory comments, scanner
and instance-revision checks, and an independent final open-alert inventory.
The three unclassified temporary-path findings (#7478, #6890 and #4315) remain
open for separate review; no blanket temporary-path or subprocess rule was disabled.

Removed the ET acronym alias from the Plex probe's defusedxml ElementTree import,
addressing the remaining N817 naming report. Canonical AST comparison confirms
only the import binding and its references change. The three real XML-parser
regressions pass, including size, malformed-input and forbidden-declaration
checks; selected Pylint and Ruff checks pass. No live Plex/container probe ran.
The import source fix still needs publication and subsequent scanner refresh.

Independent API and UI checks now confirm **387 open alerts**: Bandit 146,
modern Pylint 136, Prospector 80 and Opengrep 25, down from the preceding 473
snapshot. This combines genuine scan reconciliation with fifteen individually
supported false-positive decisions. The broader remediation goal remains active.


### Private runtime fixtures and explicit NGINX source selection

Addressed the source causes behind temporary-path alerts #6890 and #4315.
The opt-in Sieve test now allocates a private directory with mktemp, validates
its returned path, registers class cleanup before compilation, and gives the
fixture directory and mode-0600 files to the synthetic mail UID. Paths are
passed as shell positional arguments rather than interpolated into commands.
Pod commands have a 60-second deadline. The deployed-rule equality check and
all seven message behavior cases remain intact.

The NGINX runtime suite requires an explicitly selected matching source tree.
Both fixture configs must resolve to regular files within that tree. Invalid
or missing sources fail before temporary directories, servers or processes
are created; requesting the binary without its source does not silently skip.
The Dovecot probe now mounts its isolated /tmp tmpfs with mode 1777 initially,
matching its existing sticky-bit assertion. Alert #7478 remains open pending
publication and a separate disposition of the container mount context.

Seven local regressions exercise compiler-failure cleanup, divergent deployed
rules, invalid allocation responses, positional shell arguments, command
deadlines, missing source setup and config symlink containment. The full suite
ran 443 tests successfully with 21 opt-in skips. Selected Pylint and Ruff checks
passed; Bandit reported no analysis errors. No live pod, NGINX server, container
probe or application deployment was executed. Source-based alert closures still
require publication and genuine scanner refresh; no scanner rule was disabled.


### Separate Traefik administrative reconciliation from verification

Split the provisioning tool's large main function into credential loading,
client reconciliation and contract verification, KV reads and CAS writes, and
OpenBao prerequisite verification. Check-only mode retains its preliminary KV
reads and performs no writes. Client updates retain unrelated fields and mappers;
existing session secrets are preserved and malformed sessions still block writes.
The HTTPS origin, header scoping and redirect rejection checks are unchanged.

A transient comparison against the preceding committed implementation exercised
648 combinations of check/write mode, missing or duplicate clients, configuration
drift, invalid sessions, missing keys, unavailable prerequisites and injected
request failures. Ordered requests, headers, payloads, output and exceptions
matched exactly. Four permanent mocked regressions cover preservation of client
fields/mappers, CAS versions and session secrets, invalid-session refusal, and
duplicate-client refusal. No credential file or administrative service was used.

The full suite ran 447 tests successfully with 21 opt-in skips. Ruff and diff
checks passed, and Bandit reported no analysis errors. Full Pylint no longer
reports main's excessive locals, branches or statements; its three existing
HTTP callback signature/origin-expression warnings remain open for review.
Publication and genuine scanner refresh are still required for alert closure.


### Separate NGINX read-only content probe responsibilities

Refactored the NGINX content probe into explicit manifest validation, synthetic
fixture creation, backend and NGINX startup, HTTP behavior checks, and runtime
guard verification. An immutable target record replaces six positional probe
arguments. Both application entry points retain their original target values.
All five local Pylint warnings for argument counts, locals, branches and statements
are gone; the probe and its regression module both pass full Pylint checks.

A transient comparison with the preceding implementation covered 46 combinations
of Nextcloud/WordPress and injected command failures. Ordered command arguments,
fixture file bytes, output and exceptions matched exactly, including reverse
container cleanup. Three permanent offline regressions check backend cleanup on
NGINX startup failure, rejection of writable mounts and each missing process
guard, and refusal of a truncated FastCGI upload despite HTTP 200. Existing
read-only content, capabilities, no-new-privileges, seccomp and request-size
assertions remain active. No container, live workload or external endpoint was used.

The full unit suite passed with 450 tests and 21 opt-in skips. Ruff and diff
checks passed; Bandit reported no analysis errors. These source changes still
require publication and genuine scanner refresh before remote findings close.


### Token lifetime and SafeLoader false-positive review

Independently refreshed the open inventory at 387. Reviewed the exact scanned
4049613b source for Bandit #7526, #7488 and #7484: their 1h/24h values are
OpenBao auth-role token_ttl/token_max_ttl durations, not credential material.
Reviewed #7306 against the same revision: UniqueKeyLoader directly subclasses
yaml.SafeLoader, only overrides mapping construction for duplicate-key rejection,
and is explicitly passed to both YAML load APIs. It adds no object constructors.
Existing regressions reject Python object tags through both single-document
and multi-document parsing and retain duplicate-key rejection.

Dismissed only those four findings as false positives, with individual explanatory
comments and reopening conditions. Each PATCH checked the current rule, path,
instance revision and state before changing it; responses and an independent
open-alert inventory confirmed the decisions. The verified open count is now
383. No scanner rule or YAML safety check was disabled.

Bound the Firefox Sync bootstrap test's per-iteration response iterator in its
handler default, removing the remaining W0640 closure warning without changing
its synchronous behavior. All six bootstrap tests and all 33 rendered-validation
tests passed; the focused Pylint check, Ruff and diff checks passed. No live
OpenBao service, cluster resource or credential file was used. The source fix
still requires publication and scanner refresh.


### Simplify synthetic tool benchmark request and trial handling

Grouped endpoint/model/provider/context/timeout settings in an immutable request
record shared by selection and synthesis. Split tool-call validation and one
trial's result collection from CLI parsing and incremental report persistence.
Updated all four direct transport test callers to the new explicit interface.
Local Pylint no longer reports excessive request arguments, positional arguments,
main locals or main statements. The existing broad exception boundary remains
open: preserving failure-stage evidence and later trials needs separate review.

A transient comparison of sixteen provider/outcome combinations against the
preceding implementation confirmed identical trial results and ordered request
payloads, including wrong/missing tools, wrong namespaces, invalid arguments,
missing call identifiers and failures in selection or synthesis. Three permanent
offline tests cover both providers' valid fixture round trips, namespace refusal
without synthesis, and selection failure recording. Existing real urllib redirect
and sanitized-error tests, credential scoping and explicit timeout checks pass.
No model service, Kubernetes secret, external tool or network endpoint was used.

The full suite ran 453 tests successfully with 21 opt-in skips. The test module
passes full Pylint; Ruff and diff checks passed, and Bandit reported no analysis
errors. Source fixes await publication and genuine scanner refresh; no scanner
rule or validation gate was disabled.


### Separate NetworkPolicy graph aggregation and SVG drawing

Extracted peer-edge collection, referenced-node ordering, selector-node mapping,
inventory/graph legends, weighted curves and node-column rendering into focused
helpers. Shared node drawing retains direction-specific counters and fragment
ordering. Local Pylint no longer reports the five excessive-return/local/statement
warnings in the renderer; its existing context-detection broad-exception warning
remains open. No policy interpretation or graph ordering algorithm was changed.

Compared the preceding implementation with the refactor across 120 deterministic
snapshots spanning empty inventories, ingress/egress combinations, repeated peers,
self-links, namespace/pod selectors, Internet/CIDR peers, ports and XML-sensitive
labels. Sections, edge counts/directions, node ordering and complete SVG bytes
match exactly with the timestamp fixed. Three permanent offline tests cover
shared-direction aggregation and hidden self-links, special/referenced nodes,
well-formed escaped XML, weighted edge labels and empty inventory rendering.
No kubectl command or live cluster query was executed.

The full suite ran 456 tests successfully with 21 opt-in skips. The new regression
module passes full Pylint; Ruff and diff checks passed, and Bandit reported no
analysis errors. Publication and genuine scanner refresh remain necessary for
source-based alert closure. No scanner rule was disabled.


### Separate reviewed Kyverno exception contract validation

Split capability declaration validation, speaker identity/guard checks,
privileged-role cross-approval, init/application capability contracts and
companion guard constraints from CEL expression assembly. Validation order,
explicit failure checks and CEL term order remain intact. All four local Pylint
complexity warnings are gone; the generator now passes full Pylint checks.

The generator's --check confirms the checked-in exception YAML is byte-for-byte
current without regeneration. Comparing with the preceding implementation also
confirmed identical complete-catalog results and identical generated CEL or
failure type/message for 1,200 deterministic mutations of catalog scalar fields.
All seventeen existing scope tests passed, covering permission-init and six
application capability contracts, privileged runtimes, companion constraints,
image repository boundaries and the reviewed speaker identity. No exception
scope, generated manifest or live policy was changed; no Kubernetes call ran.

The full suite ran 456 tests successfully with 21 opt-in skips. Ruff and diff
checks passed. Because the generated policies are unchanged, this source-only
refactor does not establish any new admission or deployment behavior. Publication
and genuine scanner refresh remain necessary for remote alert closure.


### Close probe pipes and register class fixture cleanup before setup failures

The Mastodon media-cache check and isolated OpenBao TLS-reload probe now use
Popen contexts around their existing terminate/wait/kill finalizers. This keeps
the bounded shutdown behavior and also closes process-owned pipes when startup,
validation or normal execution exits. Their two local R1732 warnings are gone.
The TLS fixture log also specifies UTF-8 explicitly.

The static-asset and media-cache runtime suites now enter TemporaryDirectory
and server contexts through unittest.enterClassContext and register server
shutdown immediately after starting its thread. This covers allocation, bind
and config-read failures before the existing process-startup cleanup guard.
Class teardown still terminates child processes and closes logs; unittest then
shuts down/closes servers and removes temporary trees, including setup failures.
Pylint still reports the class-context allocations and class-owned child process
allocations; these warnings remain open for separate evidence-based review.

Three new offline regressions verify both suites remove their temporary tree
when server binding fails, the media origin shuts down/closes after early config
failure, and malformed forwarding output still terminates/waits and exits the
process context. All ten fixture-safety tests pass, as does full Pylint for that
regression module. The full suite ran 459 tests successfully with 21 opt-in skips.
Ruff and diff checks passed; Bandit reported no analysis errors. No process,
server, cluster command, external request or live workload was executed by these
mocked regressions. Publication and scanner refresh are still required.


### Pin system executables without disrupting the custom kubectl installation

Replaced seven implicit PATH lookups with explicit /usr/bin executable paths:
four Git calls in the manifest inventory/runtime-contract validators, OpenSSL
calls in signing-key validation and the isolated TLS fixture, and the network
report's systemctl service-health queries. Local inspection confirmed these
system tools exist at the selected paths. The network report remains standalone.
The affected source instances correspond to #7513, #7512, #7504, #7503, #7510,
#7500 and #7544; they await publication and scanner refresh rather than dismissal.
Kubectl remains unchanged because the operator intentionally uses a home/bin
installation; trusting a guessed system location would break legitimate use.

Two permanent regressions execute real read-only Git inventory commands and
invalid-public-key validation with hostile replacement executables as the entire
PATH. The inventories still return the actual tracked checkout, and a fake
successful OpenSSL cannot bypass invalid signing-key rejection. These tests use
only local files and system commands; no service, credential or cluster is read.

The full suite ran 461 tests successfully with 21 opt-in skips. The new regression
module passes full Pylint; Ruff and diff checks passed. Bandit B607 reports zero
findings and zero analysis errors across all five changed source modules and the
new regression module. Other subprocess audit findings remain open for separate
review; no scanner rule or validation gate was disabled.


### Separate streaming benchmark settings, state and metrics

Refactored the streaming benchmark's eight-argument request routine into immutable
request settings, explicit incremental output/timing state, provider-event
consumption and result metric assembly. The transport still owns the same
whole-request deadline and response context; interruption leaves the accumulated
state available for an incomplete result. Extracted API-key loading preserves
its existing behavior and does not print or persist credentials. Updated both
original direct request-test callers. All five original request complexity
warnings are gone; the existing broad per-trial failure boundary remains open.

Compared the previous implementation with the refactor across 120 deterministic
Ollama/OpenAI-compatible stream traces. Request URLs/headers/body bytes, timing
metrics and rates, content/reasoning, completion markers, failures and response
closure match exactly. Two permanent offline regressions prove a mid-stream
deadline retains partial text/reasoning and closes its response, and EOF/[DONE]
without a provider completion marker stays incomplete. Existing protocol,
redirect, credential, usage/native-metric and deadline regressions also pass.
No model service, Kubernetes secret, external tool or network endpoint was used.

The full suite ran 463 tests successfully with 21 opt-in skips. The regression
module passes full Pylint; Ruff and diff checks passed, and Bandit reported no
analysis errors. These source fixes still require publication and genuine
scanner refresh; no scanner rule or deadline behavior was weakened.


### Separate synthetic Sync storage authentication and lifecycle checks

Extracted tokenlib derivation/client creation, Hawk authorization, staged batch
validation and synthetic-user lifecycle checks from the Firefox Sync storage
probe. All four local complexity warnings are gone; the probe passes full Pylint.
The first collections read still refuses existing data before any write/delete.
The write-attempt flag remains set before PUT so ambiguous responses trigger
cleanup, and deletion is still followed by an empty-collections verification.

Compared the previous implementation with 119 mocked storage scenarios including
existing data, wrong reads, early batch visibility, failed commit, missing
collection timestamps, failed cleanup and injected transport failures at each
request. Hawk headers, exact requests/body bytes, storage state, output, failure
messages and response closure match. Three permanent offline regressions cover
existing-data refusal, ambiguous-write cleanup and unverified-cleanup failure.
Existing origin, redirect and sanitized-error tests also pass. No Kubernetes
secret, live storage user, external endpoint or production data was accessed.

The full suite ran 466 tests successfully with 21 opt-in skips. The updated
regression module passes full Pylint; Ruff and diff checks passed. Source-based
alert closure requires publication and genuine scanner refresh. A separate
fresh GitHub inventory now reports 365 open alerts; this local refactor has not
yet been credited as remote closure.


### Refresh Prospector and retain owner-reviewed password decisions

Dispatched the genuine Prospector-only workflow against published main c3e54059.
Run [43055665617](https://github.com/shaman007/home-k3s/actions/runs/43055665617)
completed successfully through analysis, guarded SARIF preparation and upload.
Its open count fell from 80 to 56; every remaining Prospector instance references
c3e54059. This reconciles the preceding refactors rather than replacing history
with an empty or incomplete report.

Re-reviewed thirteen recurring PyLintPython3_E5110 findings against their updated
c3e54059 instances. AST inspection of all 135 Python modules at that revision
found no Django imports. Individually dismissed these forced-plugin configuration
warnings as false positives with explanatory comments and reopening conditions:
8018, 8004, 8002, 8001, 8000, 7999, 7998, 7997, 7996, 7995, 7994, 7987, 7984.
An initial revision guard refused mutation when concurrent analysis advanced the
instances from 9f642572; the new revision was audited before applying decisions.

The repository owner explicitly reviewed all possible-hardcoded-password findings
and requested they be retained as won't fix. Applied that decision to all five
currently open instances: 7979, 7978, 7453, 7430 and 7429. Each comment records
owner acceptance and retains the decision for unchanged usage; reopen only if
the value becomes a live credential or its security context changes. This is a
standing decision for these reviewed values/usages, not a global suppression of
future hardcoded credentials. Earlier closed findings were left closed.

PATCH operations checked exact rule, path, revision and open state; returned
reasons/comments and independent inventories confirmed all eighteen dispositions.
The final API and code-scanning UI both report 314 open alerts: Bandit 130,
modern Pylint 103, Prospector 56 and Opengrep 25. No possible-hardcoded-password
or E5110 findings remain open. The preceding table snapshot was 365; the net
change combines genuine scanner reconciliation and exact reviewed decisions.
No code, scanner rule, cluster or live application was changed in this batch.


### Split backup/Collabora and Alloy runtime probe responsibilities

Separated disposable backup identity/container startup, SSH/rsync round-trip
verification and Collabora discovery/jail checks. Separated Alloy manifest/config
validation, volume allocation, synthetic fixture creation, receiver/Alloy startup,
Snappy delivery and runtime/checkpoint checks. Cleanup ownership stays in the
original outer try/finally scopes, including partially allocated resources.
Both probes now pass full Pylint; their six original complexity warnings are gone.

Compared both preceding implementations with eighty probe/failure scenarios.
Ordered command arguments/options, fixture bytes, outputs and exceptions matched,
including cleanup after injected command failures. Four permanent offline tests
cover backup removal after failed round-trip checks, Collabora removal after
failed discovery, Alloy volume removal after partial setup, and immediate
rejection of a writable root before checkpoint verification. Existing process
wrapper regressions still pass. No actual SSH, container, receiver, live workload
or external endpoint was used in these mocked comparisons or new regressions.

The full suite ran 470 tests successfully with 21 opt-in skips. Both probes and
the updated regression module pass full Pylint; Ruff and diff checks passed, and
Bandit reported no analysis errors. Publication and genuine scanner refresh are
still required for source-based alert closure. No scanner rule or guard was
removed, and the actual opt-in runtime probes were not executed.


### Review duplicate offline policy and monitoring subprocess findings

Individually reviewed seventeen Opengrep call sites in seven offline Kyverno and
promtool harnesses. Executables are explicitly selected by the operator/CI, not
an external service. Commands use fixed argv lists for version, local apply/test,
or rule check/test; none enables a shell or Kyverno cluster mode. Resource paths
refer to local generated fixtures. CI's Kyverno setup verifies the pinned archive
checksum. Comments require reopening if untrusted input or cluster mode is added.
Reviewed Opengrep IDs: 7977, 7976, 7975, 7971, 7970, 7969, 7968, 7627, 7625,
7624, 7623, 7620, 7618, 7617, 6901, 6900, 6899.

Matched the seventeen duplicate Bandit B603 warnings to the same exact AST call
sites. Audited every subprocess reference in each module before also classifying
its seven B404 imports: all launch references are the reviewed run/check_output
calls, with only an output constant otherwise referenced. No hidden alias or
additional launch API was accepted. Reviewed Bandit IDs: 7974, 7973, 7972, 7967,
7965, 7964, 7963, 7568, 7567, 7566, 7565, 7551, 7460, 7458, 7452, 7451, 7449,
7448, 7447, 7446, 6885, 6884, 6883, 4219.

All forty-one findings were dismissed as scoped false positives with individual
comments. Exact rule/path/revision/state guards refused concurrent instance
updates; the affected revisions were re-audited before completing the batch.
Returned reasons/comments and an independent inventory confirm all forty-one
are absent from the open set. Four unrelated Opengrep subprocess calls remain
open, as do other unreviewed Bandit launches/imports. No scanner rule was disabled.

Verified the installed Kyverno CLI is 1.19.2 and ran the actual local CEL harnesses
with KUBECONFIG=/dev/null: 92 component cases plus 16 idempotence checks,
36 recurring-job cases plus 28 idempotence checks, and 74 infrastructure guard
checks all passed. Five audit-fixture unit tests also passed. These commands
used local fixtures; no live-cluster mutation or credential access occurred.
No source changed, so the full unit suite was not repeated for this review.

The independently verified open count is now 267: Bandit 106, modern Pylint 97,
Prospector 56 and Opengrep 8. The change from 314 combines these forty-one exact
decisions with six newly reconciled Pylint source fixes from the paired probe
refactor. Further actionable findings and unresolved reviews remain.


### Split GPU/mail probe checks and close SMTP buffered streams

Separated GPU fixture creation, one-shot/default/fallback permission boundaries
and actual node-watch checks. Separated disposable mail certificate generation,
Dovecot/Postfix startup, IMAP/SMTP protocol checks and process-guard/reload checks.
Outer cleanup ownership still covers partially allocated containers and volumes.
Both probes pass full Pylint; their six original complexity warnings are gone.

Fixed a buffered-stream cleanup gap in the SMTP probe: ExitStack now closes each
socket and makefile wrapper even if greeting, STARTTLS or authentication fails.
The plaintext stream is still closed before TLS wrapping. The probe sends only
PROXY/EHLO/STARTTLS/AUTH/NOOP/QUIT, with no mail submission commands.

Ninety mocked old/new probe scenarios produced identical ordered commands,
fixture bytes, protocol sends, output and exceptions; resource closure is the
intentional improvement. Four permanent offline tests cover GPU permission and
missing-guard rejection with fixture removal, the successful no-mail SMTP
transcript, closure after greeting/authentication failures, and cleanup after
partial Postfix volume setup. The capability masks, sticky-bit check, read-only
INBOX selection, TLS verification, reloads and post-reload protocol checks remain.
No actual device, container, mail server, production secret or external endpoint
was used in these comparisons or regressions.

The full suite ran 474 tests successfully with 21 opt-in skips. Both source
modules and the updated regression module pass full Pylint; Ruff and diff checks
passed, and Bandit reported no analysis errors. The actual opt-in runtime probes
were not executed. Publication and genuine scanner refresh remain necessary for
source-based alert closure; no scanner rule or runtime guard was disabled.


### Separate infrastructure backfill contract, preflight and rollout checks

Extracted container/target environment contract checks, all-target preflight,
sequential rollout and exact-spec/continuous-readiness waiting from the large
backfill functions. The four complexity warnings are gone. The optional
storage_guard import remains lazy because the generated hook provides that
module and non-storage checks do not require it; its existing lint context
warnings remain open for separate review.

Expanding every extracted helper call reproduces the entire preceding module
AST exactly, preserving check order, retry limits, environment checks, admission
dry runs, resource-version patches, rollout deadlines and stability timing.
Regenerated the infrastructure bundle and compared parsed documents: only the
ConfigMap's embedded backfill.py changed. All other data, mutation policies,
RBAC, service accounts and job specifications are identical. The generator's
--check passes. No live hook or cluster mutation was executed.

Three new offline regressions prove unexpected spec drift stops later targets,
readiness lost after preflight blocks mutation, and readiness loss resets the
continuous fifteen-second stable window. Existing admission/storage/GPU refusal
checks pass. The full suite ran 477 tests successfully with 21 opt-in skips.
Selected Pylint style/correctness checks, Ruff and diff checks passed; Bandit
reported no analysis errors. Existing tiny mock-opener method-count warnings
were left unchanged. Publication and genuine scanner refresh remain necessary
for remote alert closure; no runtime guard or scanner rule was disabled.


### Review explicit system-command and isolated OpenBao subprocess findings

Individually reviewed fourteen exact alerts at scanned revision 4801d366. Seven
Bandit B603 sites use explicit system paths: four fixed read-only Git inventory
commands, one systemctl is-active query over the fixed suricata/ntopng/evebox
names, and two OpenSSL calls for public-key stdin validation or disposable
certificate generation. They use separate argv items without shell or PATH
lookup. The two real hostile-PATH regressions passed again, including refusal
of an invalid signing key despite a fake successful OpenSSL earlier in PATH.

The remaining launch is an explicitly operator-selected OpenBao fixture binary
with a fixed server/config argv, generated private in-memory storage and
loopback-only TLS listeners. It does not initialize or unseal production storage;
VAULT_/BAO_ environment variables are stripped. Its Bandit call warning and
Opengrep duplicate were reviewed together. Every subprocess reference in all
five modules was inspected before classifying their five B404 imports: no
additional launch functions, aliases or implicit shells were accepted.

Dismissed only these fourteen findings as scoped false positives with comments
and reopening conditions for executable/argument trust or added launch sites:
8017, 8016, 8015, 8014, 8013, 8012, 8011, 8005, 7611, 7545, 7517, 7509, 7502,
7499. Revision guards stopped an initial attempt when scanning advanced, and
the current revision was audited before applying decisions. Returned comments/
reasons and an independent inventory confirm all fourteen are absent from open.
No scanner rule or source file was changed, and the actual OpenBao fixture was
not executed. The full unit suite was not repeated for this decision-only batch.

The current independently verified total is 244 open alerts: Bandit 94, modern
Pylint 87, Prospector 56 and Opengrep 7. This includes ongoing source-scan
reconciliation as well as the fourteen exact decisions; unreviewed launches,
imports and other actionable findings remain open.


### Split audit-policy case generation and shard writing without reducing coverage

Separated sanitized workload preparation, deterministic variant naming, identity
and guard negatives, policy image/container/compliance variants, privileged and
hardened-root negatives, capability mutations, standalone smoke cases, input
validation and shard writing. All seven original harness complexity/nesting
warnings are gone. Extracted existing regression fixture-reading checks as well;
both the harness and its regression module now pass full Pylint.

Compared complete old/new case generation across six scenarios: forward/reversed
catalog order, catalog snapshots, actual workload snapshots and altered actual
security contexts/labels. All 9,996 ordered case tuples and expectation counts
matched, and caller inputs remained unchanged. All 489 files emitted for the
complete reviewed case corpus with fixed policy identifiers and checked-in
exceptions were byte-identical, including shard counts and applicable exception
scope. Independent AST checks also confirm unchanged CLI validation, complete
input loading and every subprocess command/options expression. No real CLI,
cluster query or policy deployment was executed for these comparisons.

Three new offline regressions cover separate Pod negatives, capability reordering
versus duplicate/moved-role refusal, and sanitization of actual workload images/
labels without copying unrelated environment or mutating the source. Existing
partition, shard-bound, exception-scope and noncompliant-container tests pass.
The full suite ran 480 tests successfully with 21 opt-in skips. Full Pylint,
Ruff and diff checks passed; Bandit reported no analysis errors. Publication and
genuine scanner refresh remain necessary for source-based alert closure. No
case, policy guard, scanner rule or failure gate was removed.


### Separate Longhorn component backfill checks and close HTTP failures

Extracted all-target preflight, sequential rollout, exact-spec/readiness waiting
and frontend verification. Rewrote readiness count conjunctions as equivalent
ordered all() checks. All five original local Pylint warnings are gone; the
component hook passes full Pylint. HTTPError responses are now closed before
the existing sanitized RuntimeError is raised, fixing a failure-path resource
leak without exposing response bodies or changing the public error message.

Expanding helper calls reproduces the preceding module AST except the two
intentional changes: readiness expression spelling and error.close(). Compared
18,000 Deployment/DaemonSet readiness combinations across desired counts,
generations, missing fields and mismatched counts; every result matches.
Regenerated both the component bundle and the infrastructure bundle that embeds
this module as storage_guard.py. Parsed-document comparisons prove only the
intended embedded script changes; policies, RBAC, jobs, catalog and other data
are identical. Both generator --check commands pass. No live hook was run.

Expanded the readiness regression to require every replica/scheduling counter
and reject zero desired workloads, and added an HTTP-failure regression proving
response closure plus unchanged sanitized output. Existing failed-preflight,
storage degradation and timeout/later-target refusal tests pass. Also removed
an existing test-local shadow of the patch helper. The full suite ran 481 tests
successfully with 21 opt-in skips. Selected Pylint checks, Ruff and diff checks
passed; Bandit reported no analysis errors. Existing small mock-opener method-
count warnings remain unchanged. Publication and genuine scanner refresh remain
necessary for remote alert closure; no safety gate or scanner rule was disabled.


### Simplify stateless test openers and retain framework callback interfaces

Replaced eight one-method stateless mock Opener classes across the component,
infrastructure and recurring-job backfill tests with named functions exposed
through SimpleNamespace.open. Their method bodies, request traces and mock
response behavior are unchanged. Reversing the adaptation reproduces each
previous test-module AST; one additional test-local patch variable rename is
normalized separately. Added the missing duplicate-key mapping-method docstring
in ci_yaml.py; AST comparison confirms no loader behavior change.

Separately reviewed seven exact framework-interface warnings. Both NoRedirect
redirect_request methods match HTTPRedirectHandler's complete standard-library
signature, so reducing their parameters would break the callback contract.
The three YAML extension classes directly inherit SafeLoader/SafeDumper APIs
and intentionally customize only mapping construction, alias handling or scoped
representation. Their inherited API is not reflected by the small-class rule.
Dismissed only #7735, #7734, #7670, #7669, #7653, #7249 and #6658 as false
positives with framework-specific comments and reopening conditions. Exact
revision/rule/path/state guards and independent inventory checks confirmed them.
The eight test-class warnings await real source rescanning rather than dismissal.

The full suite ran 481 tests successfully with 21 opt-in skips. Selected Pylint
checks, Ruff and diff checks passed; Bandit reported no analysis errors. Existing
YAML inheritance-depth and cross-module duplication heuristics were not disabled.
No live cluster, credential file or external API was used by the changed tests.
The independently verified current open total is 226: Bandit 94, modern Pylint
69, Prospector 56 and Opengrep 7. This combines ongoing source reconciliation
and the seven exact decisions; source fixes in this commit still need publication.
