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
