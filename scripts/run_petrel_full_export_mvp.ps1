param(
    [string]$ProjectFile = "D:\Computer\Code\Petrel_project\Petrel_DemoData_project\Petrel2010 demo project ExportPilot.pet",

    [string]$ProjectName = "Petrel2010 demo project",

    [string]$PetrelVersion = "2018.2.0.5333",

    [string]$InventoryPackage = "D:\Computer\Code\Petrel_project\build\inventory_pilots\Petrel2010_demo_project_inventory_20260701_055128",

    [string]$ExportPackage = "D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609",

    [string]$WorkflowName = "ExportPiloX",

    [string]$LicensePackage = "BatchProfile",

    [switch]$ValidateOnly,

    [switch]$DryRun,

    [switch]$NoValidate
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$mvpBuilder = Join-Path $scriptDir "build_petrel_full_export_mvp.ps1"
$runner = Join-Path $scriptDir "invoke_petrel_export_pilot.ps1"

if (-not (Test-Path -LiteralPath $mvpBuilder -PathType Leaf)) {
    throw "MVP builder not found: $mvpBuilder"
}
if (-not (Test-Path -LiteralPath $runner -PathType Leaf)) {
    throw "Runner not found: $runner"
}
if (-not (Test-Path -LiteralPath $ProjectFile -PathType Leaf)) {
    throw "Project file not found: $ProjectFile"
}

Write-Output "Building KB-derived full export MVP artifacts..."
& $mvpBuilder `
    -ProjectName $ProjectName `
    -PetrelVersion $PetrelVersion `
    -ExportPackage $ExportPackage `
    -InventoryPackage $InventoryPackage `
    -WorkflowName $WorkflowName

$mode = if ($ValidateOnly) { "ValidateOnly" } else { "RunWorkflow" }

Write-Output "Running Petrel export MVP mode: $mode"
$arguments = @{
    Mode = $mode
    WorkflowName = $WorkflowName
    ProjectFile = $ProjectFile
    InventoryPackage = $InventoryPackage
    ExportPackage = $ExportPackage
    PetrelOptionStyle = "Slash"
    LicensePackage = $LicensePackage
}

if (-not $ValidateOnly) {
    $arguments.Wait = $true
}
if ($DryRun) {
    $arguments.DryRun = $true
}
if ($NoValidate) {
    $arguments.NoValidate = $true
}

& $runner @arguments
$lastExitCodeVariable = Get-Variable -Name LASTEXITCODE -ErrorAction SilentlyContinue
$runnerExitCode = if ($null -ne $lastExitCodeVariable) { $lastExitCodeVariable.Value } else { 0 }
if ($null -ne $runnerExitCode -and $runnerExitCode -ne 0) {
    exit $runnerExitCode
}
