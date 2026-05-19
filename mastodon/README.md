## ArgoCD

Mastodon is split across two ArgoCD Applications:

* `argocd/application-mastodon.yaml`
* `argocd/application-mastodon-custom.yaml`

The main release uses a vendored copy of the official chart in
`mastodon/helm-chart` with values from `mastodon/mastodon-values.yaml`.

The custom app keeps local infrastructure that is not owned by the upstream
chart: ExternalSecrets, dedicated Postgres, ingress, network policies, and the
bookmarked media sync job.

The vendored chart includes the OIDC existingSecret patch from upstream PR #34.

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
