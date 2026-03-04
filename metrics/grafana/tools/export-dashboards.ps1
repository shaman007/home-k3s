param(
  [string]$GrafanaUrl = "https://grafana.w386.k8s.my.lan",
  [string]$GrafanaToken = $env:GRAFANA_TOKEN,
  [switch]$InsecureTls = $true,
  [string]$OutputDir = "metrics/grafana/dashboards/live",
  [string]$IndexFile = "metrics/grafana/dashboards/index.json"
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($GrafanaToken)) {
  throw "Grafana token is required. Set -GrafanaToken or GRAFANA_TOKEN."
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$curlArgs = @("-sS")
if ($InsecureTls) { $curlArgs += "-k" }
$authHeader = "Authorization: Bearer $GrafanaToken"

$searchUrl = "$GrafanaUrl/api/search?type=dash-db&limit=5000"
$searchRaw = & curl.exe @curlArgs -H $authHeader $searchUrl
$dashboards = $searchRaw | ConvertFrom-Json

$index = @()

foreach ($item in $dashboards) {
  if (-not $item.uid) { continue }

  $dashUrl = "$GrafanaUrl/api/dashboards/uid/$($item.uid)"
  $dashRaw = & curl.exe @curlArgs -H $authHeader $dashUrl
  $dashObj = $dashRaw | ConvertFrom-Json

  $dashboard = $dashObj.dashboard
  if (-not $dashboard) { continue }

  $safeTitle = ($dashboard.title -replace '[^a-zA-Z0-9._-]+', '-') -replace '-+', '-'
  $safeTitle = $safeTitle.Trim('-')
  if ([string]::IsNullOrWhiteSpace($safeTitle)) {
    $safeTitle = $dashboard.uid
  }

  $fileName = "{0}-{1}.json" -f $dashboard.uid, $safeTitle
  $filePath = Join-Path $OutputDir $fileName

  $dashboard | ConvertTo-Json -Depth 100 | Set-Content -Path $filePath -Encoding UTF8

  $index += [pscustomobject]@{
    title = $dashboard.title
    uid = $dashboard.uid
    version = $dashboard.version
    folder = $dashObj.meta.folderTitle
    updated = $dashObj.meta.updated
    url = "$GrafanaUrl$($dashObj.meta.url)"
    file = $fileName
  }
}

$index | Sort-Object title | ConvertTo-Json -Depth 10 | Set-Content -Path $IndexFile -Encoding UTF8

Write-Output ("Exported {0} dashboards to {1}" -f $index.Count, $OutputDir)
