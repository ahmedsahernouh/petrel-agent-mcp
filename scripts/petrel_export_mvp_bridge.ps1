param(
    [string]$ExportPackage = $env:PETREL_EXPORT_PACKAGE,

    [string]$InventoryPackage = $env:PETREL_INVENTORY_PACKAGE,

    [string]$ExportManifest = $env:PETREL_EXPORT_MANIFEST,

    [string]$StepName = "petrel_export_mvp_bridge",

    [switch]$NoValidate
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-RequiredPath {
    param(
        [string]$PathValue,
        [string]$Name,
        [switch]$Leaf
    )

    if ([string]::IsNullOrWhiteSpace($PathValue)) {
        throw "$Name was not provided and no matching environment variable is set."
    }

    if ($Leaf) {
        if (-not (Test-Path -LiteralPath $PathValue -PathType Leaf)) {
            throw "$Name does not exist: $PathValue"
        }
    } elseif (-not (Test-Path -LiteralPath $PathValue -PathType Container)) {
        throw "$Name does not exist: $PathValue"
    }

    return (Resolve-Path -LiteralPath $PathValue).Path
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$exportRoot = Resolve-RequiredPath -PathValue $ExportPackage -Name "ExportPackage"
if ([string]::IsNullOrWhiteSpace($ExportManifest)) {
    $ExportManifest = Join-Path $exportRoot "00_manifest\export_manifest.csv"
}
$manifestPath = Resolve-RequiredPath -PathValue $ExportManifest -Name "ExportManifest" -Leaf
$inventoryRoot = ""
if (-not [string]::IsNullOrWhiteSpace($InventoryPackage)) {
    $inventoryRoot = Resolve-RequiredPath -PathValue $InventoryPackage -Name "InventoryPackage"
}

$reportsDir = Join-Path $exportRoot "07_workflows_reports\exported_reports"
$runDir = Join-Path $exportRoot "07_workflows_reports\automation_runs"
New-Item -ItemType Directory -Force -Path $reportsDir, $runDir | Out-Null

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$probePath = Join-Path $reportsDir "external_workflow_bridge_probe.csv"
$statusPath = Join-Path $runDir "petrel_export_mvp_bridge_$stamp.json"

$probeRows = @(
    [pscustomobject]@{ key = "step_name"; value = $StepName },
    [pscustomobject]@{ key = "export_package"; value = $exportRoot },
    [pscustomobject]@{ key = "inventory_package"; value = $inventoryRoot },
    [pscustomobject]@{ key = "export_manifest"; value = $manifestPath },
    [pscustomobject]@{ key = "bridge_timestamp_utc"; value = (Get-Date).ToUniversalTime().ToString("o") }
)
$probeRows | Export-Csv -LiteralPath $probePath -NoTypeInformation -Encoding UTF8

$workflowStatus = "skipped"
$fileStatus = "skipped"
$validationStatus = "skipped"

$workflowRegistrar = Join-Path $scriptDir "register_petrel_workflow_artifacts.ps1"
if (Test-Path -LiteralPath $workflowRegistrar -PathType Leaf) {
    $workflowOutput = & $workflowRegistrar `
        -ExportPackage $exportRoot `
        -WorkflowName "ExportPiloX" `
        -InventoryPackage $inventoryRoot
    $workflowStatus = (($workflowOutput | Select-Object -First 1) -replace '^Artifact registration:\s*', '')
}

$fileRegistrar = Join-Path $scriptDir "register_petrel_file_exports.ps1"
if (Test-Path -LiteralPath $fileRegistrar -PathType Leaf) {
    $fileOutput = & $fileRegistrar `
        -ExportPackage $exportRoot `
        -InventoryPackage $inventoryRoot
    $fileStatus = (($fileOutput | Select-Object -First 1) -replace '^File export registration:\s*', '')
}

if (-not $NoValidate) {
    $validator = Join-Path $scriptDir "validate_export_package.ps1"
    $validationOutput = & $validator -ExportPackage $exportRoot -UpdateManifest -WriteChecksums
    $validationStatus = (($validationOutput | Select-Object -First 1) -replace '^Validation status:\s*', '')
}

$status = [ordered]@{
    created_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    step_name = $StepName
    export_package = $exportRoot
    inventory_package = $inventoryRoot
    export_manifest = $manifestPath
    probe_file = $probePath
    workflow_artifact_registration_status = $workflowStatus
    file_export_registration_status = $fileStatus
    validation_status = $validationStatus
}
$status | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $statusPath -Encoding UTF8

Write-Output "Bridge status file: $statusPath"
Write-Output "Probe file: $probePath"
Write-Output "Workflow artifact registration: $workflowStatus"
Write-Output "File export registration: $fileStatus"
Write-Output "Validation: $validationStatus"
