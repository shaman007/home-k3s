# Harbor application configuration

`harbor.snapshot.yaml` records the non-secret configuration currently stored in
Harbor's database: OIDC/auth settings, registry endpoints, projects, retention
rules, scanner, and the absence of replication and immutable-tag policies. It
is a recovery snapshot and is not submitted to Kubernetes by Argo CD.

`../reconcile-proxy-caches.sh` is the executable bootstrap path for all eight
proxy-cache endpoint/project pairs. It creates missing objects and refuses to
silently change an endpoint whose URL or type differs. Project metadata and
retention rules remain documented in the snapshot and should be restored
through the Harbor API after the proxy projects exist.

Garbage collection runs daily at 01:00 UTC, one hour after retention. Restore
the `garbageCollection` settings through Administration > Clean Up > Garbage
Collection (Custom cron `0 0 1 * * *`). Both optional deletion switches remain
disabled. The next scheduled execution must be checked in GC History after
restoration; saving the schedule alone does not prove a scheduled run succeeded.

The database PVC `database-data-harbor-database-0` is explicitly managed by
`../persistent-volume-claim-harbor-database.yaml` at 5Gi. The Helm StatefulSet's
original 1Gi claim template is retained because that field is immutable; its
existing ordinal-0 PVC is expanded separately. Do not recreate the database or
shrink the PVC to match the old template.

Credentials, robot tokens, users, project memberships, image data, audit logs,
generated database IDs, and schedule run timestamps are intentionally absent.
Keep credentials in Vault and restore them separately.
