# FOSSA license review

## Pylint 4.1.4 — reviewed 2026-11-17

The supplied FOSSA screenshots for revision `067c922` identify
`GPL-2.0-only`, `GPL-2.0-or-later` and `CC-BY-SA-4.0` findings in Pylint 4.1.4.
These findings can receive project/version-scoped exceptions for the usage
described below. This does not declare the upstream licenses incorrect or
approve them for every use.

### Verified usage boundary

- [CI requirements](../tools/ci/requirements-pylint.txt) pin Pylint 4.1.4.
- [Validate Kubernetes](../.github/workflows/validate-k8s.yml) installs those
  requirements and invokes `python -m pylint` as a separate code-checking tool.
- Repository inspection found no application imports of Pylint and no Dockerfile
  installation of the lint requirements. The [AIY image](../aiy-voice/Dockerfile)
  installs its separate [runtime lockfile](../aiy-voice/requirements.lock), which
  does not include Pylint, and copies selected application source files.

This is source/build-recipe evidence; no published image contents were inspected
as part of this review.

### GPL findings

[Pylint 4.1.4 metadata](https://pypi.org/project/pylint/4.1.4/)
declares `GPL-2.0-or-later`. FOSSA also reports `GPL-2.0-only`; the screenshots
do not expose its exact file matches, so this review does not reclassify that
finding or assume all package files have the same license.

Running Pylint to inspect this project's code does not by itself make that code
a derivative of Pylint or require changing the project's MIT license. GNU's
[GPL tools FAQ](https://www.gnu.org/licenses/gpl-faq.html#CanIUseGPLToolsForNF)
and [output FAQ](https://www.gnu.org/licenses/gpl-faq.html#GPLOutput) explain
the distinction between using a GPL tool and incorporating its code into an
output. Here Pylint is an independent lint command, not application code.

Suggested FOSSA reason for the two GPL findings:

> Pylint 4.1.4 is used as a standalone local/CI code-analysis tool. Repository
> build recipes do not include it in application runtime dependencies or images,
> and application code does not import it. Using this tool to check our source
> does not incorporate Pylint code into that source. Re-review on version,
> integration or distribution changes.

### CC-BY-SA-4.0 finding

The same upstream release description explicitly assigns CC-BY-SA-4.0 to
`doc/logo.png` and `doc/logo.svg`. These are Pylint documentation artwork,
not the project's application code. The inspected build recipes do not copy
these assets into application images. Confirm the FOSSA file matches are these
assets before applying this justification; other matches need their own review.

Suggested FOSSA reason:

> CC-BY-SA-4.0 applies to Pylint documentation logos (doc/logo.png and
> doc/logo.svg). Pylint 4.1.4 is used only as a local/CI lint tool; the inspected
> application build recipes do not include these assets. Re-review if the
> matched files, dependency version or distributed contents change.

### Exception scope and follow-up

Scope each exception to **home-k3s**, **Pylint 4.1.4**, and the individual
reviewed license finding. Do not ignore the whole dependency, suppress security
issues, or change the organization-wide license policy. `Denied` describes the
FOSSA policy result and does not alone establish a license violation.

Re-review on Pylint upgrades, different matched files, application imports,
custom Pylint integration, or redistribution of Pylint or its artwork. If those
components are redistributed, their applicable notice, source and artwork
license obligations must be assessed for that distribution.

This documentation update does not change FOSSA rules. The later supplied
screenshot shows four ignored issues and one active CC-BY-SA-4.0 issue, but does
not establish the scope/reasons of the existing ignores or subsequent status.
