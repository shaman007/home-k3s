# Codacy security scan

The Codacy workflow selects three source scanners explicitly: Bandit for Python
security checks, Opengrep for supported source languages, and ShellCheck for shell
scripts. Each runs independently with default rules, its own SARIF file, and a
stable GitHub code-scanning category. No Codacy project token is required, so rule
selection is consistent for pushes and fork pull requests.

Python 3 Pylint also runs on every normal push, pull request and scheduled scan.
Its successful manual run validated the analyzer and upload path before enabling
it here. It retains the historical category
`.github/workflows/codacy.yml:codacy-security-scan`, so source fixes refresh existing
lint findings instead of waiting for manual dispatch. The parser-error safeguard
also applies to this regular job. Style and correctness findings remain enabled.

An unrestricted run of Analysis CLI 7.9.25 attempted the full tool catalog. Trivy
failed without configured patterns, Reek required a configuration, and TSQLLint
crashed on a duplicate `set-ansi` key. Checkov also emitted `No specified files`
instead of JSON for some invocations. These tools are outside the selected scan;
this workflow does not provide dependency, container-image, or comprehensive
Kubernetes misconfiguration scanning. Kubernetes schema and repository policy
checks remain in the separate `Validate Kubernetes` workflow.

Keep `fail-if-incomplete: true` and the SARIF preparation step: analyzer failures
and missing reports must fail CI. Findings are uploaded to GitHub code scanning
without failing on their count; code-scanning rules control acceptance of findings.
Matrix fail-fast is disabled so one failed scanner does not cancel the others.

When adding a scanner, verify that it runs with default rules on this repository
and produces valid SARIF before adding it to the matrix. The action's supported
inputs are documented in its pinned
[action definition](https://github.com/codacy/codacy-analysis-cli-action/blob/562ee3e92b8e92df8b67e0a5ff8aa8e261919c08/action.yml).

Codacy CLI 7.9.25 can emit multiple batches for the same scanner (the failing
Opengrep run emitted five). GitHub no longer combines runs with the same tool and
category, so `tools/ci/prepare_codacy_sarif.py` combines the batches before upload.
It preserves results, fingerprints and invocations, deduplicates identical rule
definitions, and remaps rule and artifact indices into the combined tables.
Different driver metadata stays in separate runs. Missing runs, conflicting rules,
and unsupported run tables fail preparation rather than discard scan evidence.
This adapter targets the pinned Codacy formatter; review it when upgrading Codacy.
Regression tests cover the five-batch failure and reference preservation.

The rejection is described in GitHub's
[SARIF upload change](https://github.blog/changelog/2025-07-21-code-scanning-will-stop-combining-multiple-sarif-runs-uploaded-in-the-same-sarif-file/).

Codacy also emits `ruleIndex: -1` for findings whose pattern lacks a description,
and can use a non-security-local index in the combined rule list. Preparation
resolves results by `ruleId`, adds an ID-only descriptor if needed, and enriches
it if a later batch supplies metadata. Findings and fingerprints are retained;
an invalid index without a rule ID still fails.

The adapter reads the container-created report and writes a separate runner-owned
file in the checkout, which is the file passed to `upload-sarif`. The scanner
report can be read-only; preparation never overwrites it. The command-line
regression test covers this file-permission boundary as well as batch merging.

Codacy's `primaryLocationLineHash` is an issue hash, which conflicts with the
source-line hash calculated by GitHub's pinned uploader. Preparation moves the
original value to `result.properties["codacy.primaryLocationLineHash"]` and lets
the uploader calculate the matching fingerprint from the checked-out source.
Other fingerprint keys and every finding are preserved, including different rules
at the same location. Conflicting provenance fails preparation. This removes the
cause of the inconsistent-fingerprint annotations; GitHub alert reconciliation
must still be verified after a new upload. The uploader's behavior is defined in
[its pinned fingerprint implementation](https://github.com/github/codeql-action/blob/33d7b85da1a04171e211befe2c739303b9a4c066/src/fingerprints.ts#L159-L175).

Manual dispatch can select one supported historical linter with `legacy_tool`;
`none` retains the three security scanners plus Python 3 Pylint. Reports use their original
category so genuine rescans can supersede stale findings. These scans fail before
upload if either Pylint variant or Prospector reports a Python parser error,
preventing an incomplete analysis from replacing historical results. Prospector
uses a shared `Prospector_pylint` rule; its `(syntax-error)` diagnostic suffix is
checked as well as the dedicated Pylint rule IDs. Explicit failed SARIF
invocations are rejected for every scanner, including security tools, even when
the report contains no findings. Python 3 Pylint, Prospector and Remark have
completed genuine uploads and reconciled historical findings. PowerShell tooling
was retired at the user's request after moving off Windows; PSScriptAnalyzer is no
longer a dispatch option, and its four old findings have retirement comments; no empty reports or bulk dismissals substitute
for a scan.

The first manual Remark run
[43005823657, attempt 1](https://github.com/shaman007/home-k3s/actions/runs/43005823657/attempts/1)
successfully ran the analyzer but failed preparation: commit `86d41c16` published
only the workflow, whose new option was unavailable in its older adapter. Publish
the matching adapter and tests together before retrying on a new commit. No report
was uploaded by that failed attempt, and historical findings were retained.

Commit `6b30e257` subsequently published the matching adapter and regression tests.
[Push run 43006083625](https://github.com/shaman007/home-k3s/actions/runs/43006083625)
passed Bandit, Opengrep and ShellCheck with zero annotations on all three check
runs, verifying removal of the previously observed 20 fingerprint warnings.

The genuine legacy `pylint` diagnostic run
[43011027851](https://github.com/shaman007/home-k3s/actions/runs/43011027851)
on `f381f0a3` produced parser errors. The preparation safeguard rejected its report
and skipped upload, preserving all historical findings. All 127 current Python
files compile with the current interpreter, and the normal Python 3 lint run
[43010923234](https://github.com/shaman007/home-k3s/actions/runs/43010923234)
passed alongside Bandit, Opengrep and ShellCheck on that same revision.

The incompatible legacy `pylint` choice has therefore been removed from manual
dispatch. Use `pylintpython3` for supported Python linting. This does not delete or
dismiss any legacy alerts; their remaining source findings and overlap with the
current analyzer still need review. Parser-error rejection remains active, and
expected preparation failures now print a concise CLI error instead of a Python
traceback. Rerunning the old commit will still run its old workflow definition.
