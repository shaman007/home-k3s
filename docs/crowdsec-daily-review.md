# CrowdSec daily security review

Ordinary CVE probes and sustained HTTP scans are background traffic. They no
longer create immediate Prometheus alerts. CrowdSec detection, short bans, raw
Traefik/agent logs and Grafana scenario graphs remain enabled. Collection-health
alerts and Keycloak/Kubernetes/Falco detections are unchanged.

The existing external-access daily email runs at 06:20 Europe/Prague and covers
the previous local calendar day. Its plain-text and HTML versions include a
CrowdSec review: scenario detection counts, source IPs, top targets without query
strings, response codes and triage. It uses Loki with existing access and mail
configuration; there is no new recipient, credential or notification channel.
Counts are detections, not individual requests, unique attackers or breaches.

Only the known Traefik `.env` blackhole router or explicit `noop@internal`
service identifies ignored traffic. HTTP 403/404 alone never does. The external
access totals omit these requests. The CrowdSec summary omits an IP's detections
only if all its observed HTTP requests in its scenario time windows hit a known blackhole.
Mixed traffic stays visible. With no matching logs the outcome remains unknown.
This conservative IP/time-window correlation may retain some blackhole noise; it never
claims exact per-detection attribution. Raw scenario dashboard counters remain
unfiltered for investigation.

Rejected responses alone are described as background/rejected activity, not as
proof of a successful attack. 2xx/3xx/5xx responses require review but also do not
prove exploitation. CrowdSec ban enforcement is not inferred from these logs.
The current inspection found no `.env` blackhole access logs in the last day, so
blackhole classification is covered by representative fixtures, not a live hit.

Validate with `python3 -m unittest tests.test_crowdsec_daily_review` and
`python3 tests/run_monitoring_alert_tests.py /path/to/promtool`. Publish the
Prometheus ConfigMap, report ConfigMap, dashboard source/generated ConfigMap,
fixtures and this documentation together. Argo CD reconciles the changes; verify
loaded rule removal and the next delivered email after publication. Existing
firing alerts can remain until their normal expiry after the rules are removed.
