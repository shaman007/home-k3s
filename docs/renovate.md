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
| Variable | `RENOVATE_APP_ID` | The App's numeric ID |
| Secret | `RENOVATE_APP_PRIVATE_KEY` | The App's complete PEM private key |

Enter the private key directly into the GitHub secret; never commit it or paste it
into a chat. The old `RENOVATE_TOKEN` secret is no longer used by this workflow.
Without App credentials the workflow fails before running Renovate.

## Verification and existing PRs

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

`platformAutomerge` is disabled so Renovate evaluates checks before merging,
instead of delegating the decision to GitHub's required-check configuration.
Keep the default test checking enabled; do not set `ignoreTests: true` or
`statusCheckNames: null`. The App still respects branch protections.

Merging happens during a Renovate run, not immediately when CI finishes. With
the current daily schedule, this can wait until the next scheduled run, or a
manual workflow dispatch. Renovate may rebase an outdated PR and wait for its CI
again; normally only one PR per target branch is automerged per run.

### One-off migration of legacy PRs

For the five existing PAT-authored PRs (#1108, #1109, #1111, #1112, #1113), run
the workflow manually with `migrate_legacy_prs` enabled. This enables
`ignorePrAuthor` for that run so the App can find the old account's PRs, and
passes their exact branch names through `checkedBranches` to request regeneration.
Scheduled runs and ordinary manual runs leave both migration settings disabled.

Review each PR for manual edits before using this option: forced regeneration
can discard branch edits and may select a newer dependency version. Verify all
commits in each resulting PR, including any historical merge commits, rather
than checking only its latest commit. Remove this migration option after the
five PRs have been migrated or closed.
