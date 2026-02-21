## Keycloak Postgres Migration (db namespace -> keycloak namespace)

Dedicated Postgres for Keycloak is defined in:

* `keycloak/postgres-pvc.yaml`
* `keycloak/postgres-service.yaml`
* `keycloak/postgres-deployment.yaml`
* `keycloak/postgres-network-policy.yaml`

Key points:

* Uses plain PostgreSQL image: `harbor.andreybondarenko.com/dockerhub/postgres:18`
* No PostGIS extensions.
* Metrics are exposed by `postgres-exporter` sidecar on `keycloak-postgres-metrics:9187`.

Migration job template:

* `keycloak/tools/migrate-keycloak-db-job.yaml`

Suggested cutover order:

1. Wait until `keycloak-postgres` pod is ready.
2. Scale Keycloak down:
   `kubectl -n keycloak scale sts/keycloak --replicas=0`
3. Run migration:
   `kubectl apply -f keycloak/tools/migrate-keycloak-db-job.yaml`
4. Verify migration logs:
   `kubectl -n keycloak logs job/keycloak-postgres-migrate`
5. Apply Keycloak deployment/service manifest with updated DB host:
   `kubectl apply -f keycloak/keycloak-deplyoment.yaml`
6. Scale Keycloak up:
   `kubectl -n keycloak scale sts/keycloak --replicas=1`
