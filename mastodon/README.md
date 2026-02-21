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
