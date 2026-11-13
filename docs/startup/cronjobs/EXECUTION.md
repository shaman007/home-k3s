# Custom CronJob runtime verification — 2026-11-13

Published source: `90fc5ca3`. CI was not awaited. No Longhorn object, job,
endpoint or schedule was modified by this verification.

## Scoped authorization and changes

The user authorized one manual run of each of the seven custom jobs and a safe
skip diagnostic without application work or provider shutdown. Subsequent
explicit authorizations covered creating two missing report ConfigMaps,
removing only the failed first skip diagnostic, and media retry ConfigMaps/Jobs.
Native Mastodon Deployments and CronJob schedules were not patched.

All six affected Argo applications observed `90fc5ca3`. Nextcloud remains
Healthy/OutOfSync because of the pre-existing retired vault-pki-renewer Role and
RoleBinding; these were not deleted.

## Integration omissions found and fixed locally

* Report Jobs initially could not mount script ConfigMaps because explicit Argo
  source includes omitted them. Two immutable ConfigMaps from the published
  commit were created with user approval; include patterns and regression tests
  are corrected locally. These fixes still need publication.
* Media init kubectl defaulted to localhost:8080 despite projected credentials.
  An explicit in-cluster kubeconfig references the projected CA and tokenFile;
  no token value was exported or copied.
* Native web does not mount the init helper. The final media gate sends the same
  reviewed Ruby helper through stdin for the fixed read-only dependencies/schema
  modes. Both modes passed against live web in approximately 0.2 seconds.

## Evidence so far

| Job | Observed result |
| --- | --- |
| verify-gate-rspamd-spam-trainer | ready, Complete |
| verify-gate-mastodon-spam-list-sync | ready, Complete |
| verify-gate-nextcloud | ready, Complete |
| verify-gate-wordpress-daily-report | ready, Complete |
| verify-gate-external-access-daily-report | ready, Complete |
| verify-gate-logs-check | ready, Complete; all 114 Ollama batches and final report finished |
| verify-gate-bookmarked-media-sync | init skipped after bounded wait; uploader also skipped, Complete |
| verify-gate-bookmarked-retry | bounded skip in init and uploader, Complete; helper mount omission confirmed |
| verify-gate-bookmarked-final | both gates ready, Complete; 1611 files downloaded, descriptions updated on 1569 assets, 0 errors |
| verify-gate-skip-retry | skipped after 3.005 seconds; no main work invoked, Complete |

The first `monitoring/verify-gate-skip` expired before its container could start
because its ConfigMap was missing. It was not counted as a gate result, and only
that failed diagnostic Job was deleted with explicit user approval.

Local tests after the final source fix: 739 tests passed, 21 skipped. Python
lint, shell syntax, runtime contracts and Kubernetes resource schemas passed.
A Job marked Complete after skip does not prove its main work completed.

## Maintenance silences

Narrow `KubeJobFailed` silences match the exact test Job names and namespace;
no broad application or provider outage alerts were silenced. Initial expiry:
2026-11-13T21:38:24Z.

* mail: cbbab529-b780-463a-903b-cbe5959dd70e
* mastodon: e3e527ca-3856-4de2-8681-38b79b9ce7a0
* monitoring: 43261c07-2b7e-43f8-b934-9946f3a3c9f9
* wordpress: 6344e2af-db17-41d7-8384-9d56e2cabad2
* nextcloud: 09df3899-4d81-42f3-ac37-0a5b58371406
* intermediate media retry: 8075042d-2939-4b36-a859-0cd236967c3b,
  expiry 2026-11-13T21:33:55Z

Remove verification silences after verification/rollback. Retain script
ConfigMaps while referenced by existing CronJob or Job templates. Source fixes
must be published and adopted before claiming the scheduled media template is
fully operational.

Final media-run silence: `c854c789-999e-4737-a5b9-7c725bf0a36f`, expiry
2026-11-13T21:39:22Z. Silences for mail, mastodon initial jobs, WordPress,
Nextcloud and the intermediate media retry were removed after verification.
Only the monitoring test-name silence and final media-run silence remained
while those two ordinary workloads were running.

Scheduled Rspamd run `rspamd-spam-trainer-29910067` (21:07 UTC) and Nextcloud
run `nextcloud-29910075` (21:15 UTC) also passed ready and completed naturally.
The monitoring test silence was removed after logs-check completed.

## Final outcome

All seven ordinary custom jobs completed successfully. The first media variants
skipped rather than doing work; the final fixed variant completed the full
export/download/upload/description workflow. The dedicated safe skip diagnostic
completed after 3.005 seconds without main work. No provider was stopped.

All seven created maintenance silences were removed. Alertmanager reported zero
active verification silences and zero active alerts for verification Job names.
Native Mastodon web, Sidekiq and streaming retained the original Pod UIDs and had
zero restarts. Longhorn was not modified. CI was not awaited.

Git fixes remain local and uncommitted. In particular, the **scheduled media
CronJob still references the originally published wrapper** until the source fix
is committed/pushed and ArgoCD reconciles it. The successful final Job used the
explicitly approved fixed template, not a manual patch of the live CronJob.
Argo showed orphan warnings after the temporary manual creations (2 for
mastodon-custom; 4 for the monitoring applications). Publish/adopt the declared
ConfigMaps before reassessing those warnings; do not suppress warnings or delete
working resources. The successful standalone diagnostic Job has a 24-hour TTL.
Intermediate immutable script ConfigMaps are retained for existing Job history;
cleanup, if desired, is separate from this verification.

Final local validation: 739 tests passed (21 skipped), canonical generator check,
Python lint and shell syntax passed. The three affected Argo sources rendered
successfully with their dependency ConfigMaps; schema validation found 58 valid
ordinary Kubernetes resources, with 19 CRDs skipped, and no errors. Resource
policy checked 11 containers with no errors.

## Publication follow-up: 37c98bdd

Argo adopted the fixed report ConfigMaps and scheduled media CronJob now refers
to `bookmarked-media-sync-dependencies-4c425ff40291`. Mastodon orphan warnings
cleared. The two remaining monitoring orphans were exactly the successful
`verify-gate-skip-retry` Job and its Pod; the user explicitly authorized deleting
that diagnostic Job, and core-mode resource inspection confirmed no remaining
orphans for logs-check. Nextcloud retains its pre-existing retired PKI Role/
RoleBinding drift; no working resources were deleted.

CI follow-up: 37c98bdd CodeQL, Codacy Security Scan and pre-commit passed, but
Validate Kubernetes failed in the media shell fixture: replacing /work after
injecting a GitHub checkout path corrupted that host path. The isolated fix
reorders substitutions and always simulates a checkout path containing /work.
Positive/auth-denial cases use a 5-second fixture budget to avoid the sub-second
boundary of the production integer clock; the outage fixture remains bounded
at 1 second. This is a test-only correction, separate from the mail package.

The test-only CI correction passed all 739 baseline tests (21 skipped) from an
isolated checkout under a /work path, with mail changes excluded. Read-only Git
context was supplied for the three inventory tests that require repository
metadata; neither the source index nor refs were changed by validation.
