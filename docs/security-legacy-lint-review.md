# Legacy lint remediation inventory

Updated user decision (2026-11-11): mark confirmed stale findings as **won't fix**.
This supersedes the earlier decision to retain the entire historical inventory.
Current-source findings still require fixes or individually supported decisions.

The exact reviewed batch of **1,440 alerts** and its group comments are preserved
in the [approved historical snapshot](https://github.com/shaman007/home-k3s/blob/16e7083d90253082880085ffc93a48352dce5164/docs/security-stale-alerts.json).
The completed one-off JSON has been removed from the current tree at the user's
request; GitHub retains each alert's disposition and explanatory comment:

| Confirmed stale group | Alerts | Evidence |
| --- | ---: | --- |
| Retired legacy Pylint | 1396 | All from commit `2ff670f9b304`; incompatible engine retired; modern Pylint and CodeQL remain active |
| Retired standalone Ruby | 31 | Every alert references deleted Ruby source; no `.rb` files or RuboCop job remain |
| Retired Synapse SQL migration | 6 | Referenced migration file deleted; no `.sql` files or TSQLLint job remain |
| Other deleted historical sources | 7 | No current file or renamed counterpart; these are intentionally removed one-off tools |

All selected alerts originate from the same historical commit. Current scanner
findings, historical findings on retained code, and renamed-file counterparts
are excluded. No analysis history or scanner configuration is deleted.

Execution is complete: all 1,440 selected alerts were confirmed dismissed with
the approved reason and comment, and none remains in the open-alert set. The
per-group totals and evidence are retained in the table above and the historical
snapshot. On 2026-11-11, an independent API refresh again confirmed that zero
approved IDs remain open; the repository has 586 open findings overall.

The most recent completed local scan verifies zero missing-docstring, long-line,
naming, or unused-variable/import findings across 129 modules. A separate Ruff
spacing scan (`E2` rules) is also clean. The old style counts below are historical,
not evidence that those source defects still exist.

## Original inventory before remediation

These are formatting, docstring, naming, import-style and structural-complexity checks. They are part of the requested remediation scope, alongside correctness and security findings.

The table groups convention/refactor work only. Pylint error/warning reports and all Bandit, Opengrep, Shellcheck and unresolved security findings also remain in scope. The active security scanners and CI checks remain enabled. No analysis history is deleted.

| Rule | Alerts |
| --- | ---: |
| `PyLintPython3_C0103` | 56 |
| `PyLintPython3_C0114` | 42 |
| `PyLintPython3_C0115` | 45 |
| `PyLintPython3_C0116` | 356 |
| `PyLintPython3_C0301` | 341 |
| `PyLintPython3_C0321` | 84 |
| `PyLintPython3_C0327` | 1 |
| `PyLintPython3_C0410` | 2 |
| `PyLintPython3_C0415` | 5 |
| `PyLintPython3_R0201` | 10 |
| `PyLintPython3_R0801` | 3 |
| `PyLintPython3_R0903` | 2 |
| `PyLintPython3_R0911` | 2 |
| `PyLintPython3_R0912` | 9 |
| `PyLintPython3_R0913` | 7 |
| `PyLintPython3_R0914` | 17 |
| `PyLintPython3_R0915` | 8 |
| `PyLintPython3_R0916` | 3 |
| `PyLint_C0103` | 87 |
| `PyLint_C0111` | 440 |
| `PyLint_C0301` | 334 |
| `PyLint_C0321` | 84 |
| `PyLint_C0326` | 261 |
| `PyLint_C0327` | 1 |
| `PyLint_C0330` | 57 |
| `PyLint_C0410` | 2 |
| `PyLint_C0412` | 1 |
| `PyLint_R0201` | 10 |
| `PyLint_R0801` | 3 |
| `PyLint_R0903` | 2 |
| `PyLint_R0911` | 2 |
| `PyLint_R0912` | 8 |
| `PyLint_R0913` | 7 |
| `PyLint_R0914` | 16 |
| `PyLint_R0915` | 8 |
| `PyLint_R0916` | 3 |

Fix source files and verify behavior before claiming remediation. Current scanner results require a matching rescan to verify closure; source changes alone do not close retired scanner configurations. Confirmed retired configurations use the explicitly authorized stale-finding disposition above.
