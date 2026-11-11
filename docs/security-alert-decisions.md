# Security alert decisions

This ledger distinguishes source fixes, reviewed exceptions and findings that
still need investigation. A local fix is not evidence that GitHub has closed an
alert. Do not dismiss an entire scanner's results as false positives.

## Inventory observed on 2026-11-11

GitHub's main-branch code-scanning UI reported 3,850 open alerts after the TLS
and workflow-action pinning changes. The authenticated CLI could not read the
alert API (HTTP 403), so this is a UI inventory, not an exhaustive API export.

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

Status: fixed in the worktree; deployment and GitHub rescan pending. Assertions
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
Secret documents are not included in the relevant diagnostics. GitHub dismissal
is pending authenticated API access.

The separate YAML parse-error path had a real disclosure risk: parser exceptions
can quote source snippets. It now reports only path, line and column and suppresses
the original exception chain. A regression checks the complete formatted traceback
for a malformed synthetic Secret, including the absence of its credential value.

## Remaining dispositions

CodeQL alert 3, shell findings, unverified TLS contexts, subprocess audit
findings and legacy correctness findings remain open for source-level review.
An unverified TLS exception is an accepted risk, not a false positive. A
subprocess call using `shell=False` is not automatically safe: validate the
executable and whether untrusted values can become command options or executable
code. Each retained exception must identify its scope, evidence, rationale and
condition for revisiting it.
