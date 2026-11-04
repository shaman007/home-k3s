# Cluster monitoring alerts

Implemented from the 2026-11-04 audit at the user's request. Prometheus rules and inventory are owned by `metrics/kubernetes-prometheus/config-map-prometheus-server-conf.yaml`; email routing is in the adjacent Alertmanager ConfigMap. Critical HTTPS probes are configured in `connectivity-exporter/config-map-connectivity-exporter-config.yaml`.

The set retains 21 existing alerts (correcting OpenBao selectors, memory/load/filesystem calculations and pod readiness) and adds 55 alerts. All have owner `homelab`, a runbook link, and warning/critical priority. Existing email destination and transport are retained. Warnings repeat every four hours; critical notifications repeat every thirty minutes. Group wait is ten seconds and group interval five minutes. Email delivery is not an independent monitoring channel: a completely failed Prometheus/Alertmanager/mail stack cannot report its own outage through itself.

## Coverage and thresholds

- Expected scrape inventory covers configured cluster jobs; the intentionally optional Fedora desktop is excluded. `TargetDown` detects discovered but unreachable targets; inventory detects wholly missing jobs after ten minutes. Workload replica deficit rules detect partial replica loss. Update inventory when intentionally adding/removing a job.
- OpenBao: actual `openbao` job and `vault_core_unsealed`; missing/down target and sealed state are critical. These metrics cover the exposed endpoint, while StatefulSet readiness covers all replicas.
- Alert pipeline: notification errors/drops, missing discovery and fewer than three Alertmanager peers. Counter failures require persistence to avoid transient restart noise.
- Certificates: less than fourteen days remaining, or fifteen minutes not ready. External Secrets/SecretStores: ten minutes not ready, or more than five reconcile errors in fifteen minutes. Controller replicas are deduplicated.
- Workloads: fifteen-minute desired/available deficits, deployment progress failure, running unready pods excluding terminating pods and Job-owned pods. Argo unhealthy/failed sync for fifteen minutes, OutOfSync for thirty minutes. Deliberate maintenance should use a time-bounded Alertmanager silence.
- Storage: PVC warning above 85% through 95%; existing above-95% critical retained. Inodes above 90%; prediction requires six hours of data, usage above 70% and one hour of sustained forecast exhaustion within 24 hours. Longhorn degraded redundancy for fifteen minutes, faulted for five minutes.
- Backups: existing two-hour Talos protection retained. Longhorn daily backups permit thirty hours, monthly backups thirty-five days. Missing schedules, never-successful runs, suspension and stale successes are distinct. Suspended jobs do not generate the stale-success alert. Inventory names follow the eight deployed backup CronJobs; update it with schedule changes.
- Databases: Redis/Valkey down, rejected connections, more than one hundred evictions per fifteen minutes, configured memory limit above 90% (unlimited memory excluded). PostgreSQL/MySQL connections above 80%; PostgreSQL replica lag above sixty seconds only on replicas. Existing server-down rules retained.
- Ingress: service 5xx fraction above 5%, p95 latency above three seconds; both require at least one hundred requests per ten minutes. Independent HTTPS probes from the connectivity-exporter check SSO OpenID discovery, Harbor ping and Mastodon health, including certificate verification and exact HTTP 200. Failure or missing probe persists ten minutes. These are in-cluster probes of public routes, not an external Internet vantage point.
- Monitoring: rule evaluation, TSDB/WAL, Thanos upload/halted compaction, Loki discard/WAL and Alloy config/log-drop failures.
- Networking: CoreDNS SERVFAIL above 5% or p99 latency above one second, minimum one hundred responses/requests per ten minutes. Hubble loss above one event per second. MetalLB stale configuration or a LoadBalancer service lacking an address for ten minutes. Pool fullness alone is deliberately not an alert: reserved pools are fully allocated by design. FRR/BGP is retired. Normal Cilium policy-denied traffic is not treated as a network outage.
- Applications/GPU: Harbor queue above one hundred tasks; GPU temperature above a conservative operational warning threshold of 85 C (not a claim about its hardware maximum), remap failures/uncorrectable remapped rows, missing GPU telemetry, and container restarts after OOM kills. GPU utilization alone does not page.

## Triage

1. Check the alert's resource labels and current Prometheus expression; compare the dashboard and recent changes. Inspect `up`, rule health and data freshness before treating missing data as application failure.
2. Inspect the owning GitOps folder and Argo application, then Kubernetes readiness/events/logs. Use read-only diagnostics first. For certificate warnings, inspect issuer/renewal status; do not manually replace secrets or keys from an alert alone.
3. For capacity, inspect growth, replicas and backup health before expanding or deleting anything. For Longhorn faults, inspect volume/replica/node health; never delete PVCs or replica data as an initial response.
4. For notification failures, inspect Prometheus notification counters, Alertmanager peers and email errors, then mail delivery logs. A successful rule evaluation does not prove delivered mail. Test delivery through a short-lived controlled alert only when explicitly authorized.
5. During planned work, create a narrow, expiring silence and verify recovery before it expires. Do not disable rules or change desired replicas merely to clear an alert.

## Instrumentation gaps

External Home Assistant remains outside the agreed cluster scope. The receiving rsync daemon has no successful-backup timestamp; no freshness rule can establish externally initiated backup success. Mail queue depth/age, Mastodon Sidekiq waiting/retry depth and Immich pending/failed queues are not exported by the installed collectors. Immich active jobs are not a backlog metric. These need instrumentation before useful rules can be added. No dummy always-empty alerts were installed for those signals. Driver-specific GPU faults require an actual exported fault signal; generic container OOM and remap telemetry are covered.

## Validation

Run `python tests/run_monitoring_alert_tests.py /path/to/promtool` with PyYAML and the running Prometheus version's promtool. This extracts actual shipped rules, checks syntax/duplicates, and exercises synthetic healthy/failing conditions, zero-limit Redis, missing versus down jobs, Job/terminating-pod exclusions, monthly backup timing, minimum ingress traffic and assigned/unassigned LoadBalancer addresses. Alertmanager configuration is separately checked with the running version's amtool. Live preflight evaluates every alert expression and records genuine baseline warnings before rollout. Recheck loaded rules, evaluation health, target health, probe samples and Argo reconciliation after deployment.
