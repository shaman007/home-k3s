param(
    [string]$Namespace = "longhorn-system",
    [string]$OutputPath = "longhorn/recurring-jobs-export.yaml"
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$resolvedOutputPath = if ([System.IO.Path]::IsPathRooted($OutputPath)) {
    $OutputPath
} else {
    Join-Path $repoRoot $OutputPath
}

$outputDirectory = Split-Path -Path $resolvedOutputPath -Parent
if (-not (Test-Path -Path $outputDirectory)) {
    New-Item -ItemType Directory -Path $outputDirectory | Out-Null
}

$backupTask = "backup"
$trimTask = "filesystem-trim"
$jobs = kubectl get recurringjobs.longhorn.io -n $Namespace -o json |
    jq -c --arg backup $backupTask --arg trim $trimTask '
        .items
        | sort_by(.metadata.name)[]
        | select(.spec.task == $backup or .spec.task == $trim)
        | {
            apiVersion,
            kind,
            metadata: {
                name: .metadata.name,
                namespace: .metadata.namespace
            },
            spec: .spec
        }'

if (-not $jobs) {
    throw "No Longhorn recurring jobs with task '$backupTask' or '$trimTask' were found in namespace '$Namespace'."
}

$renderedDocs = foreach ($job in $jobs) {
    (($job | yq eval -P -) -join "`n").TrimEnd()
}

$header = @(
    "# Exported from the live cluster with .\tools\longhorn\export-recurring-jobs.ps1",
    "# Includes Longhorn RecurringJob resources for task=backup and task=filesystem-trim."
)

$content = ($header -join "`n") + "`n" + ($renderedDocs -join "`n---`n")
Set-Content -Path $resolvedOutputPath -Value $content -NoNewline -Encoding ascii

$backupCount = ($jobs | Select-String -Pattern '"task":"backup"' | Measure-Object).Count
$trimCount = ($jobs | Select-String -Pattern '"task":"filesystem-trim"' | Measure-Object).Count

Write-Host "Exported $($jobs.Count) recurring jobs to $resolvedOutputPath"
Write-Host "  backup: $backupCount"
Write-Host "  filesystem-trim: $trimCount"
