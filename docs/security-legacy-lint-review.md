# Legacy lint remediation inventory

User decision: keep all 2,319 historical Pylint convention/refactor alerts open and fix them. No bulk dismissal is authorized.

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

Fix source files and verify behavior before claiming remediation. Historical scanner results require a matching rescan to verify closure; source changes alone do not close retired scanner configurations.
