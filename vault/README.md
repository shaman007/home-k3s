# Vault

Controlled by Argo CD.

## Metrics

Vault metrics are exposed from the active Vault service at `/v1/sys/metrics?format=prometheus`.

The upstream chart telemetry is enabled in [`argocd/application-vault.yaml`](../argocd/application-vault.yaml), Prometheus scrapes `vault-active.vault.svc.cluster.local:8200` via [`metrics/kubernetes-prometheus/config-map-prometheus-server-conf.yaml`](../metrics/kubernetes-prometheus/config-map-prometheus-server-conf.yaml), and monitoring egress is opened in [`metrics/network-policy-monitoring-allow-egress-prometheus-scrape-targets.yaml`](../metrics/network-policy-monitoring-allow-egress-prometheus-scrape-targets.yaml).

## Dashboard

Grafana provisions a Vault overview dashboard from [`metrics/grafana/config-map-grafana-dashboard-vault-overview.yaml`](../metrics/grafana/config-map-grafana-dashboard-vault-overview.yaml).

## PKI Renewal

The Vault API/Raft TLS Secret is renewed by [`cron-job-vault-pki-renewer.yaml`](./cron-job-vault-pki-renewer.yaml).
The CronJob authenticates through the `vault-pki-renewer` Kubernetes auth role with a projected, audience-bound ServiceAccount token. Vault issues a 15-minute token with a 30-minute maximum TTL and the `vault-pki-renewer` policy.
The version-controlled [`policy-vault-pki-renewer.hcl`](./policy-vault-pki-renewer.hcl) grants only `pki-root/issue/vault-server`. Apply it with `vault policy write vault-pki-renewer vault/policy-vault-pki-renewer.hcl` after changes are reviewed.
The `vault-server-tls` certificate uses that role for the Vault API and Raft DNS names.

All renewal targets must be created before the job runs. The renewer has no Secret `create` or `list` permission: namespace Roles restrict it to `get`, `update`, and `patch` on these fixed names:

- `vault/vault-server-tls`

## PKI ACME

Internal ingress certificates use cert-manager with Vault's role-specific ACME
directory backed by the `w386-lab-intermediate` issuer. All application and
Vault ingress certificates have migrated. The legacy ingress Secrets remain
temporarily as rollback artifacts but are no longer renewed or writable by the
renewer ServiceAccount.

See [`docs/vault-acme-migration.md`](../docs/vault-acme-migration.md) for the
security restrictions, network paths, validation sequence, and completed
removal of the wildcard-copy targets.

## External Secrets Authentication

Vault-backed SecretStores authenticate through namespace-bound `vault-auth` ServiceAccounts and Vault Kubernetes auth roles. The roles issue 15-minute tokens with 30-minute maximum TTLs and attach the application policy plus the minimal `external-secrets-token` lookup-self policy.

The legacy token rotator is suspended, has no RBAC permissions, and does not reference its former bootstrap token. Its stub resources remain temporarily so Argo CD can reconcile the previous objects without relying on pruning.
