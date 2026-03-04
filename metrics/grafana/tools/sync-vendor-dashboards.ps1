param(
  [string]$SourcesFile = "metrics/grafana/dashboards/sources.json",
  [switch]$InsecureTls = $false
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $SourcesFile)) {
  throw "Sources file not found: $SourcesFile"
}

$sources = Get-Content -Raw $SourcesFile | ConvertFrom-Json
$outputDir = $sources.defaults.outputDir
$defaultDatasource = $sources.defaults.datasource

New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

$curlArgs = @("-sS", "-L")
if ($InsecureTls) { $curlArgs += "-k" }

function Resolve-Revision {
  param(
    [int]$GnetId,
    [object]$Revision
  )

  if ($Revision -is [int]) {
    return $Revision
  }

  if ($Revision -is [long]) {
    return [int]$Revision
  }

  if (($Revision -is [string]) -and ($Revision -ne "latest")) {
    $parsed = 0
    if ([int]::TryParse($Revision, [ref]$parsed)) {
      return $parsed
    }
    throw "Invalid revision '$Revision' for gnetId=$GnetId"
  }

  $metaUrl = "https://grafana.com/api/dashboards/$GnetId"
  $metaRaw = & curl.exe @curlArgs $metaUrl
  $meta = $metaRaw | ConvertFrom-Json

  if ($null -ne $meta.revision) {
    return [int]$meta.revision
  }

  if ($null -ne $meta.dashboard -and $null -ne $meta.dashboard.revision) {
    return [int]$meta.dashboard.revision
  }

  if ($null -ne $meta.revisions -and $meta.revisions.Count -gt 0) {
    return [int](($meta.revisions | Measure-Object -Property revision -Maximum).Maximum)
  }

  throw "Could not resolve latest revision for gnetId=$GnetId"
}

$index = @()

foreach ($entry in $sources.dashboards) {
  $gnetId = [int]$entry.gnetId
  $revision = Resolve-Revision -GnetId $gnetId -Revision $entry.revision
  $datasource = if ([string]::IsNullOrWhiteSpace($entry.datasource)) { $defaultDatasource } else { [string]$entry.datasource }
  $outputFile = [string]$entry.outputFile

  if ([string]::IsNullOrWhiteSpace($outputFile)) {
    $outputFile = "$gnetId-r$revision.json"
  }

  $downloadUrl = "https://grafana.com/api/dashboards/$gnetId/revisions/$revision/download"
  $raw = & curl.exe @curlArgs $downloadUrl
  $dashboard = $raw | ConvertFrom-Json

  # Keep dashboards deterministic and ready for provisioning/import.
  $dashboard.id = $null
  $dashboard.uid = $null
  $dashboard.version = 1

  # Replace common datasource placeholders used in grafana.com dashboards.
  $json = $dashboard | ConvertTo-Json -Depth 100
  $json = $json -replace '\$\{DS_PROMETHEUS\}', $datasource
  $json = $json -replace '\$DS_PROMETHEUS', $datasource
  $json = $json -replace '\$\{DS_LOKI\}', $datasource
  $json = $json -replace '\$DS_LOKI', $datasource

  $normalized = $json | ConvertFrom-Json
  $path = Join-Path $outputDir $outputFile
  $normalized | ConvertTo-Json -Depth 100 | Set-Content -Path $path -Encoding UTF8

  $index += [pscustomobject]@{
    gnetId = $gnetId
    revision = $revision
    datasource = $datasource
    title = $normalized.title
    file = $outputFile
    source = $downloadUrl
    updatedAt = (Get-Date).ToString("s")
  }

  Write-Output ("Synced gnetId={0} rev={1} -> {2}" -f $gnetId, $revision, $outputFile)
}

$indexPath = Join-Path (Split-Path $SourcesFile -Parent) "vendor-index.json"
$index | Sort-Object gnetId | ConvertTo-Json -Depth 10 | Set-Content -Path $indexPath -Encoding UTF8
Write-Output ("Wrote vendor index: {0}" -f $indexPath)
