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

These local checks alone do not establish ingestion or Grafana rendering.

## Pilot acceptance: 2026-11-19

Deployed revision `883a5f1f095989e03bdcb14355bfbf2a73f8b343`. The `tempo`,
`open-webui`, `grafana`, and `monitoring-network-policy` applications passed
`tools/ops/verify.py argocd` with that exact revision: Healthy, Synced, unpaused,
and normal automation enabled. Tempo was Ready with its 5 GiB PVC Bound;
the running process reported `target: all` and 24-hour retention. Its observed
pilot footprint was about 80 MiB memory and 6 millicores, not a sizing guarantee.

An authenticated request from the Open WebUI browser UI, in a temporary chat,
used local model `qwen2.5:1.5b` and returned the requested `TEMPO_OK` response.
The successful `/api/chat/completions` request has trace ID
`da30d429ac35a7ec5e15e59c021f06c9`. Tempo returned 31 spans with
`service.name=open-webui`, including 24 SQLite connection spans and two HTTP 200
calls to `ollama-small` `/api/chat` (about 3.30 s and 327 ms).

Grafana's provisioned datasource health returned `Data source is working`.
The exact trace rendered in Grafana Explore with the span waterfall and a total
duration of 3.74 s. Its default span pruning grouped the 24 connection spans,
displaying eight rows; this does not mean the original spans were lost.

The streaming endpoint's server span lasted only 16.49 ms, while its child
Ollama calls continued afterward. This is an instrumentation boundary: use the
whole trace and HTTP client spans for this workflow, not the server span alone
as the model response duration. No internal model/GPU spans were established.

Existing HTTP and user-count OTLP metrics had samples about 27 seconds old
with the configured 30-second export interval. No trace-export errors were found
in the inspected post-rollout logs. A metrics-view conflict warning was observed;
the existing dashboard metrics still arrived. Startup branding-file warnings
from the read-only root filesystem are unrelated to trace delivery.

The two narrowly scoped maintenance silences were explicitly expired after
verification: `d9a94ceb-4b26-4a4a-a85b-23d4c77423e3` (Open WebUI) and
`4453336b-1a20-41bf-b8de-9b49ebba0243` (Grafana). Their initial expiry was
2026-11-19 12:35 Europe/Prague. No relevant active unsilenced alerts remained.
Reconciliation was never paused. Persistence across a Tempo restart and actual
24-hour retention expiry have not been tested by this acceptance run.
