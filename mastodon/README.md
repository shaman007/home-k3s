## ArgoCD

Mastodon is split across two ArgoCD Applications:

* `argocd/application-mastodon.yaml`
* `argocd/application-mastodon-custom.yaml`

The main release uses a vendored copy of the official chart in
the upstream Mastodon Helm repository with values from
`mastodon/mastodon-values.yaml`.

The custom app keeps local infrastructure that is not owned by the upstream
chart: ExternalSecrets, dedicated Postgres, ingress, network policies, and the
bookmarked media sync job.

The upstream chart includes OIDC `existingSecret` support, so no local chart
fork is maintained here.

Mastodon's Redis-protocol endpoint is the application-local
`valkey.mastodon.svc.cluster.local` StatefulSet. The chart keeps its
`redis`, `REDIS_*`, and `mastodon-redis` configuration names because
Mastodon and the upstream chart use Redis-compatible terminology; these names
do not imply that a Redis server is still deployed.

# TODO

* Metrics + Dashboard

## Postgres Migration (db namespace -> mastodon namespace)

Dedicated PostgreSQL for Mastodon is defined in:

* `mastodon/postgres-pvc.yaml`
* `mastodon/postgres-service.yaml`
* `mastodon/postgres-deployment.yaml`
* `mastodon/postgres-network-policy.yaml`

Key points:

* Uses plain PostgreSQL image: `harbor.andreybondarenko.com/dockerhub/postgres:18`
* Metrics are exposed by `postgres-exporter` sidecar on `mastodon-postgres-metrics:9187`
* For large databases, migration runtime can be long; keep Mastodon scaled down during the copy

Migration job template:

* `mastodon/tools/migrate-mastodon-db-job.yaml`

Cutover order:

1. Wait for `mastodon-postgres` readiness.
2. Scale `mastodon-web`, `mastodon-sidekiq-all-queues`, `mastodon-streaming` to `0`.
3. Run migration job and wait for completion.
4. Update `mastodon-env` `DB_HOST` to `mastodon-postgres.mastodon.svc.cluster.local`.
5. Scale workloads back to `1`.

## Bookmarked media sync failures

The importer skips definite S3 404s. Other exhausted downloads fail the fetch
stage, and CLI installation, login, upload, bulk lookup and description update
errors fail the Job. Face-detection queueing remains best-effort because that API
requires additional privileges. A failed description update is reported after the
remaining updates have been attempted.

Each HEAD request has a 30-second total timeout. Downloads use three attempts by
default, each limited to 120 seconds, with a 15-second delay between attempts and
no nested curl retries (at most 420 seconds per object including HEAD). The Job's
3,300-second deadline remains the overall bound. API description requests have
60-second attempt timeouts and a bounded retry window. Kubernetes retries a failed
Job; duplicate uploads continue to use Immich's deduplication.

## Bookmarked media description tags

The exporter strips only exact, case-insensitive matches from the 101 selected
tags in `bookmarked-media-strip-tags.txt`. Other hashtags, including linked
names, retain their original spelling and hash. Ordinary links and mentions
continue to be removed. The list is embedded in the Ruby exporter in
`config-map-bookmarked-media-sync-scripts.yaml`; keep both lists in sync.
See `bookmarked-media-strip-tags-analysis.md` for selection and frequency counts.

## Registration spam lists

`config-map-spam-list-sync.yaml` and `cron-job-spam-list-sync.yaml` import
https://github.com/martinmuc/mastodon-spam-lists daily at 04:23 Europe/Prague.
The job uses the same Mastodon image, chart-generated `mastodon-env`, and
existing database/Redis secrets. Existing namespace network policies permit
HTTPS downloads, DNS, PostgreSQL, and Valkey; Kubernetes API access is disabled.
Keep the job image aligned with the web image when upgrading Mastodon.

The importer downloads the full domain list, MX list, and IP list before writes.
Mastodon's native `EmailDomainBlock` enforces domain/MX restrictions; its native
`IpBlock` uses `sign_up_block`, which restricts registration rather than general
access. Existing exact-match moderation records are preserved. The import does
not suspend accounts, delete users, or change federation rules. Mastodon's own
registration exceptions (such as valid invitations) still apply.

Two upstream MX entries are deliberately excluded: `smtp.google.com` is shared
legitimate mail infrastructure, and `communications` is not a fully qualified
domain. Other malformed entries, unexpectedly small/large lists, common protected
mail providers, private addresses, and overly broad CIDRs stop the entire import.
All database writes are transactional. A failed download retains existing rules.

IP rules owned by this importer have a 14-day expiry, renewed while listed.
Existing manual IP rules are never changed. Email/MX imports are additive because
Mastodon has no ownership/comment field for these records: upstream removals do
not automatically unblock a domain. Review removals manually in the admin UI.
The job logs newly created record IDs and aggregate counts, without user data.
For rollback, suspend the CronJob first and remove only its newly created records
using those IDs after checking for intervening moderation changes. Removing the
CronJob or ConfigMap alone does not remove imported database records.

For a read-only preview, run the embedded `sync.rb` with `bundle exec rails runner`
in the Mastodon web environment with `SPAM_LIST_APPLY=false` (the script default).
The scheduled job explicitly sets `SPAM_LIST_APPLY=true`. Deployment requires
approval under this repository's live-cluster change policy; neither manifest
has been deployed by this change. After activation, verify a completed import,
the native block records, and registration rejection for a listed domain while
an ordinary provider remains eligible. Do not send test confirmation mail to
third-party addresses.

Focused offline checks:
`python3 -m unittest discover -s tests -p test_mastodon_spam_list_sync.py -v`.
