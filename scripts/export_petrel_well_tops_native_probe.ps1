param(
    [string]$ProjectName = "Petrel2010 demo project",
    [string]$ProjectFile = "D:\Computer\Code\Petrel_project\Petrel_DemoData_project\Petrel2010 demo project ExportPilot.pet",
    [string]$PetrelVersion = "2018.2.0.5333",
    [string]$ExportPackage = "D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609",
    [string]$InventoryPackage = "D:\Computer\Code\Petrel_project\build\inventory_pilots\Petrel2010_demo_project_inventory_20260701_055128",
    [string]$SourceWellTopsFile = "",
    [string]$PythonPath = "",
    [switch]$NoRegister,
    [switch]$NoValidate
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
. (Join-Path $scriptDir "petrel_mcp_dependencies.ps1")
$pythonScript = Join-Path $scriptDir "export_petrel_well_tops_native_probe.py"
$pythonExe = Resolve-PetrelMcpPython -ExplicitPath $PythonPath -ProjectRoot $repoRoot

$pythonArgs = @(
    $pythonScript,
    "--project-name",
    $ProjectName,
    "--petrel-version",
    $PetrelVersion,
    "--project-file",
    $ProjectFile,
    "--export-package",
    $ExportPackage
)

if (-not [string]::IsNullOrWhiteSpace($SourceWellTopsFile)) {
    $pythonArgs += @("--source-well-tops-file", $SourceWellTopsFile)
}

& $pythonExe @pythonArgs

$exitCode = Get-PetrelMcpLastExitCode
if ($exitCode -ne 0) {
    exit $exitCode
}

if (-not $NoRegister) {
    $registrar = Join-Path $scriptDir "register_petrel_file_exports.ps1"
    & $registrar `
        -ExportPackage $ExportPackage `
        -ProjectName $ProjectName `
        -PetrelVersion $PetrelVersion `
        -InventoryPackage $InventoryPackage
}

if (-not $NoValidate) {
    $validator = Join-Path $scriptDir "validate_export_package.ps1"
    & $validator -ExportPackage $ExportPackage -UpdateManifest -WriteChecksums
}
