# Renovate in GitHub Actions

The Renovate workflow uses a GitHub App installation token and GitHub API commits
(`RENOVATE_PLATFORM_COMMIT=enabled`) so GitHub signs the generated commits. Do not
set `gitAuthor` or `RENOVATE_GIT_AUTHOR`, or fall back to a personal access token.

## Required setup

Use a GitHub App that you own and install it only on `shaman007/home-k3s`.
An installation of the Mend-hosted Renovate App does not provide its private key
for this self-hosted workflow. Avoid running both bots against the same branches.

Configure the App's repository permissions according to the
[Renovate GitHub App documentation](https://docs.renovatebot.com/modules/platform/github/#running-as-a-github-app).
In particular, updating this repository's Actions requires Workflows write
permission in addition to Contents, Issues, and Pull requests write permissions.
Do not add the App to a branch-rule bypass list to solve signing errors.

Under repository Settings -> Secrets and variables -> Actions, add:

| Type | Name | Value |
| --- | --- | --- |
| Variable | `RENOVATE_CLIENT_ID` | The App's Client ID |
| Secret | `RENOVATE_APP_PRIVATE_KEY` | The App's complete PEM private key |

The workflow uses the token action's `client-id` input. Existing installations
can continue using the numeric `RENOVATE_APP_ID` variable as a fallback; set
`RENOVATE_CLIENT_ID` to migrate without interrupting scheduled runs.

Enter the private key directly into the GitHub secret; never commit it or paste it
into a chat. The old `RENOVATE_TOKEN` secret is no longer used by this workflow.
Without App credentials the workflow fails before running Renovate.

## Verification and existing PRs

Renovate runs with `LOG_LEVEL=debug` so failures such as `Error updating branch:
update failure` include the affected dependency/file and underlying error. A
successful workflow exit alone does not establish that every branch was updated.

Digest pinning for the `github-actions` manager is restricted to the `action`
and `workflow` dependency types, following Renovate's
[GitHub Action digest helper](https://docs.renovatebot.com/presets-helpers/#helperspingithubactiondigests).
The manager also extracts tool versions from action `with:` inputs as
`uses-with` dependencies. Helm, kubectl and Cosign inputs accept release versions,
not `version@commit` references. Applying `pinDigests` to these inputs caused the
`renovate/pin-dependencies` branch in dashboard #1118 to fail with `Digest is not
updated` for Helm. Tool version updates remain enabled; only action and reusable
workflow references receive commit pins.

The workflow sets `RENOVATE_DOCKER_MAX_PAGES=100`. GHCR caps Immich tag-list
responses at 1,000 entries per page even when Renovate requests 10,000. On
2026-11-11, the server's `v3.3.6` tag appeared on page 33 and `v3.4.0` on the
final page 34; Renovate's default 20-page limit missed both. This global setting
belongs in the workflow environment, rather than repository `renovate.json`.

After the configuration is published to `main` and the App credentials exist,
dispatch the Renovate workflow. Request rebase/retry on an existing Renovate PR
to regenerate its unsigned commit. Inspect the new commit on GitHub and confirm
that its signature is Verified, then check the PR's rules and CI results.

Switching from a personal account to an App changes the PR author identity.
Renovate may not adopt PRs created by the old account; confirm that the expected
PR was updated before relying on the migration. Avoid forcing regeneration of
branches containing manual edits without reviewing those edits first.

Signed commits satisfy the signature requirement; reviews, status checks, and
other branch protections still apply.

## Automerge

Minor and patch updates are eligible for PR automerge after CI passes. Major
updates and Argo CD minor/major upgrades still require manual merging.
Pin and digest-only updates are not included in the automerge rule.

`platformAutomerge` is enabled so Renovate asks GitHub to merge eligible PRs
when branch protections pass. Enable **Allow auto-merge** in repository settings
and require CI checks on `main` before publishing this configuration. Keep signed
commits required, and keep the default test checking enabled.

The required checks are `validate-manifests`, `pre-commit`, the three
`Codacy Security Scan` jobs (bandit, opengrep, shellcheck), the four CodeQL
`Analyze` jobs (actions, go, python, ruby), and the code-scanning results:
`CodeQL`, `Bandit (reported by Codacy)`, `Opengrep (reported by Codacy)`, and
`Shellcheck (reported by Codacy)`. `validate-manifests` aggregates input validation
and every Kyverno CEL matrix shard. Keep this list aligned with workflow changes.

Renovate must run once to enable native auto-merge on each eligible PR. After
that, GitHub can merge when required CI passes without another Renovate run.
The `main` protection does not require branches to be up to date, so one automatic
merge does not force every queued PR through another rebase/CI cycle. All 13 CI
checks and signed commits remain required. CI validates each PR's tested revision;
it does not necessarily cover integration with the latest `main`. No
branch-protection bypass is needed.
