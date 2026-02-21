# Dawarich Postgres Migration (db namespace -> dawarich namespace)

Dedicated PostGIS for Dawarich is defined in:

* `dawarich/postgres-pvc.yaml`
* `dawarich/postgres-service.yaml`
* `dawarich/postgres-deployment.yaml`
* `dawarich/postgres-network-policy.yaml`

Key points:

* Uses PostGIS image as required: `harbor.andreybondarenko.com/github/cloudnative-pg/postgis:17`
* Metrics are exposed by `postgres-exporter` sidecar on `dawarich-postgres-metrics:9187`.

Migration job template:

* `dawarich/tools/migrate-dawarich-db-job.yaml`

Suggested cutover order:

1. Wait until `dawarich-postgres` pod is ready.
2. Scale Dawarich deployment down:
   `kubectl -n dawarich scale deploy/dawarich --replicas=0`
3. Run migration:
   `kubectl apply -f dawarich/tools/migrate-dawarich-db-job.yaml`
4. Verify migration logs:
   `kubectl -n dawarich logs job/dawarich-postgres-migrate`
5. Apply deployment with updated DB host:
   `kubectl apply -f dawarich/dawarich-deploy.yaml`
6. Scale Dawarich back:
   `kubectl -n dawarich scale deploy/dawarich --replicas=1`
