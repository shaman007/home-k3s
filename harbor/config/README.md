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

Credentials, robot tokens, users, project memberships, image data, audit logs,
generated database IDs, and schedule run timestamps are intentionally absent.
Keep credentials in Vault and restore them separately.
