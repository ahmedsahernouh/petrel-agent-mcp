param(
    [string]$ProjectName = "Petrel2010 demo project",

    [string]$ProjectFile = "D:\Computer\Code\Petrel_project\Petrel_DemoData_project\Petrel2010 demo project ExportPilot.pet",

    [string]$PetrelVersion = "2018.2.0.5333",

    [string]$ExportPackage = "D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609",

    [string]$InventoryPackage = "D:\Computer\Code\Petrel_project\build\inventory_pilots\Petrel2010_demo_project_inventory_20260701_055128",

    [int]$MaxXmlNames = 20,

    [string]$PythonPath = "",

    [switch]$NoValidate
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
. (Join-Path $scriptDir "petrel_mcp_dependencies.ps1")
$pythonScript = Join-Path $scriptDir "export_petrel_native_semantic_zero_gui.py"

if (-not (Test-Path -LiteralPath $pythonScript -PathType Leaf)) {
    throw "Semantic zero-GUI exporter not found: $pythonScript"
}
if (-not (Test-Path -LiteralPath $ExportPackage -PathType Container)) {
    throw "Export package not found: $ExportPackage"
}

$pythonExe = Resolve-PetrelMcpPython -ExplicitPath $PythonPath -ProjectRoot $repoRoot

$arguments = @(
    $pythonScript,
    "--project-name", $ProjectName,
    "--project-file", $ProjectFile,
    "--petrel-version", $PetrelVersion,
    "--export-package", $ExportPackage,
    "--inventory-package", $InventoryPackage,
    "--max-xml-names", [string]$MaxXmlNames
)

if ($NoValidate) {
    $arguments += "--no-validate"
}

& $pythonExe @arguments
$exitCode = if ($null -ne (Get-Variable -Name LASTEXITCODE -ErrorAction SilentlyContinue)) { $LASTEXITCODE } else { 0 }
if ($exitCode -ne 0) {
    exit $exitCode
}
