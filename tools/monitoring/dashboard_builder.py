"""Build shared Grafana panel, variable and ConfigMap structures for GitOps dashboards."""

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
