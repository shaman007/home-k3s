#!/usr/bin/env python3
"""Generate the security overview from existing Prometheus and sanitized Loki sources."""
import json
from pathlib import Path

from dashboard_builder import DS, query_variable

ROOT = Path(__file__).resolve().parents[2]
LOKI = {"type": "loki", "uid": "db1b23ef-7ce7-4bb2-b0b6-998c13754cfd"}
CREDENTIAL_ERRORS = "invalid_user_credentials|user_not_found|user_disabled|user_temporarily_disabled"
AUDIT = '{job="kubernetes-audit",node=~"${node:regex}",detection=~"${audit_detection:regex}",outcome=~"${outcome:regex}"}'
FALCO = '{job="falco",hostname=~"${node:regex}",rule=~"${falco_rule:regex}"}'
PANELS = []


def panel(title, expr, x, y, w=12, h=8, kind="timeseries", ds=None,
          legend="", description="", unit="short"):
    """Build a panel with explicit data source and bounded default log volume."""
    ds = ds or DS
    target = {"refId": "A", "expr": expr, "datasource": ds}
    if kind in ("stat", "table"):
        target.update(instant=True, range=False)
    else:
        target["range"] = True
    if ds["type"] == "loki":
        target.update(queryType="instant" if kind in ("stat", "table") else "range", maxLines=200)
    if kind == "table":
        target["format"] = "table"
    target["legendFormat"] = legend
    p = {"id": len(PANELS) + 1, "title": title, "description": description,
         "type": kind, "datasource": ds,
         "gridPos": {"x": x, "y": y, "w": w, "h": h}, "targets": [target],
         "fieldConfig": {"defaults": {"unit": unit, "noValue": "No data",
             "color": {"mode": "palette-classic"}}, "overrides": []},
         "options": {"legend": {"displayMode": "table", "placement": "bottom", "calcs": ["lastNotNull"]},
                     "tooltip": {"mode": "multi"}}}
    if kind == "stat":
        p["options"] = {"colorMode": "value", "graphMode": "none",
                        "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}}
    elif kind == "logs":
        p["options"] = {"showTime": True, "showLabels": False, "showCommonLabels": False,
                        "wrapLogMessage": True, "enableLogDetails": True, "sortOrder": "Descending", "dedupStrategy": "none"}
    elif kind == "table":
        p["options"] = {"showHeader": True, "cellHeight": "sm", "sortBy": [{"displayName": "alertname", "desc": False}]}
    if kind == "table" and ds["type"] == "loki":
        p["options"]["sortBy"] = []
    PANELS.append(p)
    return p


def row(title, y):
    """Separate overview, signal families and collection quality."""
    PANELS.append({"id": len(PANELS) + 1, "type": "row", "title": title,
                   "collapsed": False, "panels": [], "gridPos": {"x": 0, "y": y, "w": 24, "h": 1}})


def custom(name, values):
    """Use bounded known classifications; discovery is unnecessary for lazy event labels."""
    return {"name": name, "label": name.replace('_', ' ').title(), "type": "custom",
            "query": ','.join(values), "multi": True, "includeAll": True, "allValue": ".*",
            "current": {"text": "All", "value": "$__all"}, "options": []}


def build():
    """Create one overview without changing existing detection or notification rules."""
    PANELS.clear()
    row("Security overview · collection health", 0)
    health = [
        ("CrowdSec endpoints · expected 2", 'sum(up{job="crowdsec"}) or vector(0)', 2),
        ("Keycloak endpoints · expected 1", 'sum(up{job="keycloak"}) or vector(0)', 1),
        ("Audit nodes · expected all control planes", 'sum(up{job="kubernetes-audit"}) or vector(0)', 3),
        ("Falco nodes · expected all nodes", 'sum(up{job="falco"}) or vector(0)', 3),
    ]
    for i, (title, expr, expected) in enumerate(health):
        p = panel(title, expr, i*6, 1, 6, 4, "stat",
                  description="Global coverage, independent of event filters. Scrape availability alone does not prove ingestion. Current cluster baseline: " + str(expected) + ".")
        p["fieldConfig"]["defaults"].update(color={"mode": "thresholds"}, thresholds={"mode": "absolute", "steps": [{"color": "red", "value": None}, {"color": "green", "value": expected}]})
    panel("Active rules · grouped by API server", 'ALERTS{category="security",alertstate=~"pending|firing"}', 0, 5, 24, 7, "table",
          description="Each row groups events, rather than representing one attack. See actors, actions and targets in the table below. Node identifies the receiving API server; the collector namespace is hidden. Falco sends events directly to Alertmanager and is shown separately.")
    panel("Security alert history · Prometheus", 'max by (alertname,alertstate) (ALERTS{category="security"})', 0, 12, 24, 6,
          legend="{{alertname}} / {{alertstate}}", description="Alert state samples, not an event count. Falco has a separate Loki event history.")
    row("CrowdSec · exploit attempts and sustained scanning", 18)
    panel("Scenario overflows · selected range", 'sum by (name) (increase(cs_bucket_overflowed_total{job="crowdsec"}[$__range]))', 0, 19,
          legend="{{name}}", description="All scenarios for context. Overflows are detections, not requests, unique attackers or successful exploitation.")
    panel("Retained CrowdSec alerts by scenario", 'sum by (reason) (cs_alerts{job="crowdsec"})', 12, 19,
          legend="{{reason}}", description="Current retained alert inventory; not a counter and not new alerts in the selected time range.")
    panel("Exploit and scanning activity", 'sum by (name) (increase(cs_bucket_overflowed_total{job="crowdsec",name=~"crowdsecurity/(http-cve-probing|http-backdoors-attempts|.*[Cc][Vv][Ee].*|http-probing|http-sensitive-files|http-admin-interface-probing)"}[10m]))', 0, 27,
          legend="{{name}}", description="Rolling 10-minute detection counts. Routine scans are reviewed in the daily external-access email, without immediate alerts. Attempts do not prove exploitation; counters retain raw detection context.")
    panel("CrowdSec parsing activity", 'sum by (source) (rate(cs_kubernetessource_hits_total{job="crowdsec"}[$__rate_interval]))', 12, 27,
          legend="{{source}}", unit="ops", description="Useful collection activity, not confirmation that a particular request was classified correctly.")
    row("Keycloak · credential failure bursts", 35)
    keycloak = 'keycloak_user_events_total{job="keycloak",realm=~"${realm:regex}",event="login",error=~"' + CREDENTIAL_ERRORS + '"}'
    panel("Credential failures · selected range", 'sum by (realm,error) (increase(' + keycloak + '[$__range]))', 0, 36,
          legend="{{realm}} / {{error}}", description="Credential/account errors only. Refresh-token failures are excluded; realm totals do not identify a user or attacker.")
    panel("Guessing threshold · failures / 5 minutes", 'sum by (realm) (increase(' + keycloak + '[5m]))', 12, 36,
          legend="{{realm}}", description="Alert threshold: at least 10 failures / 5m, sustained for 1m.")
    row("Kubernetes audit · Secrets, dangerous RBAC, sensitive exec, privileged Pods", 44)
    panel("Audit detections · event count / interval", 'sum by (detection,outcome) (count_over_time(' + AUDIT + '[$__interval]))', 0, 45,
          ds=LOKI, legend="{{detection}} / {{outcome}}", description="Counts persisted sanitized Loki records. Denied, failed and dry-run attempts are not successful changes.")
    panel("Audit events · selected range", 'sum by (detection,outcome) (count_over_time(' + AUDIT + '[$__range]))', 12, 45,
          kind="table", ds=LOKI, legend="{{detection}} / {{outcome}}", description="No data can mean no matching events; check collector health above and below.")
    panel("Audit event details · latest 200", AUDIT + ' | json | line_format "{{.timestamp}} {{.detection}} {{.outcome}} apiserver={{.node}} source_ip={{.source_ip}} actor={{.actor}} impersonated={{.impersonated}} {{.verb}} {{.resource}}/{{.subresource}} namespace={{.namespace}} name={{.name}} code={{.code}} role={{.role_ref}} audit_id={{.audit_id}}"', 0, 53, 24, 10, "logs", LOKI,
          description="Allowlisted audit metadata only; no Secret contents, request/response bodies or exec command arguments. Expand a line for structured fields.")
    row("Falco · terminal shell, new binary, reverse-shell signature", 63)
    panel("Falco detections · event count / interval", 'sum by (rule) (count_over_time(' + FALCO + '[$__interval]))', 0, 64,
          ds=LOKI, legend="{{rule}}", description="Persisted events survive sensor restarts. Shell means a terminal shell; new binary means overlay upper-layer execution; socket redirection is one reverse-shell signature.")
    panel("Falco events · selected range", 'sum by (rule) (count_over_time(' + FALCO + '[$__range]))', 12, 64,
          kind="table", ds=LOKI, legend="{{rule}}", description="No events is different from a missing sensor. Node filter applies to event history, not the global coverage counters.")
    panel("Falco event details · latest 200", FALCO + ' | json | line_format "{{.hostname}} {{.output}}"', 0, 72, 24, 10, "logs", LOKI,
          description="Sanitized Falco output with Pod, executable and container identity; no process command line or environment. Open log details for JSON fields.")
    row("Collection freshness, drops and notification delivery", 82)
    panel("Audit ingestion age by node", 'time() - max by (node) (homelab_audit_last_received_timestamp_seconds{job="kubernetes-audit",node=~"${node:regex}"})', 0, 83,
          unit="s", legend="{{node}}", description="Last raw audit record received; sustained age over 300s raises a health alert. This is not the age of the last detection.")
    panel("Falco syscall activity", 'sum by (node) (rate(falcosecurity_scap_n_evts_total{job="falco",node=~"${node:regex}"}[$__rate_interval]))', 12, 83,
          unit="ops", legend="{{node}}")
    p = panel("Falco lost events / second", 'sum by (node) (rate(falcosecurity_scap_n_drops_total{job="falco",node=~"${node:regex}"}[$__rate_interval]))', 0, 91,
              unit="ops", legend="{{node}} / syscall")
    p['targets'].append({"refId":"B","datasource":DS,"expr":'sum by (node) (rate(falcosecurity_falco_outputs_queue_num_drops_total{job="falco",node=~"${node:regex}"}[$__rate_interval]))',"legendFormat":"{{node}} / output queue","range":True})
    panel("Sidekick deliveries · selected range", 'sum by (destination,status) (increase(falcosecurity_falcosidekick_outputs_total{job="falcosidekick"}[$__range]))', 12, 91,
          legend="{{destination}} / {{status}}", description="Output counters are lazy. Alertmanager acceptance and Loki persistence are separate from recipient delivery; health alerts handle first error samples.")
    panel("Sidekick endpoints · expected 2", 'sum(up{job="falcosidekick"}) or vector(0)', 0, 99, 6, 5, "stat")
    panel("Alertmanager delivery errors · selected range", 'sum by (integration) (increase(alertmanager_notifications_failed_total{integration=~"telegram|email"}[$__range]))', 6, 99, 18, 5,
          legend="{{integration}}", description="Shared notification transport for all alerts, not security-only delivery attribution.")
    # Reserve space for an actionable audit table immediately below rule groups.
    for existing in PANELS:
        if existing['gridPos']['y'] >= 12:
            existing['gridPos']['y'] += 10
    event_expr = ('sum by (node,detection,actor,action,target_namespace,target_name,outcome,source_ip) '
                  '(count_over_time(' + AUDIT + ' | json actor="actor", verb="verb", resource="resource", '
                  'subresource="subresource", target_namespace="namespace", target_name="name", source_ip="source_ip" '
                  '| __error__="" | label_format action="{{.verb}} {{.resource}}{{if .subresource}}/{{.subresource}}{{end}}", '
                  'target_namespace="{{if .target_namespace}}{{.target_namespace}}{{else}}(cluster){{end}}", '
                  'target_name="{{if .target_name}}{{.target_name}}{{else}}(collection){{end}}" [15m]))')
    details = panel("Who did what and where · audit events in the last 15 minutes", event_expr,
                    0, 12, 24, 10, "table", LOKI,
                    description="Events behind active audit alerts, grouped by actor, action and target; the value is the event count. Allowed means API permitted, denied means API rejected, and dry-run means validation without changes. The receiving API server is not necessarily the request source. Source IP is available for new events and may identify a node after NAT. Get reads one object, list retrieves a collection, and watch subscribes to changes. Actor is the authenticated identity, not a proven person or process. These fields are queried from logs without adding Prometheus metric labels.")
    PANELS.insert(6, PANELS.pop())
    groups = next(p for p in PANELS if p['title'] == "Active rules · grouped by API server")
    for table, order, excluded, aliases in [
        (groups, ["alertname","alertstate","node","outcome","name","destination"],
         ["Time","__name__","category","cluster","job","namespace","owner","priority","severity","Value","Value #A"],
         {"alertname":"Detection", "alertstate":"State", "node":"API server / sensor node", "outcome":"Outcome", "name":"Scenario", "destination":"Destination"}),
        (details, ["actor","action","target_namespace","target_name","outcome","detection","node","source_ip","Value #A"], ["Time"],
         {"actor":"Actor", "action":"Action", "target_namespace":"Target namespace", "target_name":"Object / collection", "outcome":"Outcome", "detection":"Detection", "node":"API server", "source_ip":"Source IP", "Value #A":"Events", "Value":"Events"}),
    ]:
        table['transformations'] = [{"id":"organize", "options":{
            "excludeByName": {name:True for name in excluded},
            "indexByName": {name:i for i,name in enumerate(order)}, "renameByName":aliases}}]
        table['options']['sortBy'] = []
    outcomes = {"allowed":{"text":"API allowed"}, "denied":{"text":"API denied"},
                "failed":{"text":"Request failed"}, "dry-run":{"text":"Dry-run only"}}
    detections = {"secret_read":{"text":"Secret access outside reviewed exceptions"},
                  "dangerous_rbac":{"text":"Permission grant / dangerous role"},
                  "sensitive_exec":{"text":"Exec / attach / port-forward"},
                  "privileged_pod":{"text":"Privileged Pod"}}
    for table in [groups, details]:
        table['fieldConfig']['overrides'] = [
            {"matcher":{"id":"byName","options":"Outcome"},"properties":[{"id":"mappings","value":[{"type":"value","options":outcomes}]}]},
        ]
    details['fieldConfig']['overrides'] += [
        {"matcher":{"id":"byName","options":"Actor"},"properties":[{"id":"custom.width","value":320},{"id":"custom.wrapText","value":True}]},
        {"matcher":{"id":"byName","options":"Detection"},"properties":[{"id":"mappings","value":[{"type":"value","options":detections}]}]},
    ]
    groups['fieldConfig']['overrides'] += [
        {"matcher":{"id":"byName","options":"Detection"},"properties":[{"id":"mappings","value":[{"type":"value","options":{
            "KubernetesUnexpectedSecretRead":{"text":"Secret access outside reviewed exceptions"},
            "KubernetesSensitivePodExec":{"text":"Exec / attach / port-forward"},
            "KubernetesDangerousRBAC":{"text":"Permission grant / dangerous role"},
            "KubernetesPrivilegedPod":{"text":"Privileged Pod"},
        }}]}]},
    ]
    return {"uid":"security-overview","title":"Security Overview","description":"CrowdSec, Keycloak, Kubernetes audit and Falco detections with collection and delivery health. Events indicate activity or attempts, not proof of compromise.",
            "schemaVersion":41,"version":1,"editable":True,"tags":["homelab","security"],"refresh":"1m",
            "time":{"from":"now-6h","to":"now"},"timezone":"browser","panels":PANELS,
            "links":[{"title":"CrowdSec details","type":"link","url":"/d/crowdsec-overview/crowdsec","keepTime":True},
                     {"title":"Keycloak details","type":"link","url":"/d/keycloak-events-only2/keycloak-events","keepTime":True},
                     {"title":"Alertmanager","type":"link","url":"https://alerts.int.andreybondarenko.com","targetBlank":True}],
            "templating":{"list":[query_variable("node","label_values(kube_node_info, node)"),query_variable("realm",'label_values(keycloak_user_events_total{job="keycloak"}, realm)'),
                custom("audit_detection",["secret_read","dangerous_rbac","sensitive_exec","privileged_pod"]),custom("outcome",["allowed","denied","failed","dry-run"]),
                custom("falco_rule",["Terminal shell in container","Drop and execute new binary in container","Redirect STDOUT/STDIN to Network Connection in Container"])]}}


def main():
    """Write the provisioned dashboard ConfigMap."""
    text = json.dumps(build(), indent=2, ensure_ascii=False)
    dest = ROOT / 'metrics/grafana/config-map-grafana-dashboard-security-overview.yaml'
    dest.write_text('---\napiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: grafana-dashboard-security-overview\n  namespace: monitoring\ndata:\n  security-overview.json: |-\n' + '\n'.join('    '+line for line in text.splitlines()) + '\n')
    print(dest)


if __name__ == '__main__':
    main()
