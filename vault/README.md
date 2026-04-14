# Vault

Controlled by Argo CD.

## Metrics

Vault metrics are exposed from the active Vault service at `/v1/sys/metrics?format=prometheus`.

The upstream chart telemetry is enabled in [`argocd/application-vault.yaml`](../argocd/application-vault.yaml), Prometheus scrapes `vault-active.vault.svc.cluster.local:8200` via [`metrics/kubernetes-prometheus/config-map-prometheus-server-conf.yaml`](../metrics/kubernetes-prometheus/config-map-prometheus-server-conf.yaml), and monitoring egress is opened in [`metrics/network-policy-monitoring-allow-egress-prometheus-scrape-targets.yaml`](../metrics/network-policy-monitoring-allow-egress-prometheus-scrape-targets.yaml).

## Dashboard

Grafana provisions a Vault overview dashboard from [`metrics/grafana/config-map-grafana-dashboard-vault-overview.yaml`](../metrics/grafana/config-map-grafana-dashboard-vault-overview.yaml).

## PKI Renewal

Internal ingress TLS secrets are renewed by [`cron-job-vault-pki-renewer.yaml`](./cron-job-vault-pki-renewer.yaml).
The CronJob expects a `vault-pki-renewer-token` secret in the `vault` namespace with a `token` key bound to a periodic Vault policy that can renew itself and issue `pki-root/issue/w386-k8s-my-lan-wildcard` plus `pki-root/issue/vault-ingress`.

## Token Rotation

Vault-backed External Secrets tokens are rotated by [`cron-job-vault-token-rotator.yaml`](./cron-job-vault-token-rotator.yaml).
The CronJob connects to `vault-active.vault.svc:8200` and expects a `vault-token-rotator-token` secret in the `vault` namespace with a `token` key that can:

- read and write `sys/policies/acl/external-secrets-token`
- look up and create tokens under `auth/token/*`

The job discovers Vault-backed `SecretStore` and `ClusterSecretStore` resources, reuses the current non-default token policies, appends a shared `external-secrets-token` policy for `auth/token/lookup-self`, and patches the referenced Kubernetes secret when the token is within the renewal window.
If a token is already invalid, the job skips it unless the store declares a `vault.w386.k8s.my.lan/token-policies` annotation with a comma-separated policy list that can be used for recovery.
