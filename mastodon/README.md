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
