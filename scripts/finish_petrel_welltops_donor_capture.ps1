param(
    [string]$BeforeSnapshot = "",

    [string]$ProjectDirectory = "D:\Computer\Code\Petrel_project\Petrel_DemoData_project",

    [string]$ProjectStem = "Petrel2010 demo project ExportPilot",

    [string]$OutputRoot = "D:\Computer\Code\Petrel_project\build\native_edit_experiments",

    [switch]$AllowRunningPetrel
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

if ([string]::IsNullOrWhiteSpace($BeforeSnapshot)) {
    $candidate = Get-ChildItem -LiteralPath $OutputRoot -Directory -Filter "*before_welltops_export_command_donor" |
        Sort-Object LastWriteTimeUtc -Descending |
        Select-Object -First 1
    if ($null -eq $candidate) {
        throw "No before Well Tops donor snapshot found. Pass -BeforeSnapshot explicitly."
    }
    $BeforeSnapshot = $candidate.FullName
}

$BeforeSnapshot = (Resolve-Path -LiteralPath $BeforeSnapshot).Path

$petrelProcesses = @(Get-Process Petrel -ErrorAction SilentlyContinue)
if ($petrelProcesses.Count -gt 0 -and -not $AllowRunningPetrel) {
    $titles = ($petrelProcesses | ForEach-Object { "$($_.Id): $($_.MainWindowTitle)" }) -join "; "
    throw "Petrel is still running. Save and close Petrel before taking the after snapshot. Running: $titles"
}

$afterOutput = & (Join-Path $scriptDir "new_petrel_native_workflow_snapshot.ps1") `
    -ProjectDirectory $ProjectDirectory `
    -ProjectStem $ProjectStem `
    -Label "after_welltops_export_command_donor" `
    -OutputRoot $OutputRoot

$afterSnapshotLine = $afterOutput | Where-Object { $_ -like "Snapshot:*" } | Select-Object -First 1
if ($null -eq $afterSnapshotLine) {
    throw "After snapshot path was not reported by new_petrel_native_workflow_snapshot.ps1"
}
$afterSnapshot = ($afterSnapshotLine -replace "^Snapshot:\s*", "").Trim()

$terms = @(
    "ExportWell",
    "Export well",
    "Export well tops",
    "Well Tops",
    "WellTops",
    "Petrel well tops",
    "Petrel well tops (ASCII)",
    "well_tops_exportpilot",
    "well_tops_workflow",
    "SheetSaveCmd",
    "SystemCmd",
    "ExportSeismicCmd",
    "BXML",
    "LZ4",
    "export_package",
    "inventory_package",
    "export_manifest"
) -join "|"

$compareOutput = & (Join-Path $scriptDir "compare_petrel_native_workflow_snapshots.ps1") `
    -BeforeSnapshot $BeforeSnapshot `
    -AfterSnapshot $afterSnapshot `
    -ProjectStem $ProjectStem `
    -TermsCsv $terms `
    -OutputRoot $OutputRoot

$compareReportLine = $compareOutput | Where-Object { $_ -like "Report:*" } | Select-Object -First 1
$compareReport = if ($null -ne $compareReportLine) { ($compareReportLine -replace "^Report:\s*", "").Trim() } else { "" }

$mapOutput = & (Join-Path $scriptDir "map_petrel_native_workflow_regions.ps1")

$summary = [ordered]@{
    created_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    before_snapshot = $BeforeSnapshot
    after_snapshot = $afterSnapshot
    compare_report = $compareReport
    compare_output = @($compareOutput)
    region_map_output = @($mapOutput)
    next_step = "Inspect compare report and map for a new Well Tops export command record before attempting any native patching."
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$captureDir = Join-Path $OutputRoot "welltops_export_donor_capture_$stamp"
New-Item -ItemType Directory -Force -Path $captureDir | Out-Null
$summaryPath = Join-Path $captureDir "welltops_export_donor_capture_report.json"
$summary | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $summaryPath -Encoding UTF8

Write-Output "Well Tops donor capture finish complete"
Write-Output "Before snapshot: $BeforeSnapshot"
Write-Output "After snapshot: $afterSnapshot"
if (-not [string]::IsNullOrWhiteSpace($compareReport)) {
    Write-Output "Compare report: $compareReport"
}
Write-Output "Capture report: $summaryPath"
