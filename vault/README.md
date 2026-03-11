# Vault

Controlled by Argo CD.

## Metrics

Vault metrics are exposed from the active Vault service at `/v1/sys/metrics?format=prometheus`.

The upstream chart telemetry is enabled in [`argocd/application-vault.yaml`](../argocd/application-vault.yaml), Prometheus scrapes `vault-active.vault.svc.cluster.local:8200` via [`metrics/kubernetes-prometheus/config-map-prometheus-server-conf.yaml`](../metrics/kubernetes-prometheus/config-map-prometheus-server-conf.yaml), and monitoring egress is opened in [`metrics/network-policy-monitoring-allow-egress-prometheus-scrape-targets.yaml`](../metrics/network-policy-monitoring-allow-egress-prometheus-scrape-targets.yaml).

## Dashboard

Grafana provisions a Vault overview dashboard from [`metrics/grafana/config-map-grafana-dashboard-vault-overview.yaml`](../metrics/grafana/config-map-grafana-dashboard-vault-overview.yaml).
