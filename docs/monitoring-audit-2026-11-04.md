# Monitoring audit — 2026-11-04

## Scope and observed state

Live audit: 92 Argo CD applications, 145 Deployment/StatefulSet/DaemonSet objects, 85 active Prometheus targets (all up), 52 scrape jobs, 6,563 collected metric names, two Grafana datasources and 35 dashboards. All Argo applications were Healthy/Synced at capture. These are point-in-time observations, not deployment results. CronJobs and externally hosted services are distinguished below.

Grafana 13.3.0 reported a healthy database. Grafana-managed alert rule inventory is empty; alerting is managed by Prometheus (21 rules, all inactive and evaluating successfully). Successful evaluation does not establish meaningful coverage: two OpenBao rules select an obsolete job/metric. Notification delivery was not tested.

## Implemented change set

- Enable cert-manager metrics, Cilium agent metrics, Headlamp telemetry, Immich API/worker telemetry, snapshot-controller metrics and Open WebUI native HTTP metrics. Open WebUI exports OTLP/HTTP to Prometheus every 30 seconds; tracing and OTLP logging are explicitly disabled, and pod identity distinguishes exporter instances.
- Add 21 scrape jobs for External Secrets, Kyverno, Headlamp, Mastodon, Reloader, Argo repo-server/notifications, Alloy, Alertmanager, the Prometheus Thanos sidecar, Immich, MetalLB/FRR, Meilisearch, Firefox Sync, Metrics Server, snapshot-controller, node-feature-discovery, Longhorn CSI controllers, Hister, Spotify and WordPress Valkey. Per-pod discovery retains replica identity; notifications uses its existing service because its container declares no metrics port.
- Keep dedicated Traefik and Prometheus jobs and drop their redundant generic pod/service discovery targets.
- Extend Prometheus egress and target ingress for the needed ports, including Cilium host/remote-node permissions. Add the Argo ingress policy to its Kustomization.
- Provision thirteen dashboards: Application Workloads, Metrics Collection, GPU Overview, Cluster Network Metrics, Platform Controller Metrics, Database and Storage Metrics, Firefox Sync Metrics, Mastodon Application Metrics, Immich Application Metrics Meilisearch Metrics, Open WebUI Metrics, Hister Metrics and Your Spotify Metrics. The workload dashboard supplies shared resource coverage, not native business metrics, for workloads lacking an exporter.
- Repair Vault Overview using job=openbao, vault_core_unsealed and vault_core_active; replace a nonexistent generic route counter with the observed KV-read counter. Repair MySQL/SeaweedFS datasource bindings while preserving live UIDs. Replace the MySQL buffer-pool/host-RAM comparison, whose instance labels cannot join, with buffer-pool used percentage.
- Preserve every Prometheus alert rule byte-for-byte. Alert suggestions below are documentation only.

MetalLB controller/speaker and both FRR endpoints were checked through temporary port forwards. They require HTTPS and authentication; the existing Prometheus service-account credential successfully read all four exporters. The staged job keeps bearer authentication and follows the pinned upstream chart default for ephemeral self-signed metrics certificates (`insecure_skip_verify: true`). No credentials were persisted.

The initial Mastodon exporter exposed only five ruby_collector metric families because application instrumentation was disabled. Enable the chart-equivalent web and Sidekiq environment flags while retaining the custom exporter and its uncapped CPU configuration. Select one web/embedded Sidekiq exporter per pod, including Sidekiq pods that do not declare a metrics container port. Immich, Headlamp, Cilium-agent, cert-manager, Mastodon web/Sidekiq, Firefox Sync and Meilisearch metrics were subsequently verified live. The first complete application scrape capture had 134 targets, all up.

## Every installed Argo application

Configuration-only applications inherit the owning component assessment; they are not independently running services. A missing native exporter is explicitly distinguished from existing infrastructure/database coverage. Dashboard names introduced by this change are provisioned through the GitOps rollout.

| Application | Namespace | Source | Metrics assessment | Dashboard coverage |
|---|---|---|---|---|
| alloy | monitoring | `loki/alloy` | Exporter verified; collected and verified | Metrics Collection |
| argocd-applications | argocd | `argocd` | Configuration for argocd-install; Controller/server/ApplicationSet collected; repo/notifications collected and verified | ArgoCD; Metrics Collection |
| argocd-deploy | argocd | `argocd-deploy` | Configuration for argocd-install; Controller/server/ApplicationSet collected; repo/notifications collected and verified | ArgoCD; Metrics Collection |
| argocd-install | argocd | `argocd-install` | Controller/server/ApplicationSet collected; repo/notifications collected and verified | ArgoCD; Metrics Collection |
| backup-rsync | backup-rsync | `backup-rsync` | No app exporter configured; CronJob/workload coverage | Application Workloads |
| bastioncam | bastioncam | `bastioncam` | No app exporter configured | Application Workloads |
| bitwarden | bitwarden | `bitwarden` | PostgreSQL collected; web app uses workload coverage | PostgreSQL Database; Database and Storage Metrics |
| ca-scanner | ca-scanner | `canitiser` | No app exporter configured; job coverage | Application Workloads |
| cert-manager | cert-manager | `chart:cert-manager, cert-manager` | Metrics disabled; enabled and collected | Platform Controller Metrics |
| cilium | kube-system | `chart:cilium, chart:values` | Operator/Envoy/Hubble collected; agent disabled, enabled and collected | Cluster Network Metrics |
| clamav | clamav | `clamav` | Collected | ClamAV Exporter |
| collabora | nextcloud | `chart:collabora-online` | Collected | Libreoffice Collabora |
| comfyui | comfyui | `comfyui` | No app exporter configured; GPU metrics collected | Application Workloads; GPU Overview |
| connectivity-exporter-core | connectivity-exporter | `connectivity-exporter` | Collected | Platform Health; Metrics Collection |
| connectivity-exporter-network-policy | connectivity-exporter | `connectivity-exporter` | Configuration for connectivity-exporter-core; Collected | Platform Health; Metrics Collection |
| convertx | convertx | `convertx` | No app exporter configured | Application Workloads |
| coredns-custom | kube-system | `kube-system/coredns-custom` | Configuration for cilium; Operator/Envoy/Hubble collected; agent disabled, enabled and collected | Cluster Network Metrics |
| crowdsec | crowdsec | `chart:crowdsec, chart:values` | Collected | CrowdSec |
| crowdsec-config | crowdsec | `crowdsec` | Configuration for crowdsec; Collected | CrowdSec |
| dawarich | dawarich | `dawarich` | PostgreSQL/Valkey collected; Rails app uses workload coverage | Database and Storage Metrics; Application Workloads |
| element | matrix | `synapse` | Synapse collected; frontend uses workload coverage | Synapse; Application Workloads |
| external-access-analytics | monitoring | `metrics` | Collected | External Access Analytics |
| external-secrets | external-secrets | `chart:external-secrets` | All three component exporters verified; collected and verified | Platform Controller Metrics |
| external-secrets-network-policy | external-secrets | `external-secrets` | Configuration for external-secrets; All three component exporters verified; collected and verified | Platform Controller Metrics |
| finance-ticker | monitoring | `metrics` | Collected | Finance Ticker |
| firefox-sync | firefox-sync | `firefox-sync` | Local StatsD bridge and Prometheus collection prepared | Application Workloads |
| gpu-operator | gpu-operator | `chart:gpu-operator` | Operator and DCGM collected | GPU Overview |
| grafana | monitoring | `metrics/grafana` | Collected | Grafana metrics; Metrics Collection |
| harbor | harbor | `chart:harbor` | Core/jobservice/registry/exporter collected | Harbor Overview |
| harbor-custom | harbor | `harbor` | Configuration for harbor; Core/jobservice/registry/exporter collected | Harbor Overview |
| harbor-network-policy | harbor | `harbor` | Configuration for harbor; Core/jobservice/registry/exporter collected | Harbor Overview |
| headlamp | headlamp | `headlamp` | Metrics flag disabled; enablement and actual HTTP port 4466 staged | Platform Controller Metrics; Application Workloads |
| hister | hister | `hister` | Native metrics enabled; authenticated token delivery configured with user approval | Application Workloads; native dashboard follow-up |
| homeassistant | homeassistant | `homeassistant` | External service; native integration/token requires external configuration access | No Kubernetes workload; external follow-up |
| image-builder | image-builder | `image-builder` | No app exporter configured; Kubernetes Job coverage | Application Workloads |
| immich | immich | `immich` | Telemetry disabled; API/worker enabled and collected; DB exporters still absent | Platform Controller Metrics; Application Workloads |
| infra-guards | kyverno | `infra-guards` | Configuration for kyverno; Admission/reports exporters verified; collected and verified | Platform Controller Metrics |
| karakeep | karakeep | `karakeep` | No web exporter configured; scoped Meilisearch metrics integration prepared | Application Workloads |
| keycloak | keycloak | `keycloak` | Collected | Keycloak Events; PostgreSQL Database |
| kube-node-exporter | monitoring | `metrics/kubernetes-node-exporter` | Collected | Cluster load - new; Linux Host Overview |
| kube-state-metrics | kube-system | `metrics/kube-state-metrics-configs` | Collected | Application Workloads; Platform Health |
| kubernetes-prometheus | monitoring | `metrics/kubernetes-prometheus` | Collected; Alertmanager and sidecar collection staged | Prometheus 2.0 Stats; Metrics Collection |
| kubernetes-snapshot-controller | kube-system | `metrics/kubernetes-snapshot-controller` | HTTP metrics endpoint enabled by this change | Application Workloads |
| kyverno | kyverno | `chart:kyverno` | Admission/reports exporters verified; collected and verified | Platform Controller Metrics |
| kyverno-exceptions | kyverno | `kyverno` | Configuration for kyverno; Admission/reports exporters verified; collected and verified | Platform Controller Metrics |
| kyverno-policies | kyverno | `chart:kyverno-policies` | Configuration for kyverno; Admission/reports exporters verified; collected and verified | Platform Controller Metrics |
| lenka | lenka | `lenka` | MySQL workload only; no DB exporter configured | Application Workloads |
| logs-check | monitoring | `metrics` | Kubernetes CronJob and shared platform checks | Platform Health; Application Workloads |
| loki | loki | `chart:loki` | Collected; gateway not separately collected | Three existing Loki dashboards; Metrics Collection |
| loki-external-secrets | loki | `loki` | Configuration for loki; Collected; gateway not separately collected | Three existing Loki dashboards; Metrics Collection |
| loki-network-policy | loki | `loki` | Configuration for loki; Collected; gateway not separately collected | Three existing Loki dashboards; Metrics Collection |
| longhorn | longhorn-system | `chart:longhorn` | Manager collected; individual CSI sidecars not separately collected | Longhorn Example v1.1.0; Database and Storage Metrics |
| longhorn-custom | longhorn-system | `longhorn` | Configuration for longhorn; Manager collected; individual CSI sidecars not separately collected | Longhorn Example v1.1.0; Database and Storage Metrics |
| mail | mail | `mail` | Rspamd/Valkey collected; Postfix/Dovecot/Unbound no dedicated exporters | Rspamd stat; Database and Storage Metrics |
| mastodon | mastodon | `chart:mastodon, chart:values` | PostgreSQL/Valkey collected; web and embedded Sidekiq instrumentation enabled in follow-up | Platform Controller Metrics; Database and Storage Metrics |
| mastodon-custom | mastodon | `mastodon` | Configuration for mastodon; PostgreSQL/Valkey collected; web and embedded Sidekiq instrumentation enabled in follow-up | Platform Controller Metrics; Database and Storage Metrics |
| mempalace | mempalace | `mempalace` | No app exporter configured | Application Workloads |
| metallb | metallb-system | `chart:metallb` | Controller/speaker/FRR HTTPS endpoints authenticated successfully; collected and verified | Cluster Network Metrics |
| metallb-config | metallb-system | `metallb` | Configuration for metallb; Controller/speaker/FRR HTTPS endpoints authenticated successfully; collected and verified | Cluster Network Metrics |
| metrics-server | kube-system | `chart:metrics-server` | Resource API plus authenticated HTTPS self-metrics collection | Application Workloads |
| metrics-server-network-policy | kube-system | `kube-system` | Configuration for metrics-server; Resource API plus authenticated HTTPS self-metrics collection | Application Workloads |
| minecraft | minecraft | `minecraft` | No game exporter configured | Application Workloads |
| monitoring-ingress | monitoring | `metrics` | Configuration for grafana; Collected | Grafana metrics; Metrics Collection |
| monitoring-network-policy | monitoring | `metrics` | Configuration for kubernetes-prometheus; Collected; Alertmanager and sidecar collection staged | Prometheus 2.0 Stats; Metrics Collection |
| namespaces | argocd | `namespaces` | Configuration only; no exporter required | Platform Health |
| nextcloud | nextcloud | `nextcloud` | MySQL/Valkey and Collabora collected; PHP app uses workload coverage | Database and Storage Metrics; Libreoffice Collabora |
| nllb | nllb | `nllb` | No app exporter configured; GPU metrics collected | Application Workloads; GPU Overview |
| ollama | ollama | `ollama` | No native endpoint in the deployed binary; GPU metrics collected | Application Workloads; GPU Overview |
| ollama-small | ollama | `ollama-small` | No native endpoint in the deployed binary; GPU metrics collected | Application Workloads; GPU Overview |
| ooni | ooni | `ooni` | No app exporter configured; job coverage | Application Workloads |
| open-terminal | open-terminal | `open-terminal` | No app exporter configured | Application Workloads |
| open-webui | open-webui | `open-webui` | Native OTLP/HTTP metrics enabled; tracing and OTLP logging disabled | Application Workloads; native dashboard follow-up |
| openbao | openbao | `chart:openbao` | Collected as job=openbao; existing dashboard repaired | Vault Overview |
| openbao-custom | openbao | `openbao` | Configuration for openbao; Collected as job=openbao; existing dashboard repaired | Vault Overview |
| openbao-network-policy | openbao | `openbao` | Configuration for openbao; Collected as job=openbao; existing dashboard repaired | Vault Overview |
| opensearch | opensearch | `opensearch` | No Prometheus exporter/plugin configured | Application Workloads |
| platform-health | monitoring | `metrics` | Collected | Platform Health |
| plex | plex | `plex` | No media-server exporter configured | Application Workloads |
| reloader | argocd | `chart:reloader` | Exporter verified; collected and verified | Platform Controller Metrics |
| ripe-atlas | ripe-atlas | `ripe-atlas` | No app exporter configured | Application Workloads |
| searxng | searxng | `searxng` | No app exporter configured | Application Workloads |
| seaweedfs | seaweedfs | `seaweedfs` | Master/volume/filer/S3 collected | SeaweedFS (datasource repairs deployed) |
| stirling-pdf | stirling-pdf | `stirling-pdf` | No app exporter configured; native Prometheus feature is licence-dependent | Application Workloads |
| talos-backup | talos-backup | `talos-backup` | CronJob success tracked; existing backup alerts | Application Workloads |
| thanos | monitoring | `thanos` | Querier/store/compactor collected; Prometheus sidecar collected and verified | Thanos / Overview; Metrics Collection |
| traefik | traefik | `chart:traefik` | Collected twice by pod and dedicated jobs; deduplication staged | Traefik Official Standalone Dashboard |
| traefik-network-policy | traefik | `traefik` | Configuration for traefik; Collected twice by pod and dedicated jobs; deduplication staged | Traefik Official Standalone Dashboard |
| traefik-private | traefik | `chart:traefik` | Collected twice by pod and dedicated jobs; deduplication staged | Traefik Official Standalone Dashboard |
| unifi-exporter | unifi | `unifi/poller` | Collected | Six UniFi-Poller dashboards |
| wordpress | wordpress | `wordpress` | MySQL/analytics collected; Valkey exporter verified, collected and verified | WordPress Analytics; MySQL Dashboard (repair deployed) |
| year | year | `year` | No app exporter configured | Application Workloads |
| your-spotify | spotify | `your-spotify` | FerretDB collected; authenticated native server metrics configured; backing PostgreSQL uses workload coverage | Database and Storage Metrics; Application Workloads |

## Native coverage still requiring work

- Home Assistant is an externally routed service, not a Kubernetes Deployment. Enabling its Prometheus integration and providing a long-lived token requires access to the external installation. Keep authentication enabled; do not expose `/api/prometheus` anonymously.
- Meilisearch now has a dedicated `metrics.get` key stored in OpenBao with user approval. The prepared ExternalSecret supplies that restricted key to Prometheus; the master key is not copied into monitoring. The enabled endpoint was authenticated successfully, and 128 native time series were observed in Prometheus after deployment.
- Firefox Sync emits StatsD; a localhost-only StatsD exporter sidecar and Prometheus scrape are prepared. Its UDP receiver is not exposed through a Service or ingress. Native request-duration and request counters were verified from real emitted events after deployment.
- Database exporters remain absent for Immich PostgreSQL/Valkey, Spotify backing PostgreSQL, Firefox Sync MySQL, Lenka MySQL and Harbor internal PostgreSQL/Redis. Existing application/exporter metrics do not replace those database diagnostics.
- Other applications marked “No app exporter configured” have shared workload coverage. This is an observed configuration gap, not a claim that their upstream software cannot support an exporter. Adding third-party exporters/instrumentation requires selecting and validating the integration; it has not been silently represented as complete.
- Stirling PDF native Prometheus support requires a Team/Enterprise licence according to current upstream documentation; no licence change is made.
- All four Longhorn CSI control-component endpoints (attacher/provisioner/resizer/snapshotter) were verified and added to discovery. The CSI liveness endpoint and Longhorn global manager return 404 for /metrics; no nonexistent targets are added. Loki gateway remains without a separate native exporter. Metrics Server, snapshot-controller, GPU node-feature-discovery and both embedded Alloy sidecars are covered by the follow-up collection configuration. Argo Dex has no responding metrics listener in this installation; it is not configured as an authentication provider.

## Existing dashboard review

All 35 dashboards were fetched and inspected recursively, including collapsed rows. No broad legacy-panel conversion was attempted: changing graph/table-old/singlestat schemas requires checking thresholds, transformations, repeats and display behavior. New database/storage panels provide a modern alternative without deleting existing dashboards.

| Dashboard | UID | Findings / action |
|---|---|---|
| ArgoCD | `qPkgGHg7k` | Add tags |
| ClamAV Exporter | `d2052af1-457f-4ae5-b0db-06e9bb739a81` | Add description |
| Cluster load - new | `c1e02fb9-c0c3-46ca-bd7e-0935a5b44278` | Add description |
| CrowdSec | `crowdsec-overview` | No broken datasource or legacy panel detected; validate queries and usability during normal use |
| External Access Analytics | `external-access-analytics` | Add description |
| Finance Ticker | `finance-ticker` | Add description |
| Grafana metrics | `isFoa0z7k` | 2 legacy panels; migrate and visually verify |
| Harbor Overview | `a65d2835-5027-46c8-951f-3799fb702232` | No broken datasource or legacy panel detected; validate queries and usability during normal use |
| Keycloak Events | `keycloak-events-only2` | Add description |
| Libreoffice Collabora | `pu47l-knz` | Add description; Add tags |
| Linux Host Overview | `linux-host-overview` | No broken datasource or legacy panel detected; validate queries and usability during normal use |
| Loki Logging Volume Analysis | `nmSpiZwHz` | No broken datasource or legacy panel detected; validate queries and usability during normal use |
| Loki Metrics Dashboard | `5f309ebf-2092-4182-b342-4a22c39f10b2` | 143 total nested panels; review generated/repeated expansion and query cost |
| Loki2.0 Global Metrics | `MQHVDmtWk` | No broken datasource or legacy panel detected; validate queries and usability during normal use |
| Longhorn Example v1.1.0 | `2BCgsldGz` | 11 legacy panels; migrate and visually verify; Add tags |
| MongoDB Exporter + Go/Process | `mongodb-exporter-go-process` | Generic MongoDB panels may not match FerretDB; use staged native FerretDB pool/request panels |
| MySQL Dashboard | `r4uc0hUGk` | Stale datasource and invalid host-memory join; repair deployed; 2 legacy panels; migrate and visually verify; Add tags |
| OpenWRT | `fLi0yXAWk` | Add tags |
| Platform Health | `platform-health` | Add description |
| PostgreSQL Database | `000000039` | 32 legacy panels; migrate and visually verify |
| Prometheus 2.0 Stats | `UDdpyzz7z` | Add description |
| Redis Dashboard for Prometheus Redis Exporter (helm stable/redis-ha) | `xDLNRKUWz` | 9 legacy panels; migrate and visually verify |
| Rspamd stat | `190zF30Vk` | Add tags |
| SeaweedFS | `nh02dOVnz` | Stale Prometheus datasource reference; repair deployed; Add description; Add tags |
| Synapse | `9f15576b-9cf6-4bfc-a3ab-bb95654d97c8` | Add description |
| Thanos / Overview | `xhXVFwJ7z` | Add tags |
| Traefik Official Standalone Dashboard | `n5bu_kv45` | Add tags |
| UniFi-Poller: Client DPI - Prometheus | `w3usaHLZk` | 267 legacy panels; migrate and visually verify; 275 total nested panels; review generated/repeated expansion and query cost |
| UniFi-Poller: Client Insights - Prometheus | `jMfvAjxWz` | 18 legacy panels; migrate and visually verify |
| UniFi-Poller: Network Sites - Prometheus | `9WaGWZaZk` | 5 legacy panels; migrate and visually verify |
| UniFi-Poller: UAP Insights - Prometheus | `g5wFWqxZk` | 20 legacy panels; migrate and visually verify |
| UniFi-Poller: USG Insights - Prometheus | `4Yo8IZ-Wk` | 15 legacy panels; migrate and visually verify |
| UniFi-Poller: USW Insights - Prometheus | `FsfxpWaZz` | 15 legacy panels; migrate and visually verify |
| Vault Overview | `vault-overview` | Stale job and nonexistent seal/leader/route metrics; repair deployed; Add description |
| WordPress Analytics | `wordpress-analytics` | Add description |

## Alert inventory and suggested changes — not implemented

Existing rules: High Node Memory, High Swap Usage, High Load Avarage, High Filesystem Usage, Mysql is down, VaultMetricsTargetDown, VaultSealed, Postgresql-bitwarden is down, Postgresql-keycloak is down, Postgresql-dawarich is down, Postgresql-mastodon is down, KubeJobFailed, TalosEtcdBackupMissing, TalosEtcdBackupSuspended, CPUThrottlingHigh, KubePodCrashLooping, KubePodNotReady, KubeNodeNotReady, KubeNodeUnreachable, TargetDown, PVC is full!.

| Priority | Addition or correction | Trigger / rationale |
|---|---|---|
| P1 | Repair OpenBao alert selectors | `VaultMetricsTargetDown` selects `job="vault"`; use `openbao` and detect absent targets. `VaultSealed` references absent `vault_sys_sealed`; use observed `vault_core_unsealed` with target-down coverage. |
| P1 | Detect missing expected scrape jobs | Existing TargetDown only sees `up=0`; it cannot detect exporters that disappear from discovery. Track expected critical jobs and replica counts using `absent`/inventory comparisons. |
| P1 | Alert delivery failure | Prometheus notification errors, Alertmanager failed notifications and missing Alertmanager peers; verify an actual email notification separately. |
| P1 | Certificate expiry and readiness | Certificates expiring within 14 days or prolonged not-ready state after cert-manager metrics arrive. |
| P1 | External Secrets reconciliation | SecretStore/ExternalSecret not-ready or repeated reconcile/provider errors; validate condition labels after rollout. |
| P1 | Workload desired/available mismatch | Deployment/StatefulSet/DaemonSet replica deficits, rollout deadlines and Running pods with Ready=false. Existing KubePodNotReady only examines Pending/Unknown/Failed phases. |
| P1 | Argo application health and sync | Sustained Degraded/Missing/Unknown health, failed syncs and unexpectedly OutOfSync applications; account for deliberate maintenance. |
| P1 | Storage before exhaustion | PVC warning at 85–90%, inode exhaustion and predicted capacity exhaustion; retain existing >95% critical alert. Longhorn degraded/faulted robustness and replica redundancy loss. |
| P2 | Backup freshness beyond Talos | Backup-rsync and application/database backups missing successful runs; thresholds based on actual schedules and suspension state. |
| P2 | Database/cache failures and saturation | Redis/Valkey down, rejected connections, memory/evictions, PostgreSQL connection saturation/replication lag and MySQL connection saturation; distinguish exporter health from server health. |
| P2 | Ingress/user-facing errors | Sustained Traefik 5xx fraction and latency with minimum traffic; independent HTTPS reachability probes for critical services. |
| P2 | Monitoring data loss | Prometheus rule errors/TSDB failures, Thanos upload/compaction failures, Loki ingestion errors and Alloy failed config loads/dropped log entries. |
| P2 | Cluster networking | CoreDNS error/latency, Cilium drops/lost Hubble events, MetalLB address exhaustion/announcement failure and relevant FRR/BGP session state after metrics collection. |
| P2 | Application queues | Mastodon Sidekiq backlog/retries, Immich failed/pending jobs, mail queue age/depth and Harbor job failures, after verifying real application instrumentation. |
| P2 | GPU health | Temperature against the device specification, uncorrectable remapped rows, exporter disappearance and OOM/driver faults; high utilization alone need not page. |
| P3 | Alert hygiene | Add ownership/runbooks and warning/critical routing; review fixed load=20 and typo in High Load Avarage; suppress expected maintenance/offline-target noise. |

## Validation and deployment boundary

- Live: exporter endpoint probes, authenticated MetalLB/FRR reads, Grafana health/datasources/dashboard inventory, active scrape health and Prometheus rule evaluation health.
- Local: YAML/JSON parsing, Prometheus config validation with the running promtool, live PromQL validation, provisioned dashboard mounts, target selector review and unchanged-alert comparison. Checks passed before the final infrastructure follow-up: running promtool syntax validation, 25 focused unit tests, git diff --check, 103 live PromQL evaluations (102 returned data; one event-dependent OpenBao policy counter was absent). All four newly instrumented application exporters returned native series; the new native dashboards use those observed metric families. Alert payload is byte-for-byte unchanged.
- The initial monitoring change was published as `4d20d49c` and reconciled by Argo CD. The first post-rollout target capture contained 129 active targets, all up. Meilisearch collection, exporter namespace-label preservation and Immich startup optimization are follow-up changes. No alert mutation was performed. Repository-local configuration alone does not establish collection. After publishing through the authorized GitOps process, recheck target counts and `up`, actual new metric families, Grafana provisioning and representative panel data over multiple scrape intervals.

## Upstream references

- [Immich monitoring](https://docs.immich.app/features/monitoring/)
- [cert-manager Prometheus metrics](https://cert-manager.io/docs/devops-tips/prometheus-metrics/)
- [Headlamp telemetry — metrics use the main HTTP port](https://headlamp.dev/docs/latest/development/telemetry/)
- [Home Assistant Prometheus integration](https://www.home-assistant.io/integrations/prometheus/)
- [Meilisearch metrics API and metrics.get authorization](https://specs.meilisearch.dev/specifications/text/0174-metrics-api.html)
- [Mozilla Syncstorage application configuration](https://mozilla-services.github.io/syncstorage-rs/config.html)
- [Stirling PDF usage monitoring](https://docs.stirlingpdf.com/Configuration/Automation/Usage%20Monitoring/)
- Pinned chart values inspected directly: cert-manager v1.21.3, Cilium 1.20.4, MetalLB 0.16.1.

Local Strata delegation was attempted; the readiness check failed, so the audit and implementation were completed directly.

Immich startup follow-up: the existing library init recursively applied chown even to entries already owned by 1000:1000. Limit chown to entries with mismatched owner/group, retaining the permission-repair semantics while avoiding unnecessary metadata writes. The root, upload and thumbs directories were verified already owned by 1000:1000.

## Additional collection verification

- After the Firefox/Mastodon rollout, all 134 scrape targets were up. Native series counts at that capture: Immich 5,102; Meilisearch 128; Firefox Sync 102; Mastodon 68; External Secrets 3,140; Kyverno 10,475; Headlamp 992.
- Metrics Server self-metrics accepted the projected Prometheus service-account token over HTTPS. Its serving certificate is self-signed, consistent with the existing APIService TLS configuration; the scrape retains authentication and skips certificate verification.
- GPU node-feature-discovery and both Bitwarden/Nextcloud Alloy sidecar endpoints responded with native metrics before collection was added. Their endpoints were already enabled.
- A platform-health scrape warning was traced to duplicate restart-detail samples when a Pod name was reused with a different UID. Coalesce only those exposed restart samples by their public labels. Preserve the report checks, report/HTML content, and notification decisions. The existing generated metrics-only snapshot was corrected with a resourceVersion check; no report email was triggered. A regression test covers two Pod incarnations with distinct restart counts.
- Native applications with no suitable exporter continue to have shared Kubernetes workload metrics. This does not invent application-level request or queue metrics. Externally hosted Home Assistant and licence-gated Stirling PDF telemetry require the separate access/licence follow-ups listed above.

Additional references: [Open WebUI telemetry](https://docs.openwebui.com/reference/monitoring/otel/), [Prometheus OTLP receiver](https://prometheus.io/docs/guides/opentelemetry/), [StatsD exporter](https://github.com/prometheus/statsd_exporter).

## Remaining endpoint capability checks

A read-only /metrics probe covered Bastioncam, Bitwarden, CA Scanner, ComfyUI, ConvertX, Dawarich, Photon, Hister, Karakeep, MemPalace, NLLB, both Ollama servers, Open Terminal, Plex, SearxNG, Your Spotify and Year. HTML responses were not mistaken for metric exposition. Most routes returned 404; Hister/Plex returned 403 and Your Spotify returned 401. Upstream documentation identified Hister's optional flag and Spotify's protected native endpoint, so those integrations were configured with explicitly authorized credentials. Hister uses its existing application access token because it offers no metrics-only scope; Spotify uses a dedicated metrics password. These values are delivered through OpenBao/External Secrets and never committed.

The installed Ollama 0.40.14 binary contains no OLLAMA_METRICS environment key, both servers return 404 for /metrics, and upstream's native endpoint remains an open feature request. No unmerged feature flag or new proxy was introduced. Shared workload/GPU telemetry remains valid for those servers.

Open WebUI native metrics were verified in Prometheus as http_server_requests_total, http_server_duration_milliseconds and aggregate webui_users_* series. Native endpoint probes found all four CSI control components already exposing roughly 200 metric families each. They are collected separately from Longhorn manager storage metrics.

References: [Hister metrics and authentication](https://hister.org/docs/monitoring), [Your Spotify native metrics](https://github.com/Yooooomi/your_spotify/tree/master/apps/server#prometheus), [Ollama native metrics feature request](https://github.com/ollama/ollama/issues/3144).

External Secrets policy correction: the added broad pod-selector ingress policy unintentionally isolated the previously unselected webhook and blocked admission traffic. It was narrowed immediately and removed from GitOps as redundant: the existing policy already permits metrics on non-webhook components, while the webhook retains its prior admission access. No controller, certificate, or fail-open behavior was changed.

Final native dashboard additions: Hister and Your Spotify use authenticated endpoint probes grounded in live metric families. Spotify business counters are lazy/event-dependent; process/Node.js metrics were verified immediately and absent business counters are not filled with artificial zeros. Application Workloads also exposes namespace-filtered Traefik service throughput, 5xx responses and p95 latency for applications without a native exporter. Two remaining Alloy timeouts were traced to ingress policies matching Deployment metadata labels rather than Pod labels; selectors were corrected to Bitwarden service=bitwarden and Nextcloud app=nextcloud,component=web.

Completed dashboard query validation: all 128 queries evaluated successfully against live Prometheus; 125 returned series. The absent queries were an event-dependent OpenBao policy counter and Spotify ingestion/import counters. Source policy selectors were checked against live Pod-template labels. A final handoff rechecks target health, Argo state and provisioned dashboard count after the selector/dashboard sync.
