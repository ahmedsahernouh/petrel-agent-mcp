param(
    [string]$ProjectName = "Petrel2010 demo project",

    [string]$PetrelVersion = "2018.2.0.5333",

    [string]$ExportPackage = "D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609",

    [string]$InventoryPackage = "D:\Computer\Code\Petrel_project\build\inventory_pilots\Petrel2010_demo_project_inventory_20260701_055128",

    [string]$Title = "",

    [string]$PythonPath = "",

    [switch]$NoRegister,

    [switch]$NoValidate
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
. (Join-Path $scriptDir "petrel_mcp_dependencies.ps1")
$pythonScript = Join-Path $scriptDir "report_petrel_project_audit.py"
$registrar = Join-Path $scriptDir "register_petrel_file_exports.ps1"
$validator = Join-Path $scriptDir "validate_export_package.ps1"

if (-not (Test-Path -LiteralPath $pythonScript -PathType Leaf)) {
    throw "Project audit reporter not found: $pythonScript"
}
if (-not (Test-Path -LiteralPath $ExportPackage -PathType Container)) {
    throw "Export package not found: $ExportPackage"
}

$pythonExe = Resolve-PetrelMcpPython -ExplicitPath $PythonPath -ProjectRoot $repoRoot

$pythonArgs = @("--export-package", $ExportPackage)
if ($Title -ne "") {
    $pythonArgs += @("--title", $Title)
}

& $pythonExe $pythonScript @pythonArgs

$exportExitCode = if ($null -ne (Get-Variable -Name LASTEXITCODE -ErrorAction SilentlyContinue)) { $LASTEXITCODE } else { 0 }
if ($exportExitCode -ne 0) {
    exit $exportExitCode
}

if (-not $NoRegister) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $registrar `
        -ExportPackage $ExportPackage `
        -ProjectName $ProjectName `
        -PetrelVersion $PetrelVersion `
        -InventoryPackage $InventoryPackage `
        -RegisterUnknown

    $registerExitCode = if ($null -ne (Get-Variable -Name LASTEXITCODE -ErrorAction SilentlyContinue)) { $LASTEXITCODE } else { 0 }
    if ($registerExitCode -ne 0) {
        exit $registerExitCode
    }
}

if (-not $NoValidate) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $validator `
        -ExportPackage $ExportPackage `
        -UpdateManifest `
        -WriteChecksums

    $validateExitCode = if ($null -ne (Get-Variable -Name LASTEXITCODE -ErrorAction SilentlyContinue)) { $LASTEXITCODE } else { 0 }
    if ($validateExitCode -ne 0) {
        exit $validateExitCode
    }
}
