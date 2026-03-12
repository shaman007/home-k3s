## Install chart:

add

```
- name: common
  repository: oci://registry-1.docker.io/bitnamicharts
  version: 2.19.3
```
to che Chart.yaml and .lock

```
git clone https://github.com/mastodon/chart.git
cd Chart
helm dependency build
helm install --namespace mastodon mastodon ./ -f ../mastodon-values.yaml
```

## ArgoCD

The tracked Mastodon namespace manifests can be managed by ArgoCD with:

* `argocd/application-mastodon-custom.yaml`

The main Helm release cannot be cleanly moved to ArgoCD from this repository yet,
because the current chart lives under `mastodon/chart` and that path is ignored by
Git in `mastodon/.gitignore`.

That leaves two realistic paths:

* start tracking the current vendored chart in Git and let ArgoCD render it from the repo
* migrate to the newer official chart repo at `https://mastodon.github.io/helm-charts`

For now I recommend not switching charts yet. The newer official chart is promising,
but its published Mastodon release is still behind the `v4.5.6` app version running
here and requires a fuller values migration.
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
