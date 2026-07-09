param(
    [Parameter(Mandatory = $true)]
    [string]$ExportPackage,

    [string]$WorkflowName = "ExportPiloX",

    [string]$ProjectName = "Petrel2010 demo project",

    [string]$PetrelVersion = "2018.2.0.5333",

    [string]$InventoryPackage = "",

    [switch]$FailOnMismatch
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-RelativePath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$BasePath,

        [Parameter(Mandatory = $true)]
        [string]$PathValue
    )

    $baseUri = [System.Uri]((Resolve-Path -LiteralPath $BasePath).Path.TrimEnd("\") + "\")
    $fileUri = [System.Uri]((Resolve-Path -LiteralPath $PathValue).Path)
    return [System.Uri]::UnescapeDataString($baseUri.MakeRelativeUri($fileUri).ToString()).Replace("/", "\")
}

function New-ManifestRow {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Headers
    )

    $row = [ordered]@{}
    foreach ($header in $Headers) {
        $row[$header] = ""
    }
    return $row
}

$packageRoot = (Resolve-Path -LiteralPath $ExportPackage).Path
$manifestPath = Join-Path $packageRoot "00_manifest\export_manifest.csv"
$probePath = Join-Path $packageRoot "07_workflows_reports\exported_reports\cli_variable_probe.csv"
$runDir = Join-Path $packageRoot "07_workflows_reports\automation_runs"

if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw "Export manifest not found: $manifestPath"
}

New-Item -ItemType Directory -Force -Path $runDir | Out-Null

$headerLine = Get-Content -LiteralPath $manifestPath -TotalCount 1
if ([string]::IsNullOrWhiteSpace($headerLine)) {
    throw "Export manifest is empty: $manifestPath"
}

$headers = $headerLine.Split(",") | ForEach-Object { $_.Trim('"') }
$requiredHeaders = @(
    "export_id",
    "project_name",
    "petrel_version",
    "export_date_utc",
    "source_object_path",
    "source_object_type",
    "export_format",
    "export_file",
    "export_status",
    "validation_status",
    "notes"
)

$missingHeaders = @($requiredHeaders | Where-Object { $headers -notcontains $_ })
if ($missingHeaders.Count -gt 0) {
    throw "Export manifest is missing required columns: $($missingHeaders -join ', ')"
}

$registered = @()
$issues = @()

if (Test-Path -LiteralPath $probePath -PathType Leaf) {
    $probeValues = [ordered]@{}
    foreach ($line in (Get-Content -LiteralPath $probePath)) {
        if ([string]::IsNullOrWhiteSpace($line)) {
            continue
        }
        $parts = $line -split "`t", 2
        if ($parts.Count -eq 2) {
            $probeValues[$parts[0].Trim()] = $parts[1].Trim()
        }
    }

    $expectedExportPackage = $packageRoot
    $expectedManifest = $manifestPath
    if ($probeValues.Contains("export_package") -and $probeValues["export_package"] -ne $expectedExportPackage) {
        $issues += "export_package mismatch: expected '$expectedExportPackage' got '$($probeValues["export_package"])'"
    }
    if (-not [string]::IsNullOrWhiteSpace($InventoryPackage) -and $probeValues.Contains("inventory_package")) {
        $resolvedInventoryPackage = (Resolve-Path -LiteralPath $InventoryPackage).Path
        if ($probeValues["inventory_package"] -ne $resolvedInventoryPackage) {
            $issues += "inventory_package mismatch: expected '$resolvedInventoryPackage' got '$($probeValues["inventory_package"])'"
        }
    }
    if ($probeValues.Contains("export_manifest") -and $probeValues["export_manifest"] -ne $expectedManifest) {
        $issues += "export_manifest mismatch: expected '$expectedManifest' got '$($probeValues["export_manifest"])'"
    }

    $fileItem = Get-Item -LiteralPath $probePath
    $row = New-ManifestRow -Headers $headers
    $row["export_id"] = "workflow_report_cli_variable_probe"
    $row["project_name"] = $ProjectName
    $row["petrel_version"] = $PetrelVersion
    $row["export_date_utc"] = $fileItem.LastWriteTimeUtc.ToString("o")
    $row["source_object_path"] = "Workflow Editor/$WorkflowName/CLI variable probe"
    $row["source_object_type"] = "workflow_report"
    $row["export_format"] = "TSV"
    $row["export_file"] = Get-RelativePath -BasePath $packageRoot -PathValue $probePath
    $row["export_status"] = "exported"
    $row["validation_status"] = "unchecked"
    $row["notes"] = "Petrel Workflow Editor output sheet generated during CLI bridge run; verifies injected string variables."

    $existingRows = @(Import-Csv -LiteralPath $manifestPath)
    $newRows = @()
    $updated = $false
    foreach ($existingRow in $existingRows) {
        if ($existingRow.export_id -eq $row["export_id"]) {
            $newRows += [pscustomobject]$row
            $updated = $true
        } else {
            $newRows += $existingRow
        }
    }
    if (-not $updated) {
        $newRows += [pscustomobject]$row
    }

    $newRows | Export-Csv -LiteralPath $manifestPath -NoTypeInformation -Encoding UTF8
    $registered += $row["export_file"]
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$reportPath = Join-Path $runDir "petrel_workflow_artifact_registration_$stamp.json"
$summary = [ordered]@{
    created_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    export_package = $packageRoot
    workflow_name = $WorkflowName
    manifest_path = $manifestPath
    registered_count = $registered.Count
    registered_files = $registered
    issues = $issues
    status = if ($issues.Count -gt 0) { "warning" } elseif ($registered.Count -gt 0) { "registered" } else { "no_workflow_artifacts_found" }
}
$summary | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $reportPath -Encoding UTF8

Write-Output "Artifact registration: $($summary.status)"
Write-Output "Registered: $($registered.Count)"
Write-Output "Report: $reportPath"

if ($FailOnMismatch -and $issues.Count -gt 0) {
    exit 2
}
