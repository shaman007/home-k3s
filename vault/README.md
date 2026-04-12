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
