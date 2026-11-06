# Cluster monitoring alerts

Implemented from the 2026-11-04 audit at the user's request. Prometheus rules and inventory are owned by `metrics/kubernetes-prometheus/config-map-prometheus-server-conf.yaml`; email routing is in the adjacent Alertmanager ConfigMap. Critical HTTPS probes are configured in `connectivity-exporter/config-map-connectivity-exporter-config.yaml`.

The set retains 21 existing alerts (correcting OpenBao selectors, memory/load/filesystem calculations and pod readiness) and adds 55 alerts. All have owner `homelab`, a runbook link, and warning/critical priority. Existing email destination and transport are retained. Warnings repeat every four hours; critical notifications repeat every thirty minutes. Group wait is ten seconds and group interval five minutes. Email delivery is not an independent monitoring channel: a completely failed Prometheus/Alertmanager/mail stack cannot report its own outage through itself.

## Coverage and thresholds

- Expected scrape inventory covers configured cluster jobs; the intentionally optional Fedora desktop is excluded. `TargetDown` detects discovered but unreachable targets; inventory detects wholly missing jobs after ten minutes. Workload replica deficit rules detect partial replica loss. Update inventory when intentionally adding/removing a job.
- OpenBao: actual `openbao` job and `vault_core_unsealed`; missing/down target and sealed state are critical. These metrics cover the exposed endpoint, while StatefulSet readiness covers all replicas.
- Alert pipeline: notification errors/drops, missing discovery and fewer than three Alertmanager peers. Counter failures require persistence to avoid transient restart noise.
- Certificates: less than five days remaining, or fifteen minutes not ready. External Secrets/SecretStores: ten minutes not ready, or more than five reconcile errors in fifteen minutes. Controller replicas are deduplicated.
- Workloads: fifteen-minute desired/available deficits, deployment progress failure, running unready pods excluding terminating pods and Job-owned pods. Argo unhealthy/failed sync for fifteen minutes, OutOfSync for thirty minutes. Deliberate maintenance should use a time-bounded Alertmanager silence.
- Storage: PVC warning above 85% through 95%; existing above-95% critical retained. Inodes above 90%; prediction requires six hours of data, usage above 70% and one hour of sustained forecast exhaustion within 24 hours. Longhorn degraded redundancy for fifteen minutes, faulted for five minutes.
- Backups: existing two-hour Talos protection retained. Longhorn daily backups permit thirty hours, monthly backups thirty-five days. Missing schedules, never-successful runs, suspension and stale successes are distinct. Suspended jobs do not generate the stale-success alert. Inventory names follow the eight deployed backup CronJobs; update it with schedule changes.
- Databases: Redis/Valkey down, rejected connections, more than one hundred evictions per fifteen minutes, configured memory limit above 90% (unlimited memory excluded). PostgreSQL/MySQL connections above 80%; PostgreSQL replica lag above sixty seconds only on replicas. Existing server-down rules retained.
- Ingress: service 5xx fraction above 5%, p95 latency above three seconds; both require at least one hundred requests per ten minutes. Independent HTTPS probes from the connectivity-exporter check SSO OpenID discovery, Harbor ping and Mastodon health, including certificate verification and exact HTTP 200. Failure or missing probe persists ten minutes. The exporter Deployment explicitly loads the mounted configuration because the image entrypoint otherwise selects its bundled file. These are in-cluster probes of public routes, not an external Internet vantage point.
- Monitoring: rule evaluation, TSDB/WAL, Thanos upload/halted compaction, Loki discard/WAL and Alloy config/log-drop failures.
- Networking: CoreDNS SERVFAIL above 5% or p99 latency above one second, minimum one hundred responses/requests per ten minutes. Hubble loss above one event per second. MetalLB stale configuration or a LoadBalancer service lacking an address for ten minutes. Pool fullness alone is deliberately not an alert: reserved pools are fully allocated by design. FRR-K8s IPv4 BGP coverage is described below. Normal Cilium policy-denied traffic is not treated as a network outage.
- Applications/GPU: Harbor queue above one hundred tasks; GPU temperature above a conservative operational warning threshold of 85 C (not a claim about its hardware maximum), remap failures/uncorrectable remapped rows, missing GPU telemetry, and container restarts after OOM kills. GPU utilization alone does not page.

## BGP

Added 2026-11-06 after the production UDM BGP rollout. The existing authenticated
`metallb` scrape job already collects controller/speaker 9120, FRR controller
9140 and FRR metrics 9141; all ten targets were healthy during verification.
The nine new alerts retain the existing email receiver and priority routing.

- `BGPNeighborUnavailable`: warning after two minutes of a down or missing UDM
  session on an expected FRR node. Expected nodes come from Pod/DaemonSet
  ownership in kube-state-metrics. Other healthy MetalLB targets cannot mask it.
- `BGPServiceRouteUnavailable`: critical after two minutes without an IPv4
  advertisement for an assigned production address on a node with an
  established UDM session. A different node's session, L2 announcement or IPv6
  announcement cannot satisfy this join. Scope is `.210`, `.211`, `.213`.
- `FRRConfigUnavailable`: warning after five minutes of stale, unloaded or
  missing FRR controller configuration telemetry on an expected node.
- `BGPPrefixAdvertisementMismatch`: warning after five minutes when FRR's
  advertised-prefix gauge is missing or differs from the local speaker's
  unique IPv4 address count. Despite its `_total` suffix, do not rate this
  gauge. Expected counts follow service endpoints, not a fixed three per node;
  IPv6 intent is excluded because IPv6 uses L2.
- `BGPUnexpectedReceivedRoutes`: warning after five minutes of nonzero received
  prefixes; the cluster should accept no UDM routes.

Router-side collection runs as a read-only sidecar on the existing UniFi poller,
using its existing Secret without new Kubernetes permissions. The collector
reads the neighbor and forwarding-table APIs every 45 seconds, exposes 9131,
and is scraped as `unifi-bgp`. The existing local-controller TLS exception is
explicit; credentials and cookies remain in memory and are never exported.
Its security context is non-root, read-only-root, RuntimeDefault, drop-ALL, with
32Mi requested/64Mi limited memory and no CPU limit. Metrics access is limited
to monitoring; outbound access remains the existing controller HTTPS allowance.

- `UDMBGPCollectionUnavailable`: warning after five minutes of failed, missing
  or stale collection (last success over 120 seconds old). Collection failures
  do not re-export cached route health and cannot create route-missing alarms.
- `UDMBGPRouteMissing`: critical after two minutes without an installed active
  reviewed Kubernetes next hop for a production /32, gated on successful API
  collection. This catches router rejection even when FRR remains established.
- `UDMBGPPeerUnavailable`: warning after two minutes of a missing/down/wrong-AS
  peer reported by the router, gated on successful collection.
- `UDMBGPPolicyViolation`: critical after two minutes of unexpected peers,
  prefixes, active next hops, remote ASNs, or nonzero UDM route exports.

The collector intentionally expects only the three reviewed node IPs and three
production /32s. Update its `PEERS`/`PREFIXES` inventory alongside the router
payload when adding nodes or VIPs; a unit test checks they match. Regenerate
its ConfigMap with `python tools/monitoring/generate-unifi-bgp-exporter.py`.

The provisioned Cluster Network Metrics dashboard (`network-metrics`) shows
local and router sessions, intended prefixes/paths, installed UDM next hops,
collection freshness, config health, route exchange and policy violations. Missing series remain absent, rather than synthetic zeroes.

First inspect `up{job="metallb"}` on 9140/9141, session/config metrics, MetalLB
ConfigurationStates, ready EndpointSlices and FRR reloader logs. Then inspect
UDM neighbors and its `/32` route table. Traefik services currently have two
eligible nodes each; backup-rsync has one. Do not withdraw the last backup path
or restart nodes merely to test an alert.

Router telemetry now checks installed forwarding entries as well as FRR intent;
HTTPS probes alone can still succeed via retained L2. These checks establish
control-plane route state, not packet delivery through every application or
survival of established connections. Email routing is unchanged and inbox
delivery was not retested. No production routing fault or test email was
injected. Twenty-three rule fixtures cover failures, missing telemetry,
wrong-node joins, L2/IPv6 masking, route rejection, API failures and hold periods.
Collector unit tests check missing routes, active next hops, unexpected policy,
malformed data, read-only endpoints, redirect rejection and generated source.

Live verification on 2026-11-06: all nine alerts loaded, healthy/inactive; ten
MetalLB/FRR targets up; three local sessions; successful UDM collection with
2/2/1 installed next hops, three router peers, zero exports and zero violations.
The dashboard was re-read through Grafana's API. Prometheus used hot reload;
its original Pod remained running and the reloader annotation was restored.

The uncommitted live rollout temporarily holds `kubernetes-prometheus`,
`grafana` and `unifi-exporter` auto-sync and excludes only their application
manifests from the parent. After the matching source is committed/pushed and
verified, restore their original automatic policies and remove those three
parent exclusions, retaining the pre-existing hypermind/omni/strata exclusions.
The new narrow egress policy is live and will be adopted by the updated
`monitoring-network-policy` application include list when the source lands.
No commit or push was performed by the assistant.

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
