# Codacy security scan

The Codacy workflow selects three source scanners explicitly: Bandit for Python
security checks, Opengrep for supported source languages, and ShellCheck for shell
scripts. Each runs independently with default rules, its own SARIF file, and a
stable GitHub code-scanning category. No Codacy project token is required, so rule
selection is consistent for pushes and fork pull requests.

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
category, so `tools/ci/prepare-codacy-sarif.py` combines the batches before upload.
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

Manual dispatch can select one historical linter with `legacy_tool`; `none`
retains the normal three security scanners. Historical reports use their original
category so genuine rescans can supersede stale findings. These scans fail before
upload if either Pylint variant reports a parser error, preventing an incomplete
analysis from replacing historical results. Tool availability and successful
historical reconciliation remain to be verified in Actions; no empty reports or
bulk dismissals substitute for a scan.
