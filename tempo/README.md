# Tempo pilot: Open WebUI

One Tempo 3.1.1 process runs in `monitoring`, with a 5 GiB Longhorn PVC and
24-hour block retention. This is a single-instance pilot, not an HA tracing
service. Retention runs asynchronously; the PVC is a capacity limit, not a
guarantee that 24 hours always fit. No Kafka, collector, metrics generator
processors, external ingress, or new credentials are required.

Open WebUI exports OTLP/HTTP to `tempo.monitoring.svc.cluster.local:4318/v1/traces`.
Its existing metrics endpoint remains Prometheus. Application requests are fully
sampled for the pilot; `/health` probes are excluded. OTEL logs remain disabled.
Grafana provisions the `Tempo` datasource with stable UID `tempo` and URL
`http://tempo.monitoring.svc.cluster.local:3200`.

The Tempo ingress policy admits only Open WebUI on 4318 and Grafana on 3200.
The broad monitoring intra-namespace ingress/egress policies exclude Tempo;
namespace DNS access remains available. Tempo's internal components communicate
in the same process. Do not expose its unauthenticated API through an ingress.

## Deployment and acceptance

Publish the complete change through the normal authorized Git workflow first.
The parent Argo application discovers `argocd/application-tempo.yaml`; `tempo`,
`monitoring-network-policy`, `grafana`, and `open-webui` reconcile from `main`.
Do not leave Argo reconciliation paused to preserve an unpublished deployment.
Open WebUI uses Recreate and Grafana's datasource ConfigMap triggers reloader;
both can briefly be unavailable during rollout. Create narrow, expiring
maintenance silences for those workloads, then remove them after verification.

Acceptance requires all of the following, not just Ready pods:

1. Tempo `/ready` succeeds and Open WebUI has no OTLP export errors.
2. Send an authenticated request through Open WebUI to a configured local model.
   Use a harmless test prompt and a unique W3C `traceparent` ID. Do not persist
   credentials, request bodies, or raw trace payloads in the repository.
3. Retrieve that exact trace through Grafana's `tempo` datasource proxy and
   verify `service.name=open-webui`, the application server span, and nested
   database/outbound HTTP spans. Confirm a successful model response.
4. Open that trace in Grafana Explore and verify the span waterfall is rendered.
   An outgoing Ollama span measures the client request, not internal GPU stages.
5. Confirm the existing Open WebUI OTLP metrics continue arriving, all affected
   Argo applications reconcile, and maintenance silences are removed.

The local Open WebUI instrumentation records SQL statements and HTTP URLs;
trace readers may therefore see application metadata. Keep access through the
existing authenticated Grafana instance. Inspect test traces without printing
SQL parameters, headers, user identifiers, or request content.

## Rollback

Disable `ENABLE_OTEL_TRACES` in the Open WebUI manifest and publish/reconcile it
before removing the datasource or stopping Tempo. Remove only the tracing
exporter settings and trace-specific network policy; preserve the existing
metrics exporter configuration. Keep the Tempo PVC unless its deletion has
been explicitly authorized. Publish/reconcile rollback through Git, and verify
the model request and metric freshness again.

## Preparation validation

The official Tempo 3.1.1 Linux binary, verified against its release SHA256SUMS,
accepts the embedded configuration with `-config.verify=true`. Kubernetes
manifests pass strict kubeconform validation for Kubernetes 1.37.1. The Argo
Application is checked against the installed Application CRD schema.

Live rollout and trace acceptance results are recorded after execution; these
local checks do not establish ingestion or Grafana rendering.
