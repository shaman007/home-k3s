# Synapse

Managed by ArgoCD.

## Metrics

Synapse metrics are enabled in [synapse-configmap.yaml](synapse-configmap.yaml) and exposed through [service-metrics.yaml](service-metrics.yaml).

Prometheus scrapes this endpoint through the existing `conduit` job in [`metrics/kubernetes-prometheus/config-map-prometheus-server-conf.yaml`](../metrics/kubernetes-prometheus/config-map-prometheus-server-conf.yaml).

## Dashboard

A Synapse dashboard snapshot already exists in [`metrics/grafana/dashboards/live/9f15576b-9cf6-4bfc-a3ab-bb95654d97c8-Synapse.json`](../metrics/grafana/dashboards/live/9f15576b-9cf6-4bfc-a3ab-bb95654d97c8-Synapse.json).
