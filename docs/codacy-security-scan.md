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

Keep `fail-if-incomplete: true` and the nonempty SARIF-run check: analyzer failures
and missing reports must fail CI. Findings are uploaded to GitHub code scanning
without failing on their count; code-scanning rules control acceptance of findings.
Matrix fail-fast is disabled so one failed scanner does not cancel the others.

When adding a scanner, verify that it runs with default rules on this repository
and produces valid SARIF before adding it to the matrix. The action's supported
inputs are documented in its pinned
[action definition](https://github.com/codacy/codacy-analysis-cli-action/blob/562ee3e92b8e92df8b67e0a5ff8aa8e261919c08/action.yml).
