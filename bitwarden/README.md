# Self-hosted Bitwarden instance

* Documentation: https://bitwarden.com/help/self-host-an-organization/ and https://bitwarden.com/help/install-and-deploy-unified-beta/
* Works extremely unstable with MySQL database as the backend! Use Postgresql!


# TODO

* R/O filesystem
* Make it run not from root (own Dockerfile?)

# Observability

Bitwarden app has no native metrics to export/collect.
Postgres metrics are exposed by the `postgres-exporter` sidecar on `bitwarden-postgres-metrics:9187`.

# Postgres Migration (db namespace -> bitwarden namespace)

Dedicated Postgres for Bitwarden is defined in:

* `bitwarden/postgres-pvc.yaml`
* `bitwarden/postgres-service.yaml`
* `bitwarden/postgres-deployment.yaml`
* `bitwarden/postgres-network-policy.yaml`

Bitwarden now points to:

* `bitwarden-postgres.bitwarden.svc.cluster.local`

Migration job template:

* `bitwarden/tools/migrate-bitwarden-db-job.yaml`

Suggested cutover order:

0. If Argo auto-sync is enabled for Bitwarden, pause auto-sync (or pre-scale deployment to 0) before syncing DB host switch.
1. Wait until `bitwarden-postgres` pod is ready.
2. Stop writes by scaling Bitwarden down:
   `kubectl -n bitwarden scale deploy/bitwarden --replicas=0`
3. Run migration:
   `kubectl apply -f bitwarden/tools/migrate-bitwarden-db-job.yaml`
4. Verify migration job completed successfully:
   `kubectl -n bitwarden logs job/bitwarden-postgres-migrate`
5. Start Bitwarden:
   `kubectl -n bitwarden scale deploy/bitwarden --replicas=1`
6. Validate login, vault unlock, and new writes.
