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
