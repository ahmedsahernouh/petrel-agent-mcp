param(
    [string]$ProjectDirectory = "D:\Computer\Code\Petrel_project\Petrel_DemoData_project",

    [string]$ProjectStem = "Petrel2010 demo project ExportPilot",

    [string]$Label = "snapshot",

    [string[]]$StoreFiles = @("Model.ptd", "Data.ptd"),

    [string]$StoreFilesCsv = "",

    [string]$OutputRoot = "D:\Computer\Code\Petrel_project\build\native_edit_experiments"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not [string]::IsNullOrWhiteSpace($StoreFilesCsv)) {
    $StoreFiles = @($StoreFilesCsv -split "\|" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
}

function ConvertTo-Slug {
    param([string]$Value)

    $slug = $Value.ToLowerInvariant() -replace "[^a-z0-9]+", "_"
    $slug = $slug.Trim("_")
    if ([string]::IsNullOrWhiteSpace($slug)) {
        return "snapshot"
    }
    return $slug
}

$projectPath = (Resolve-Path -LiteralPath $ProjectDirectory).Path
$petPath = Join-Path $projectPath "$ProjectStem.pet"
$ptdDirectory = Join-Path $projectPath "$ProjectStem.ptd"

if (-not (Test-Path -LiteralPath $petPath -PathType Leaf)) {
    throw "Petrel project file not found: $petPath"
}
if (-not (Test-Path -LiteralPath $ptdDirectory -PathType Container)) {
    throw "Petrel native store directory not found: $ptdDirectory"
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$safeLabel = ConvertTo-Slug -Value $Label
$snapshotDir = Join-Path $OutputRoot "native_workflow_snapshot_${stamp}_$safeLabel"
$snapshotPtdDir = Join-Path $snapshotDir "$ProjectStem.ptd"
New-Item -ItemType Directory -Force -Path $snapshotPtdDir | Out-Null

$copied = @()

$petTarget = Join-Path $snapshotDir ([System.IO.Path]::GetFileName($petPath))
Copy-Item -LiteralPath $petPath -Destination $petTarget -Force
$petHash = Get-FileHash -LiteralPath $petTarget -Algorithm SHA256
$petItem = Get-Item -LiteralPath $petTarget
$copied += [pscustomobject]@{
    role = "project_file"
    source_path = $petPath
    snapshot_path = $petTarget
    length_bytes = $petItem.Length
    sha256 = $petHash.Hash.ToLowerInvariant()
}

foreach ($storeFile in $StoreFiles) {
    if ([string]::IsNullOrWhiteSpace($storeFile)) {
        continue
    }

    $source = Join-Path $ptdDirectory $storeFile
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "Store file not found: $source"
    }

    $target = Join-Path $snapshotPtdDir $storeFile
    Copy-Item -LiteralPath $source -Destination $target -Force
    $hash = Get-FileHash -LiteralPath $target -Algorithm SHA256
    $item = Get-Item -LiteralPath $target
    $copied += [pscustomobject]@{
        role = "store_file"
        source_path = $source
        snapshot_path = $target
        length_bytes = $item.Length
        sha256 = $hash.Hash.ToLowerInvariant()
    }
}

$manifestPath = Join-Path $snapshotDir "snapshot_manifest.json"
$manifest = [ordered]@{
    created_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    label = $Label
    project_directory = $projectPath
    project_stem = $ProjectStem
    snapshot_directory = $snapshotDir
    store_files = $StoreFiles
    files = $copied
}
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $manifestPath -Encoding UTF8

$summaryPath = Join-Path $snapshotDir "snapshot_summary.md"
$md = @(
    "# Petrel Native Workflow Snapshot",
    "",
    "- Created UTC: $($manifest.created_at_utc)",
    "- Label: $Label",
    "- Source project: $projectPath",
    "- Project stem: $ProjectStem",
    "- Snapshot directory: $snapshotDir",
    "",
    "## Files",
    "",
    "| Role | File | Bytes | SHA256 |",
    "| --- | --- | ---: | --- |"
)
foreach ($file in $copied) {
    $md += "| $($file.role) | $($file.snapshot_path) | $($file.length_bytes) | $($file.sha256) |"
}
$md | Set-Content -LiteralPath $summaryPath -Encoding UTF8

Write-Output "Native workflow snapshot complete"
Write-Output "Snapshot: $snapshotDir"
Write-Output "Manifest: $manifestPath"
Write-Output "Summary: $summaryPath"
