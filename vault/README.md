# Vault (retired rollback source)

The Vault StatefulSet is intentionally pinned to zero replicas. Its two PVCs
remain retained as a rollback source; OpenBao is the production endpoint.

## Metrics

OpenBao metrics are exposed at `/v1/sys/metrics?format=prometheus`. Prometheus
scrapes `openbao-active.openbao.svc.cluster.local:8200` via
[`metrics/kubernetes-prometheus/config-map-prometheus-server-conf.yaml`](../metrics/kubernetes-prometheus/config-map-prometheus-server-conf.yaml).

## Dashboard

Grafana provisions a Vault overview dashboard from [`metrics/grafana/config-map-grafana-dashboard-vault-overview.yaml`](../metrics/grafana/config-map-grafana-dashboard-vault-overview.yaml).

## PKI Renewal

The compatibility-named [`cron-job-vault-pki-renewer.yaml`](./cron-job-vault-pki-renewer.yaml)
runs in the retained `vault` namespace but authenticates to OpenBao through the
`vault-pki-renewer` Kubernetes auth role. Its policy permits only the dedicated
Vault and OpenBao server-certificate issuance roles.

All renewal targets must be created before the job runs. The renewer has no Secret `create` or `list` permission: namespace Roles restrict it to `get`, `update`, and `patch` on these fixed names:

- `vault/vault-server-tls`

## PKI ACME

Internal ingress certificates use cert-manager with OpenBao's role-specific
ACME directory backed by the restored `w386-lab-intermediate` issuer. The
ClusterIssuer retains the compatibility name `vault-acme` but its server URL
points to `openbao.w386.k8s.my.lan`.

See [`docs/vault-acme-migration.md`](../docs/vault-acme-migration.md) for the
security restrictions, network paths, validation sequence, and completed
removal of the wildcard-copy targets.

## External Secrets Authentication

OpenBao-backed SecretStores retain the `vault-auth` ServiceAccount and role
names, but connect to `https://openbao.openbao.svc:8200`. The restored roles
issue 15-minute tokens with 30-minute maximum TTLs and attach the application
policy plus the minimal `external-secrets-token` lookup-self policy.

The legacy token rotator is suspended, has no RBAC permissions, and does not reference its former bootstrap token. Its stub resources remain temporarily so Argo CD can reconcile the previous objects without relying on pruning.
