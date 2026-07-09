param(
    [string]$ProjectFile = "D:\Computer\Code\Petrel_project\Petrel_DemoData_project\Petrel2010 demo project ExportPilot.pet",

    [string]$WorkflowName = "ExportPiloX",

    [string]$LicensePackage = "BatchProfile",

    [switch]$CreateNewPackages,

    [switch]$DryRun,

    [switch]$NoValidate
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$runner = Join-Path $scriptDir "invoke_petrel_export_pilot.ps1"

if (-not (Test-Path -LiteralPath $runner -PathType Leaf)) {
    throw "Runner not found: $runner"
}

if (-not (Test-Path -LiteralPath $ProjectFile -PathType Leaf)) {
    throw "Project file not found: $ProjectFile"
}

$arguments = @{
    Mode = "RunWorkflow"
    WorkflowName = $WorkflowName
    ProjectFile = $ProjectFile
    PetrelOptionStyle = "Slash"
    LicensePackage = $LicensePackage
    Wait = $true
}

if ($CreateNewPackages) {
    $arguments.CreateNewPackages = $true
}
if ($DryRun) {
    $arguments.DryRun = $true
}
if ($NoValidate) {
    $arguments.NoValidate = $true
}

& $runner @arguments
$runnerExitCode = $LASTEXITCODE
if ($null -ne $runnerExitCode -and $runnerExitCode -ne 0) {
    exit $runnerExitCode
}
