# Cluster monitoring alerts

Implemented from the 2026-11-04 audit at the user's request. Prometheus rules and inventory are owned by `metrics/kubernetes-prometheus/config-map-prometheus-server-conf.yaml`; email routing is in the adjacent Alertmanager ConfigMap. Critical HTTPS probes are configured in `connectivity-exporter/config-map-connectivity-exporter-config.yaml`.

The set retains 21 existing alerts (correcting OpenBao selectors, memory/load/filesystem calculations and pod readiness) and adds 55 alerts. All have owner `homelab`, a runbook link, and warning/critical priority. Existing email destination and transport are retained. Warnings repeat every four hours; critical notifications repeat every thirty minutes. Group wait is ten seconds and group interval five minutes. Email delivery is not an independent monitoring channel: a completely failed Prometheus/Alertmanager/mail stack cannot report its own outage through itself.

## Coverage and thresholds

- Expected scrape inventory covers configured cluster jobs; the intentionally optional Fedora desktop is excluded. `TargetDown` detects discovered but unreachable targets; inventory detects wholly missing jobs after ten minutes. Workload replica deficit rules detect partial replica loss. Update inventory when intentionally adding/removing a job.
- OpenBao: actual `openbao` job and `vault_core_unsealed`; missing/down target and sealed state are critical. These metrics cover the exposed endpoint, while StatefulSet readiness covers all replicas.
- Alert pipeline: notification errors/drops, missing discovery and fewer than three Alertmanager peers. Prometheus delivery errors or drops must reach at least three per five-minute window continuously for fifteen minutes; isolated failures age out before firing. Sustained delivery failures retain critical priority.
- Certificates: less than five days remaining, or fifteen minutes not ready. External Secrets/SecretStores: ten minutes not ready, or more than five reconcile errors in fifteen minutes. Controller replicas are deduplicated.
- Workloads: fifteen-minute desired/available deficits, deployment progress failure, running unready pods excluding terminating pods and Job-owned pods. Argo unhealthy/failed sync for fifteen minutes, OutOfSync for thirty minutes. Deliberate maintenance should use a time-bounded Alertmanager silence.
- Storage: PVC warning above 85% through 95%; existing above-95% critical retained. Inodes above 90%; prediction requires six hours of data, usage above 70% and one hour of sustained forecast exhaustion within 24 hours. Longhorn degraded redundancy for fifteen minutes, faulted for five minutes.
- Backups: existing two-hour Talos protection retained. Longhorn daily backups permit thirty hours, monthly backups thirty-five days. Missing schedules, never-successful runs, suspension and stale successes are distinct. Suspended jobs do not generate the stale-success alert. Inventory names follow the eight deployed backup CronJobs; update it with schedule changes.
- Databases: Redis/Valkey down, rejected connections, more than one hundred evictions per fifteen minutes, configured memory limit above 90% (unlimited memory excluded). PostgreSQL/MySQL connections above 80%; PostgreSQL replica lag above sixty seconds only on replicas. Existing server-down rules retained.
- Ingress: service 5xx fraction above 5% for ten minutes; more than 10% of requests slower than five seconds for thirty minutes. Both require at least one hundred requests per ten minutes. Latency uses the observed `le="5.0"` bucket directly: the coarse 1.2-to-5-second bucket cannot reliably establish a three-second p95 threshold. Long-lived requests still count; inspect their contribution before treating this as application slowness. Independent HTTPS probes from the connectivity-exporter check SSO OpenID discovery, Harbor ping and Mastodon health, including certificate verification and exact HTTP 200. Failure or missing probe persists ten minutes. The exporter Deployment explicitly loads the mounted configuration because the image entrypoint otherwise selects its bundled file. These are in-cluster probes of public routes, not an external Internet vantage point.
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
and is scraped as `unifi-bgp`. Both collectors verify the trusted identity
`unifi.int.andreybondarenko.com`; credentials and cookies remain in memory and
are never exported.
Each attempt writes a structured JSON log with a fixed stage (`login`,
`neighbors`, `routes`, `decode`, `certificate`, `collection`), attempt number,
monotonic duration in seconds, outcome, and a bounded error category on failure.
HTTP attempts also include a numeric status when received and the last phase:
`response` covers connection/TLS and waiting for response headers; `body_json`
covers reading and parsing the body. These logs deliberately omit URLs,
credentials, cookies, headers, response bodies, exception text and tracebacks.
Only the two reviewed GET endpoints retry a timeout, once after a one-second
pause, keeping the existing 15-second socket timeout. Login POSTs, HTTP errors
(including 500), certificate verification errors and invalid JSON are not retried
on this basis. The existing one-time renewal after 401/403 remains separate;
combined with a timeout retry this permits at most three GET attempts per endpoint.
The next poll still starts 45 seconds after collection finishes. A recovered read
contributes fresh data to the current collection; exhausted retries fail collection
and remove route samples as before. Alert expressions and hold times are unchanged.
Its security context is non-root, read-only-root, RuntimeDefault, drop-ALL, with
32Mi requested/64Mi limited memory and no CPU limit. Metrics access is limited
to monitoring; outbound access remains the existing controller HTTPS allowance.

- `UDMBGPCollectionUnavailable`: warning after five minutes of failed, missing
  or stale collection (last success over 120 seconds old). Collection failures
  do not re-export cached route health and cannot create route-missing alarms.
- `UDMConsoleCertificateExpiring`: warning after 30 minutes with less than 21 days
  left on the certificate actually served by the router, gated on successful
  collection. Secret renewal does not update the console; follow the
  [renewal handoff](migrations/unifi-tls/README.md#renewal-and-rollback).
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
its ConfigMap with `python tools/monitoring/generate_unifi_bgp_exporter.py`.

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

External Home Assistant remains outside the agreed cluster scope. The external rsync job is also outside scope; the receiving daemon cannot establish externally initiated backup success. Driver-specific GPU faults require an actual exported fault signal; generic container OOM and remap telemetry are covered.

## Application queues

Prepared locally on 2026-11-06; this section does not establish deployment.

- **Mail:** `postfix-queue` scrapes a non-root sidecar on TCP/9154. It runs `postqueue -j` against the existing showq socket with a read-only spool mount, exports counts and oldest initial-arrival age for active/deferred/incoming/hold/maildrop, and discards addresses, recipients and all other message fields. The Postfix UID/GID is 100:102; no added capabilities or privilege escalation. Failed command execution, invalid records and timeouts produce failed collection or a failed scrape, never invented empty queues. The command has an eight-second timeout and HTTP requests have a ten-second timeout.
- **Mastodon:** the existing Valkey exporter evaluates `mastodon-queues.lua` through `EVAL_RO`. It counts each known/discovered Sidekiq waiting list, reads only the oldest entry to calculate enqueue age, and counts retry/dead/scheduled sorted sets. Only aggregates leave Valkey. Seconds and millisecond enqueue timestamps are supported. Dead jobs and scheduled jobs have dashboard panels; their presence alone does not trigger an alert.
- **Immich:** a Valkey exporter sidecar uses `EVAL_RO` and the 19 installed BullMQ queue names. It reads lengths/cardinalities only, not job hashes or failure messages. Waiting includes prioritized work and excludes the legacy priority marker. Active, paused, delayed and retained failed jobs stay separate. Missing expected queue metadata fails collection; update the queue inventory after an Immich version changes its queue names. Empty list/set keys are valid zeroes only after queue metadata is present.

| Alert | Threshold | Hold |
| --- | --- | --- |
| PostfixQueueMetricsUnavailable, MastodonQueueMetricsUnavailable, ImmichQueueMetricsUnavailable | Missing/down exporter or unsuccessful collector | 10 minutes |
| PostfixQueueBacklog | More than 50 delivery messages, excluding held mail | 15 minutes |
| PostfixQueueOldMail | Oldest delivery message arrival more than 1 hour ago | 15 minutes |
| PostfixQueueHeldMail | Any held message | 30 minutes |
| MastodonQueueBacklog | More than 100 waiting jobs in a queue | 15 minutes |
| MastodonQueueOldJobs | Oldest waiting job over 5 minutes | 15 minutes |
| MastodonRetryBacklog | More than 100 retry jobs | 30 minutes |
| ImmichQueueBacklog | More than 1,000 waiting jobs in a queue | 30 minutes |
| ImmichQueueFailedJobs | Any retained failed job in a queue | 30 minutes |

All use the existing `severity: mail` route with warning priority. These initial operational thresholds allow short bursts and imports; review them against normal workload history. Retained failed jobs are not a new-failure rate. Queue depth is not proof of stuck processing, and active jobs are not backlog. Postfix age measures time since initial arrival, not time spent in the current subqueue.

The **Mail Delivery Queues** dashboard is mounted through Grafana's existing projected dashboard volume. **Mastodon Application Metrics** and **Immich Application Metrics** gain queue panels. Failed or absent collection remains no data, accompanied by collection-health panels and separate availability alerts.

Read-only preflight found no mail backlog or Mastodon waiting/retry jobs. Mastodon retained 1,793 dead jobs and 24 scheduled jobs. Immich retained seven `integrityCheck` failures and one `backgroundTask` failure, with no waiting jobs. Those are pre-existing observations, not failures introduced by the collectors. If unchanged at deployment, the two Immich failure alerts will fire after their hold time. Review them in the admin job view without automatically retrying or deleting anything.

Deployment changes the Postfix Deployment and both Valkey StatefulSet templates. Postfix uses Recreate; adding the sidecars/mounts requires pod replacement and can briefly interrupt mail submission, Mastodon or Immich. Preserve all PVCs and queue data. Publish through the approved GitOps workflow and verify reconciliation, exporter reachability, `redis_script_result == 1`, successful mail queue collection, all six queue recording rules, loaded alerts and Grafana panels over multiple scrapes. No test mail, synthetic production jobs, retries, queue flushing or deletion are needed.

Triage from the queue panel into application/worker logs, dependency health and application administration. Federation retries and bulk imports can be legitimate. Do not clear queues or release held messages merely to silence an alert.

Collector source lives in `tools/monitoring/`; regenerate the three ConfigMaps with `python tools/monitoring/generate_queue_exporters.py`, and check with `--check`. The pinned exporter supports read-only Lua collection and script success metrics; see its [v1.97.0 implementation](https://github.com/oliver006/redis_exporter/blob/v1.97.0/exporter/lua.go). Queue alert fixtures cover normalization, exact thresholds, hold periods, healthy retained/paused/delayed work and absent telemetry. Run them with the existing monitoring alert test command below.

## Validation

Run `python tests/run_monitoring_alert_tests.py /path/to/promtool` with PyYAML and the running Prometheus version's promtool. This extracts actual shipped rules, checks syntax/duplicates, and exercises synthetic healthy/failing conditions, zero-limit Redis, missing versus down jobs, Job/terminating-pod exclusions, monthly backup timing, minimum ingress traffic and assigned/unassigned LoadBalancer addresses. Alertmanager configuration is separately checked with the running version's amtool. Live preflight evaluates every alert expression and records genuine baseline warnings before rollout. Recheck loaded rules, evaluation health, target health, probe samples and Argo reconciliation after deployment.
