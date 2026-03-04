# Grafana Dashboards (Source of Truth Snapshot)

This directory contains exported dashboard JSON from the live Grafana instance.

- Dashboard files: `metrics/grafana/dashboards/live/*.json`
- Inventory index: `metrics/grafana/dashboards/index.json`
- Vendor source manifest: `metrics/grafana/dashboards/sources.json`
- Vendor dashboards (from Grafana.com): `metrics/grafana/dashboards/vendor/*.json`
- Vendor index: `metrics/grafana/dashboards/vendor-index.json`

## Refresh dashboards from Grafana

Run:

```powershell
$env:GRAFANA_TOKEN="<service-account-token>"
powershell -NoProfile -ExecutionPolicy Bypass -File metrics/grafana/tools/export-dashboards.ps1
```

Defaults used by the script:

- URL: `https://grafana.w386.k8s.my.lan`
- TLS: insecure (`-k`)
- Output: `metrics/grafana/dashboards/live`
- Token source: `GRAFANA_TOKEN` environment variable (or `-GrafanaToken`)

Override defaults with parameters:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File metrics/grafana/tools/export-dashboards.ps1 `
  -GrafanaUrl https://grafana.example.com `
  -GrafanaToken <token> `
  -InsecureTls:$false
```

## Sync vendor dashboards from Grafana.com (gnetId)

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File metrics/grafana/tools/sync-vendor-dashboards.ps1
```

This reads `metrics/grafana/dashboards/sources.json` and downloads each entry:

- `gnetId`: Grafana.com dashboard ID
- `revision`: `latest` or a pinned integer revision
- `datasource`: optional override (defaults to `prometheus-thanos`)
- `outputFile`: target JSON filename in `vendor/`
