# Security Overview

Dashboard: https://grafana.int.andreybondarenko.com/d/security-overview/security-overview

One dashboard combines CrowdSec exploit/scanning detections, Keycloak credential
failure bursts, four Kubernetes audit detections and three Falco runtime rules.
It uses the existing Thanos and Loki data sources; no new exporter, permissions
or notification route is required.

The top section shows global endpoint coverage, active Prometheus security
alerts and their history. Falco sends events directly to Alertmanager, so its
history is shown in the Falco section using persisted Loki records, rather than
Prometheus ALERTS. Coverage cards are global and do not change with event filters.

Filters: node, Keycloak realm, audit detection/outcome and Falco rule. Node applies
to audit/Falco events and per-node collection metrics; realm applies to Keycloak;
audit/Falco classification filters apply only to their own event panels. Links
open the existing detailed CrowdSec/Keycloak dashboards and Alertmanager.

Audit details show actor, impersonation, target, verb, response code and audit ID
from the collector's sanitized records. Allowed, denied, failed and dry-run are
kept distinct. Falco details show its sanitized output. Neither query adds raw
exec command arguments, environment or Secret contents. Latest-event panels are
limited to 200 records; use Explore for a longer investigation.

No data is not a clean security verdict. Check endpoint coverage, audit ingestion
age, Falco syscall activity/drops, Sidekick health and delivery errors. Detection
counters may be lazy and reset; Loki event history is used for audit/Falco counts.
CrowdSec overflows are scenario detections, not requests or unique attackers;
`cs_alerts` is current retained inventory grouped by `reason`, not a new-event
counter. Keycloak realm totals do not attribute failures to an IP/user. Reverse
shell coverage is a socket-redirection signature, not every reverse shell.
Shared Alertmanager error metrics are not security-only delivery attribution.

## Source and publication

Generate the ConfigMap with:

```sh
python3 tools/monitoring/generate_security_dashboard.py
```

Source: `tools/monitoring/generate_security_dashboard.py`.
Output: `metrics/grafana/config-map-grafana-dashboard-security-overview.yaml`.
The projected dashboard volume in `metrics/grafana/deployment-grafana.yaml`
includes this ConfigMap. Publish these together. A UI-created dashboard is usable
immediately, but file provisioning becomes authoritative only after Argo applies
the published source. Do not change unrelated dashboards or data sources.

After publication verify `grafana` is Synced/Healthy at the exact commit, the
projected JSON matches the generated dashboard, and the dashboard API reports
`meta.provisioned=true`. Recheck queries through Grafana's datasource proxy and
inspect the browser for rendering/query errors. A ConfigMap or successful save
response alone does not prove the panels display data.
