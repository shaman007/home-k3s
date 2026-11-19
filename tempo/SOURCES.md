# Native tracing sources

Expansion prepared on 2026-11-19. Open WebUI alone has completed live acceptance
in `README.md`; the additional sources below require publication and live
verification. A rendered exporter configuration is not proof of received spans.

| Source | Transport to Tempo | Root sampling | Configuration |
| --- | --- | --- | --- |
| Open WebUI | OTLP HTTP 4318 | 100% pilot | deployment env, unchanged |
| Karakeep API/workers | OTLP HTTP 4318 | 10% | deployment env |
| Mastodon Ruby web/Sidekiq | OTLP HTTP 4318 | parent based 10% | main container env only |
| Keycloak | OTLP gRPC 4317 | parent based 10% | start flag and deployment env |
| Harbor core/jobservice/registryctl | OTLP HTTP 4318 | 10% | chart trace values |
| Traefik public/private/registry | OTLP HTTP 4318 | 10% | chart tracing values |
| Argo server/repo-server/application-controller | OTLP gRPC 4317 | parent based 10% | cmd parameters ConfigMap |
| Grafana | OTLP gRPC 4317 | 10% | server env; operational endpoints filtered |
| Prometheus | OTLP HTTP 4318 | 1% | `tracing` in prometheus.yaml |
| Thanos querier/store-gateway/receive/compactor | OTLP HTTP 4318 | parent based 1% | non-secret inline tracing config |
| Loki single binary | Jaeger compact UDP 6831 | 1% | legacy Jaeger env supported by bundled dskit |
| Kyverno admission/reports | OTLP gRPC 4317 | all | chart tracing values; existing controllers only |
| CoreDNS | Zipkin HTTP 9411 | one request per 1,000 | built-in trace plugin, Corefile reload |
| Synapse | Jaeger compact UDP 6831 | 10% | ExternalSecret config template; installed jaeger_client |

Parent sampling may retain more requests when an upstream sampled the trace.
Root sampling is not a per-service storage quota. Kyverno does not offer a
configurable sampler in this version: watch Tempo's ingestion rate, memory and
PVC growth after enabling it. Revisit collector sampling/capacity using measured
traffic; do not assume the original 5 GiB pilot can hold any workload for 24h.
Jaeger UDP has no end-to-end delivery acknowledgement; confirm stored traces.

The installed Loki dskit explicitly supplies an always-on sampler on its generic
OTEL path. Merely setting `OTEL_TRACES_SAMPLER_ARG` there would not bound traffic.
Its Jaeger path supports probabilistic sampling and is used instead.

CoreDNS, Argo and Kyverno currently have no egress isolation. Adding an Egress
policy solely for Tempo would newly isolate those pods and break unrelated
traffic. Preserve that behavior; restrict access at Tempo ingress. Add precise
trace-specific egress allows only to already isolated exporters. Each receiver
allow requires both source namespace and source pod labels. Tempo remains an
internal ClusterIP service without authentication or external ingress.

## Rollout and acceptance

Publish all changes through the normal Git workflow. Do not pause reconciliation
to preserve an unpublished rollout. Establish narrowly scoped expiring silences
for the workloads being rolled, expire them after success/rollback, and never
silence unrelated alerts. Deploy receiver configuration and network permissions
before actively verifying exporters.

Argo's cmd parameters are environment inputs: after their ConfigMap converges,
roll the server, repo-server and application-controller if they have not already
restarted. Do not restart Dex, Redis or disabled controllers for tracing.
Wait for Synapse's ExternalSecret to materialize the new template before its
restart; the mounted subPath config does not live-reload. CoreDNS has `reload`
and should pick up its Corefile without a forced rollout. Avoid concurrent
maintenance of CoreDNS, admission control, identity and the GitOps controller.

For each source, generate a safe real operation, find stored spans with the
expected service identity in Tempo and open a representative trace in Grafana.
Use read-only HTTP requests, DNS queries and normal Argo reconciliation; do not
publish Mastodon posts, delete artifacts/bookmarks or change policies as tests.
Background spans require actual background work; an idle worker is not an
export failure. Because requests are sampled, a single missing trace proves
neither broken export nor successful operation. Use bounded repeated probes or
the source's supported force-sampling request mechanism.

Confirm application responses, existing metrics/log delivery, receiver errors,
resource usage, and all affected Argo revisions/automation. Record which source
traces were actually observed; do not mark every source successful based only
on Ready pods or a service-name tag left over from an older test.

## Sources requiring additional work

OpenSearch has an experimental tracing feature, but the running image's plugin
inventory lacks `telemetry-otel`; enabling a flag alone would not provide it.
No image rebuild, new plugin installation, generic language agent injection,
or eBPF instrumentation is included here. Mastodon streaming is not covered by
the Ruby tracing integration. Native export was not established for the other
installed applications (including Immich, SeaweedFS, SearXNG and Ollama); existing
OpenTelemetry dependencies or metrics do not prove tracing support.

Version checks used deployed image tags, CoreDNS `-plugins`, Synapse's installed
Jaeger module, Argo server `--help`, the pinned Helm charts, and upstream source
for the installed Thanos, Loki and Grafana versions. Reference documentation:
[Karakeep](https://docs.karakeep.com/configuration/environment-variables/#monitoring),
[Mastodon](https://docs.joinmastodon.org/admin/config/#opentelemetry),
[Keycloak](https://www.keycloak.org/observability/tracing),
[Harbor](https://goharbor.io/docs/edge/administration/distributed-tracing/),
[Traefik](https://doc.traefik.io/traefik/observability/tracing/overview/),
[Argo CD](https://argo-cd.readthedocs.io/en/latest/operator-manual/observability/),
[Grafana](https://grafana.com/docs/grafana/latest/setup-grafana/configure-grafana/),
[Prometheus](https://prometheus.io/docs/prometheus/latest/configuration/configuration/#tracing_config),
[Thanos](https://thanos.io/tip/thanos/tracing.md/),
[Kyverno](https://kyverno.io/docs/guides/tracing/),
[CoreDNS](https://coredns.io/plugins/trace/),
[Synapse](https://element-hq.github.io/synapse/latest/usage/configuration/config_documentation.html#opentracing).
