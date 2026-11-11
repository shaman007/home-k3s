#!/usr/bin/env python3
"""Generate the GitOps dashboards added by the November 2026 monitoring audit."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UID = "ed6c70f1-51fe-45d9-9fd0-74971e3d2fd4"
DS = {"type": "prometheus", "uid": UID}


def dashboard(uid, title, description, specs, variables=None):
    """Build a Grafana dashboard with the supplied panels and template variables."""
    panels = []
    for i, (name, expr, unit, legend) in enumerate(specs):
        panels.append(
            {
                "id": i + 1,
                "type": "timeseries",
                "title": name,
                "datasource": DS,
                "gridPos": {"x": (i % 2) * 12, "y": (i // 2) * 8, "w": 12, "h": 8},
                "fieldConfig": {
                    "defaults": {
                        "unit": unit,
                        "min": 0,
                        "custom": {
                            "drawStyle": "line",
                            "lineWidth": 1,
                            "showPoints": "never",
                            "spanNulls": False,
                        },
                    },
                    "overrides": [],
                },
                "options": {
                    "legend": {
                        "showLegend": True,
                        "displayMode": "table",
                        "placement": "bottom",
                        "calcs": ["lastNotNull"],
                    },
                    "tooltip": {"mode": "multi", "sort": "desc"},
                },
                "targets": [{"refId": "A", "expr": expr, "legendFormat": legend, "range": True}],
            }
        )
    d = {
        "uid": uid,
        "title": title,
        "description": description,
        "tags": ["homelab", "monitoring-audit"],
        "schemaVersion": 41,
        "version": 1,
        "editable": True,
        "refresh": "1m",
        "time": {"from": "now-6h", "to": "now"},
        "timezone": "browser",
        "panels": panels,
        "templating": {"list": variables or []},
    }
    name = "grafana-dashboard-" + uid
    text = json.dumps(d, indent=2)
    (ROOT / "metrics/grafana" / ("config-map-" + name + ".yaml")).write_text(
        "---\napiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: "
        + name
        + "\n  namespace: monitoring\ndata:\n  "
        + uid
        + ".json: |-\n"
        + "\n".join("    " + line for line in text.splitlines())
        + "\n"
    )
    return name


def query_variable(name, query):
    """Build a Prometheus-backed Grafana query variable."""
    return {
        "name": name,
        "label": name.title(),
        "type": "query",
        "datasource": DS,
        "query": {"query": query, "refId": "StandardVariableQuery"},
        "refresh": 1,
        "multi": True,
        "includeAll": True,
        "allValue": ".*",
        "current": {"text": "All", "value": "$__all"},
        "options": [],
    }


names = []
NAMESPACE_FILTER = 'namespace=~"$namespace"'
names.append(
    dashboard(
        "application-workloads",
        "Application Workloads",
        (
            "Shared resource and availability coverage for every installe"
            "d workload. Select a namespace. Native application metrics r"
            "equire a separate exporter; empty series remain visible as n"
            "o data."
        ),
        [
            (
                "CPU cores by pod",
                (
                    f"sum by (namespace,pod) (rate(container_cpu_usage_seconds_tot"
                    f"al{{"
                    f"{NAMESPACE_FILTER}"
                    f',container!="",container!="POD"}}[$__rate_interval]))'
                ),
                "cores",
                "{{namespace}} / {{pod}}",
            ),
            (
                "Working set memory by pod",
                (
                    f"sum by (namespace,pod) (container_memory_working_set_bytes{{"
                    f"{NAMESPACE_FILTER}"
                    f',container!="",container!="POD"}})'
                ),
                "bytes",
                "{{namespace}} / {{pod}}",
            ),
            (
                "Container restarts in 1 hour",
                (
                    f"sum by (namespace,pod) (increase(kube_pod_container_status_r"
                    f"estarts_total{{"
                    f"{NAMESPACE_FILTER}"
                    f"}}[1h]))"
                ),
                "short",
                "{{namespace}} / {{pod}}",
            ),
            (
                "Ready containers",
                f"sum by (namespace,pod) (kube_pod_container_status_ready{{{NAMESPACE_FILTER}}})",
                "short",
                "{{namespace}} / {{pod}}",
            ),
            (
                "Deployment unavailable replicas",
                f"kube_deployment_status_replicas_unavailable{{{NAMESPACE_FILTER}}}",
                "short",
                "{{namespace}} / {{deployment}}",
            ),
            (
                "StatefulSet missing ready replicas",
                (
                    f"kube_statefulset_replicas{{"
                    f"{NAMESPACE_FILTER}"
                    f"}} - kube_statefulset_status_replicas_ready{{"
                    f"{NAMESPACE_FILTER}"
                    f"}}"
                ),
                "short",
                "{{namespace}} / {{statefulset}}",
            ),
            (
                "DaemonSet unavailable pods",
                f"kube_daemonset_status_number_unavailable{{{NAMESPACE_FILTER}}}",
                "short",
                "{{namespace}} / {{daemonset}}",
            ),
            (
                "CPU requests by namespace",
                (
                    "sum by (namespace) (kube_pod_container_resource_requests{"
                    f'{NAMESPACE_FILTER},resource="cpu"'
                    "})"
                ),
                "cores",
                "{{namespace}}",
            ),
            (
                "Memory requests by namespace",
                (
                    f"sum by (namespace) (kube_pod_container_resource_requests{{"
                    f"{NAMESPACE_FILTER}"
                    f',resource="memory"}})'
                ),
                "bytes",
                "{{namespace}}",
            ),
            (
                "PVC utilization",
                (
                    f"100 * max by (namespace,persistentvolumeclaim) (kubelet_volu"
                    f"me_stats_used_bytes{{"
                    f"{NAMESPACE_FILTER}"
                    f"}} / kubelet_volume_stats_capacity_bytes{{"
                    f"{NAMESPACE_FILTER}"
                    f"}})"
                ),
                "percent",
                "{{namespace}} / {{persistentvolumeclaim}}",
            ),
            (
                "CronJob time since last successful run",
                f"time() - kube_cronjob_status_last_successful_time{{{NAMESPACE_FILTER}}}",
                "s",
                "{{namespace}} / {{cronjob}}",
            ),
            (
                "Ingress requests by service",
                (
                    'sum by (service) (rate(traefik_service_requests_total{job="t'
                    'raefik",service=~"($namespace)-.*"}[$__rate_interval]))'
                ),
                "ops",
                "{{service}}",
            ),
            (
                "Ingress 5xx responses by service",
                (
                    'sum by (service) (rate(traefik_service_requests_total{job="t'
                    'raefik",service=~"($namespace)-.*",code=~"5.."}[$__rate_inte'
                    "rval]))"
                ),
                "ops",
                "{{service}}",
            ),
            (
                "Ingress p95 latency by service",
                (
                    "histogram_quantile(0.95, sum by (le,service) (rate(traefik_s"
                    'ervice_request_duration_seconds_bucket{job="traefik",service'
                    '=~"($namespace)-.*"}[$__rate_interval])))'
                ),
                "s",
                "{{service}}",
            ),
            (
                "Argo applications by sync and health",
                "count by (sync_status,health_status) (argocd_app_info)",
                "short",
                "{{sync_status}} / {{health_status}}",
            ),
        ],
        [query_variable("namespace", "label_values(kube_pod_info, namespace)")],
    )
)

names.append(
    dashboard(
        "metrics-collection",
        "Metrics Collection",
        (
            "Scrape health, sample volume, alert delivery and collector h"
            "ealth. Up means an endpoint responded, not that the applicat"
            "ion is healthy. A missing target is different from a down ta"
            "rget."
        ),
        [
            ("Targets up", 'sum by (job) (up{job=~"$job"})', "short", "{{job}}"),
            ("Targets down", 'sum by (job) (1 - up{job=~"$job"})', "short", "{{job}}"),
            (
                "Scrape duration",
                'max by (job) (scrape_duration_seconds{job=~"$job"})',
                "s",
                "{{job}}",
            ),
            (
                "Samples after relabeling",
                'sum by (job) (scrape_samples_post_metric_relabeling{job=~"$job"})',
                "short",
                "{{job}}",
            ),
            (
                "Scrape sample churn",
                'sum by (job) (scrape_series_added{job=~"$job"})',
                "short",
                "{{job}}",
            ),
            (
                "Prometheus TSDB series",
                'prometheus_tsdb_head_series{job="prometheus"}',
                "short",
                "{{instance}}",
            ),
            (
                "Prometheus rule evaluation failures",
                (
                    'sum(rate(prometheus_rule_evaluation_failures_total{job="prom'
                    'etheus"}[$__rate_interval]))'
                ),
                "ops",
                "failures",
            ),
            (
                "Prometheus alert notification errors",
                (
                    'sum(rate(prometheus_notifications_errors_total{job="promethe'
                    'us"}[$__rate_interval]))'
                ),
                "ops",
                "errors",
            ),
            (
                "Alertmanager notification failures",
                (
                    "sum by (integration) (rate(alertmanager_notifications_failed"
                    '_total{job="alertmanager"}[$__rate_interval]))'
                ),
                "ops",
                "{{integration}}",
            ),
            (
                "Alloy last config load successful",
                'alloy_config_last_load_successful{job="alloy"}',
                "short",
                "{{pod}}",
            ),
        ],
        [query_variable("job", "label_values(up, job)")],
    )
)

names.append(
    dashboard(
        "gpu-overview",
        "GPU Overview",
        (
            "NVIDIA DCGM metrics already collected from the GPU operator."
            " Memory values are MiB as exported by DCGM. GPU utilization "
            "is distinct from Kubernetes CPU usage."
        ),
        [
            ("GPU utilization", "DCGM_FI_DEV_GPU_UTIL", "percent", "{{Hostname}} / {{gpu}}"),
            (
                "GPU memory used",
                "DCGM_FI_DEV_FB_USED * 1024 * 1024",
                "bytes",
                "{{Hostname}} / {{gpu}}",
            ),
            (
                "GPU memory free",
                "DCGM_FI_DEV_FB_FREE * 1024 * 1024",
                "bytes",
                "{{Hostname}} / {{gpu}}",
            ),
            ("GPU temperature", "DCGM_FI_DEV_GPU_TEMP", "celsius", "{{Hostname}} / {{gpu}}"),
            ("GPU power", "DCGM_FI_DEV_POWER_USAGE", "watt", "{{Hostname}} / {{gpu}}"),
            ("Encoder utilization", "DCGM_FI_DEV_ENC_UTIL", "percent", "{{Hostname}} / {{gpu}}"),
            ("Decoder utilization", "DCGM_FI_DEV_DEC_UTIL", "percent", "{{Hostname}} / {{gpu}}"),
            (
                "Uncorrectable remapped rows",
                "DCGM_FI_DEV_UNCORRECTABLE_REMAPPED_ROWS",
                "short",
                "{{Hostname}} / {{gpu}}",
            ),
        ],
    )
)

names.append(
    dashboard(
        "network-metrics",
        "Cluster Network Metrics",
        (
            "Cilium, Hubble and IPv4 service BGP metrics from MetalLB/FRR"
            " and read-only UDM API collection. Compare speaker intent wi"
            "th installed UDM next hops. L2 and IPv6 remain active. No pa"
            "cket inspection features are enabled."
        ),
        [
            (
                "Hubble flows",
                "sum by (verdict) (rate(hubble_flows_processed_total[$__rate_interval]))",
                "ops",
                "{{verdict}}",
            ),
            (
                "Hubble dropped packets",
                "sum by (reason) (rate(hubble_drop_total[$__rate_interval]))",
                "pps",
                "{{reason}}",
            ),
            (
                "Hubble lost events",
                "sum by (source) (rate(hubble_lost_events_total[$__rate_interval]))",
                "ops",
                "{{source}}",
            ),
            (
                "Cilium agent target health",
                'up{job="kubernetes-pods",kubernetes_namespace="kube-system",k8s_app="cilium"}',
                "short",
                "{{instance}}",
            ),
            (
                "CoreDNS requests",
                "sum by (type) (rate(coredns_dns_requests_total[$__rate_interval]))",
                "ops",
                "{{type}}",
            ),
            (
                "CoreDNS response codes",
                "sum by (rcode) (rate(coredns_dns_responses_total[$__rate_interval]))",
                "ops",
                "{{rcode}}",
            ),
            ("MetalLB target health", 'up{job="metallb"}', "short", "{{pod}} / {{instance}}"),
            (
                "Cilium dropped packets",
                "sum by (reason,direction) (rate(cilium_drop_count_total[$__rate_interval]))",
                "pps",
                "{{direction}} / {{reason}}",
            ),
            (
                "UDM BGP sessions (1 = established)",
                'frrk8s_bgp_session_up{job="metallb",peer="192.168.30.1",vrf="default"}',
                "short",
                "{{node}} / {{peer}}",
            ),
            (
                "FRR IPv4 advertised prefixes",
                (
                    'frrk8s_bgp_announced_prefixes_total{job="metallb",peer="192.'
                    '168.30.1",vrf="default"}'
                ),
                "short",
                "{{node}}",
            ),
            (
                "IPv4 service BGP paths with established sessions",
                (
                    'count by(service,ip) ((metallb_speaker_announced{job="metall'
                    'b",protocol="bgp",ip!~".*:.*"} == 1) and on(node) max by(nod'
                    'e) (frrk8s_bgp_session_up{job="metallb",peer="192.168.30.1",'
                    'vrf="default"} == 1))'
                ),
                "short",
                "{{service}} / {{ip}}",
            ),
            (
                "FRR stale configuration (0 = healthy)",
                'frrk8s_k8s_client_config_stale_bool{job="metallb"}',
                "short",
                "{{node}}",
            ),
            (
                "Unexpected routes received from UDM (expected 0)",
                (
                    'frrk8s_bgp_received_prefixes_total{job="metallb",peer="192.1'
                    '68.30.1",vrf="default"}'
                ),
                "short",
                "{{node}}",
            ),
            (
                "UDM BGP collection (1 = successful)",
                'unifi_bgp_scrape_success{job="unifi-bgp"}',
                "short",
                "{{instance}}",
            ),
            (
                "UDM installed active service next hops",
                'unifi_bgp_route_active_next_hops{job="unifi-bgp"}',
                "short",
                "{{prefix}}",
            ),
            (
                "UDM neighbor state (1 = established)",
                'unifi_bgp_peer_established{job="unifi-bgp"}',
                "short",
                "{{peer}}",
            ),
            (
                "UDM routes exported to Kubernetes (expected 0)",
                'unifi_bgp_exported_routes{job="unifi-bgp"}',
                "short",
                "{{peer}}",
            ),
            (
                "UDM routing policy violations (expected 0)",
                'unifi_bgp_policy_violations{job="unifi-bgp"}',
                "short",
                "{{reason}}",
            ),
        ],
    )
)

names.append(
    dashboard(
        "platform-controllers",
        "Platform Controller Metrics",
        (
            "Certificates, secrets, admission policies, reloads and appli"
            "cation telemetry. Counters with no events may not exist yet."
            " New exporter data remains empty until rollout and scrape ve"
            "rification."
        ),
        [
            (
                "Certificate lifetime remaining",
                "certmanager_certificate_expiration_timestamp_seconds - time()",
                "s",
                "{{namespace}} / {{name}}",
            ),
            (
                "Certificate readiness",
                'certmanager_certificate_ready_status{condition="True"}',
                "short",
                "{{namespace}} / {{name}}",
            ),
            (
                "ExternalSecret readiness",
                'externalsecret_status_condition{job="external-secrets"}',
                "short",
                "{{namespace}} / {{name}} / {{condition}}",
            ),
            (
                "External Secrets reconcile errors",
                (
                    "sum by (pod) (rate(controller_runtime_reconcile_errors_total"
                    '{job="external-secrets"}[$__rate_interval]))'
                ),
                "ops",
                "{{pod}}",
            ),
            (
                "Kyverno admission requests",
                (
                    "sum by (request_allowed) (rate(kyverno_admission_requests_to"
                    'tal{job="kyverno"}[$__rate_interval]))'
                ),
                "ops",
                "{{request_allowed}}",
            ),
            (
                "Kyverno policy results",
                (
                    'sum(rate(kyverno_validating_policy_results_total{job="kyvern'
                    'o"}[$__rate_interval]))'
                ),
                "ops",
                "policy results",
            ),
            (
                "Reloader executed reloads",
                (
                    'sum by (pod) (rate(reloader_reload_executed_total{job="reloa'
                    'der"}[$__rate_interval]))'
                ),
                "ops",
                "{{pod}}",
            ),
            (
                "Mastodon exporter sessions",
                'ruby_collector_sessions_total{job="mastodon"}',
                "short",
                "{{pod}}",
            ),
            (
                "Mastodon exporter working",
                'ruby_collector_working{job="mastodon"}',
                "short",
                "{{pod}}",
            ),
            (
                "Immich collected metric families",
                'count by (__name__) ({job="immich",__name__!~"up|scrape_.*"})',
                "short",
                "{{__name__}}",
            ),
            ("Headlamp target health", 'up{job="headlamp"}', "short", "{{pod}}"),
            (
                "Argo repository requests",
                (
                    'sum by (request_type) (rate(argocd_git_request_total{job="ar'
                    'gocd-repo-server"}[$__rate_interval]))'
                ),
                "ops",
                "{{request_type}}",
            ),
        ],
    )
)

names.append(
    dashboard(
        "data-services",
        "Database and Storage Metrics",
        (
            "Modern panels for existing PostgreSQL, MySQL, Valkey, Ferret"
            "DB and Longhorn exporters. These supplement the imported leg"
            "acy dashboards. Database exporters do not establish applicat"
            "ion request health."
        ),
        [
            ("PostgreSQL exporter health", "pg_up", "short", "{{job}} / {{instance}}"),
            (
                "PostgreSQL database size",
                "pg_database_size_bytes",
                "bytes",
                "{{job}} / {{datname}}",
            ),
            ("MySQL exporter health", "mysql_up", "short", "{{job}}"),
            ("MySQL connections", "mysql_global_status_threads_connected", "short", "{{job}}"),
            ("Valkey exporter health", "redis_up", "short", "{{job}}"),
            ("Valkey used memory", "redis_memory_used_bytes", "bytes", "{{job}}"),
            (
                "Valkey commands",
                "rate(redis_commands_processed_total[$__rate_interval])",
                "ops",
                "{{job}}",
            ),
            (
                "FerretDB client requests",
                (
                    "sum by (method) (rate(ferretdb_client_duration_seconds_count"
                    '{job="ferretdb"}[$__rate_interval]))'
                ),
                "ops",
                "{{method}}",
            ),
            (
                "FerretDB acquired pool connections",
                'ferretdb_pool_acquired{job="ferretdb"}',
                "short",
                "{{instance}}",
            ),
            (
                "FerretDB canceled connection acquisitions",
                'rate(ferretdb_pool_acquires_canceled_total{job="ferretdb"}[$__rate_interval])',
                "ops",
                "{{instance}}",
            ),
            ("Longhorn volume robustness", "longhorn_volume_robustness", "short", "{{volume}}"),
            ("Longhorn actual size", "longhorn_volume_actual_size_bytes", "bytes", "{{volume}}"),
            ("Longhorn read throughput", "longhorn_volume_read_throughput", "Bps", "{{volume}}"),
            ("Longhorn write throughput", "longhorn_volume_write_throughput", "Bps", "{{volume}}"),
        ],
    )
)

names.append(
    dashboard(
        "firefox-sync-metrics",
        "Firefox Sync Metrics",
        (
            "Native Syncstorage StatsD metrics received by the localhost-"
            "only bridge. Durations are converted from StatsD timers to s"
            "econds. Idle/error series may be absent until events occur."
        ),
        [
            (
                "Requests by route",
                (
                    "sum by (method,route) (rate(syncstorage_request_duration_cou"
                    'nt{job="firefox-sync"}[$__rate_interval]))'
                ),
                "ops",
                "{{method}} / {{route}}",
            ),
            (
                "Requests by status",
                (
                    "sum by (status) (rate(syncstorage_request_duration_count{job"
                    '="firefox-sync"}[$__rate_interval]))'
                ),
                "ops",
                "{{status}}",
            ),
            (
                "Mean request duration",
                (
                    'sum(rate(syncstorage_request_duration_sum{job="firefox-sync"'
                    "}[$__rate_interval])) / sum(rate(syncstorage_request_duratio"
                    'n_count{job="firefox-sync"}[$__rate_interval]))'
                ),
                "s",
                "mean",
            ),
            (
                "StatsD events received",
                (
                    'sum by (type) (rate(statsd_exporter_events_total{job="firefo'
                    'x-sync"}[$__rate_interval]))'
                ),
                "ops",
                "{{type}}",
            ),
            ("Telemetry target health", 'up{job="firefox-sync"}', "short", "{{pod}}"),
            (
                "Bridge resident memory",
                'process_resident_memory_bytes{job="firefox-sync"}',
                "bytes",
                "{{pod}}",
            ),
        ],
    )
)

names.append(
    dashboard(
        "mastodon-metrics",
        "Mastodon Application Metrics",
        (
            "Native web/Puma and embedded Sidekiq metrics, plus read-only"
            " Sidekiq queue counts and waiting age from Valkey. Retry/dea"
            "d sets retain failures; they are not new-failure counters."
        ),
        [
            (
                "Web requests by status",
                (
                    'sum by (status) (rate(ruby_http_requests_total{job="mastodon'
                    '"}[$__rate_interval]))'
                ),
                "ops",
                "{{status}}",
            ),
            (
                "Puma request backlog",
                'sum by (pod) (ruby_puma_request_backlog{job="mastodon"})',
                "short",
                "{{pod}}",
            ),
            (
                "Puma thread pool capacity",
                'sum by (pod) (ruby_puma_thread_pool_capacity{job="mastodon"})',
                "short",
                "{{pod}}",
            ),
            ("Sidekiq busy workers", 'sidekiq_process_busy{job="mastodon"}', "short", "{{pod}}"),
            (
                "Sidekiq concurrency",
                'sidekiq_process_concurrency{job="mastodon"}',
                "short",
                "{{pod}}",
            ),
            (
                "Web database connections waiting",
                'sum by (pod) (ruby_active_record_connection_pool_waiting{job="mastodon"})',
                "short",
                "{{pod}}",
            ),
            (
                "Sidekiq database connections waiting",
                'sum by (pod) (active_record_connection_pool_waiting{job="mastodon"})',
                "short",
                "{{pod}}",
            ),
            ("Web and Sidekiq targets", 'up{job="mastodon"}', "short", "{{pod}}"),
            ("Waiting jobs by queue", "mastodon_queue_waiting_jobs", "short", "{{queue}}"),
            ("Oldest waiting job age", "mastodon_queue_oldest_age_seconds", "s", "{{queue}}"),
            ("Retry set", "mastodon_retry_jobs", "short", "retrying jobs"),
            ("Dead set (retained)", "mastodon_dead_jobs", "short", "dead jobs"),
            ("Scheduled jobs", "mastodon_scheduled_jobs", "short", "scheduled"),
            (
                "Queue collector result (1 = success)",
                'redis_script_result{job="valkey-mastodon"}',
                "short",
                "collector",
            ),
        ],
    )
)

names.append(
    dashboard(
        "immich-metrics",
        "Immich Application Metrics",
        (
            "Native API/worker telemetry plus read-only BullMQ waiting, a"
            "ctive, paused, delayed and retained-failure counts. Waiting "
            "includes prioritized jobs. Failed counts are retained jobs, "
            "not new-failure rates. Missing collection remains no data."
        ),
        [
            ("Telemetry endpoint health", 'up{job="immich"}', "short", "{{instance}}"),
            ("Process memory", 'process_memory_usage{job="immich"}', "bytes", "{{instance}}"),
            (
                "Process CPU utilization",
                '100 * process_cpu_utilization{job="immich"}',
                "percent",
                "{{instance}} / {{process_cpu_state}}",
            ),
            (
                "Active jobs by queue",
                'sum by (__name__) ({job="immich",__name__=~"immich_queues_.*_active"})',
                "short",
                "{{__name__}}",
            ),
            (
                "Worker job runs",
                (
                    'sum(rate(immich_job_repository_run_duration_count{job="immic'
                    'h"}[$__rate_interval]))'
                ),
                "ops",
                "runs",
            ),
            (
                "Asset creation calls",
                (
                    'sum(rate(immich_asset_repository_create_duration_count{job="'
                    'immich"}[$__rate_interval]))'
                ),
                "ops",
                "calls",
            ),
            ("Waiting jobs by queue", 'immich_queue_jobs{state="waiting"}', "short", "{{queue}}"),
            ("Active queued jobs", 'immich_queue_jobs{state="active"}', "short", "{{queue}}"),
            ("Retained failed jobs", 'immich_queue_jobs{state="failed"}', "short", "{{queue}}"),
            ("Paused jobs", 'immich_queue_jobs{state="paused"}', "short", "{{queue}}"),
            ("Delayed jobs", 'immich_queue_jobs{state="delayed"}', "short", "{{queue}}"),
            (
                "Queue collector result (1 = success)",
                'redis_script_result{job="valkey-immich"}',
                "short",
                "collector",
            ),
        ],
    )
)

names.append(
    dashboard(
        "meilisearch-metrics",
        "Meilisearch Metrics",
        (
            "Karakeep search-engine telemetry, collected with a metrics.g"
            "et-only API key. Request panels exclude the metrics endpoint"
            " itself."
        ),
        [
            ("Database size", 'meilisearch_db_size_bytes{job="meilisearch"}', "bytes", "allocated"),
            (
                "Used database size",
                'meilisearch_used_db_size_bytes{job="meilisearch"}',
                "bytes",
                "used",
            ),
            (
                "Documents by index",
                'meilisearch_index_docs_count{job="meilisearch"}',
                "short",
                "{{index}}",
            ),
            (
                "HTTP requests excluding scrapes",
                (
                    'sum by (status) (rate(meilisearch_http_requests_total{job="m'
                    'eilisearch",path!="/metrics"}[$__rate_interval]))'
                ),
                "ops",
                "{{status}}",
            ),
            (
                "HTTP p95 latency excluding scrapes",
                (
                    "histogram_quantile(0.95, sum by (le) (rate(meilisearch_http_"
                    'response_time_seconds_bucket{job="meilisearch",path!="/metri'
                    'cs"}[$__rate_interval])))'
                ),
                "s",
                "p95",
            ),
            (
                "Search queue size",
                'meilisearch_search_queue_size{job="meilisearch"}',
                "short",
                "searches",
            ),
            (
                "Task queue latency",
                'meilisearch_task_queue_latency_seconds{job="meilisearch"}',
                "s",
                "latency",
            ),
            (
                "Tasks by kind and state",
                'meilisearch_nb_tasks{job="meilisearch"}',
                "short",
                "{{kind}} / {{value}}",
            ),
        ],
    )
)

names.append(
    dashboard(
        "open-webui-metrics",
        "Open WebUI Metrics",
        (
            "Native OTLP metrics only: HTTP throughput/latency and aggreg"
            "ate user counts. Tracing and OTLP logs are disabled. OTLP is"
            " push-based and therefore has no scrape up metric; sample ag"
            "e shows export freshness."
        ),
        [
            (
                "HTTP requests by status",
                (
                    "sum by (http_status_code) (rate(http_server_requests_total{j"
                    'ob="open-webui"}[$__rate_interval]))'
                ),
                "ops",
                "{{http_status_code}}",
            ),
            (
                "HTTP p95 duration",
                (
                    "histogram_quantile(0.95, sum by (le) (rate(http_server_durat"
                    'ion_milliseconds_bucket{job="open-webui"}[$__rate_interval])'
                    ")) / 1000"
                ),
                "s",
                "p95",
            ),
            (
                "HTTP mean duration",
                (
                    'sum(rate(http_server_duration_milliseconds_sum{job="open-web'
                    'ui"}[$__rate_interval])) / sum(rate(http_server_duration_mil'
                    'liseconds_count{job="open-webui"}[$__rate_interval])) / 1000'
                ),
                "s",
                "mean",
            ),
            ("Registered users", 'webui_users_total{job="open-webui"}', "short", "users"),
            ("Active users", 'webui_users_active{job="open-webui"}', "short", "users"),
            ("Active users today", 'webui_users_active_today{job="open-webui"}', "short", "users"),
            (
                "Native export sample age",
                'time() - max(timestamp(http_server_requests_total{job="open-webui"}))',
                "s",
                "age",
            ),
            ("Active OTLP instances", 'count(target_info{job="open-webui"})', "short", "instances"),
        ],
    )
)

names.append(
    dashboard(
        "hister-metrics",
        "Hister Metrics",
        (
            "Authenticated native search/index metrics. Size/document gau"
            "ges refresh in the background. Search/index latency and coun"
            "ters need activity before yielding meaningful values."
        ),
        [
            ("Metrics target health", 'up{job="hister"}', "short", "target"),
            (
                "Indexed documents",
                'hister_index_document_count{job="hister"}',
                "short",
                "documents",
            ),
            ("Datastore size", 'hister_datastore_size_bytes{job="hister"}', "bytes", "size"),
            (
                "Documents indexed by type",
                (
                    'sum by (type) (rate(hister_documents_indexed_total{job="hist'
                    'er"}[$__rate_interval]))'
                ),
                "ops",
                "{{type}}",
            ),
            (
                "Search p95 latency",
                (
                    "histogram_quantile(0.95, sum by (le) (rate(hister_search_dur"
                    'ation_seconds_bucket{job="hister"}[$__rate_interval])))'
                ),
                "s",
                "p95",
            ),
            (
                "Indexing p95 latency",
                (
                    "histogram_quantile(0.95, sum by (le) (rate(hister_indexing_d"
                    'uration_seconds_bucket{job="hister"}[$__rate_interval])))'
                ),
                "s",
                "p95",
            ),
        ],
    )
)

names.append(
    dashboard(
        "spotify-metrics",
        "Your Spotify Metrics",
        (
            "Authenticated native server/runtime metrics. HTTP/import/ing"
            "estion counters are event-dependent and may be absent until "
            "the first event after restart. Empty counters are not presen"
            "ted as successful zeros."
        ),
        [
            ("Metrics target health", 'up{job="spotify"}', "short", "target"),
            ("Resident memory", 'process_resident_memory_bytes{job="spotify"}', "bytes", "memory"),
            (
                "Process CPU cores",
                'rate(process_cpu_seconds_total{job="spotify"}[$__rate_interval])',
                "cores",
                "CPU",
            ),
            ("Node.js used heap", 'nodejs_heap_size_used_bytes{job="spotify"}', "bytes", "heap"),
            (
                "Node.js event loop p99",
                'nodejs_eventloop_lag_p99_seconds{job="spotify"}',
                "s",
                "p99",
            ),
            (
                "Application HTTP requests",
                'sum(rate(http_requests_total{job="spotify"}[$__rate_interval]))',
                "ops",
                "requests",
            ),
            (
                "Tracks ingested",
                'sum(rate(ingested_tracks_total{job="spotify"}[$__rate_interval]))',
                "ops",
                "tracks",
            ),
            (
                "Imports in 24 hours",
                'sum(increase(imports_total{job="spotify"}[24h]))',
                "short",
                "imports",
            ),
        ],
    )
)

names.append(
    dashboard(
        "mail-queues",
        "Mail Delivery Queues",
        (
            "Read-only Postfix queue counts and oldest initial-arrival ag"
            "e. Held mail is separate from delivery backlog. No mail cont"
            "ent or addresses are exported. Missing collection is not an "
            "empty queue."
        ),
        [
            (
                "Messages by queue",
                'postfix_queue_messages{job="postfix-queue"}',
                "short",
                "{{queue}}",
            ),
            (
                "Oldest message arrival age by queue",
                'postfix_queue_oldest_age_seconds{job="postfix-queue"}',
                "s",
                "{{queue}}",
            ),
            (
                "Queue collection successful",
                'postfix_queue_scrape_success{job="postfix-queue"}',
                "short",
                "collection",
            ),
            ("Exporter reachable", 'up{job="postfix-queue"}', "short", "target"),
        ],
    )
)

if __name__ == "__main__":
    print("\n".join(names))
