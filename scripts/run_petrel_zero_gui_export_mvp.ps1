param(
    [string]$ProjectFile = "D:\Computer\Code\Petrel_project\Petrel_DemoData_project\Petrel2010 demo project ExportPilot.pet",

    [string]$ProjectName = "Petrel2010 demo project",

    [string]$PetrelVersion = "2018.2.0.5333",

    [string]$InventoryPackage = "D:\Computer\Code\Petrel_project\build\inventory_pilots\Petrel2010_demo_project_inventory_20260701_055128",

    [string]$ExportPackage = "D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609",

    [string]$WorkflowName = "ExportPiloX",

    [int64]$MaxTextProbeBytes = 10485760,

    [int]$MaxCandidatesPerFile = 200,

    [string]$PythonPath = "",

    [switch]$CreateNewPackage,

    [switch]$SkipSemanticExtraction,

    [switch]$NoValidate
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $scriptDir "petrel_mcp_dependencies.ps1")
$mvpBuilder = Join-Path $scriptDir "build_petrel_full_export_mvp.ps1"
$nativeExporter = Join-Path $scriptDir "export_petrel_native_project_zero_gui.ps1"
$semanticExporter = Join-Path $scriptDir "export_petrel_native_semantic_zero_gui.ps1"

if (-not (Test-Path -LiteralPath $ProjectFile -PathType Leaf)) {
    throw "Project file not found: $ProjectFile"
}
if (-not (Test-Path -LiteralPath $mvpBuilder -PathType Leaf)) {
    throw "MVP builder not found: $mvpBuilder"
}
if (-not (Test-Path -LiteralPath $nativeExporter -PathType Leaf)) {
    throw "Zero-GUI native exporter not found: $nativeExporter"
}
if (-not $SkipSemanticExtraction -and -not (Test-Path -LiteralPath $semanticExporter -PathType Leaf)) {
    throw "Zero-GUI native semantic exporter not found: $semanticExporter"
}

Write-Output "Building KB-derived full export MVP artifacts..."
& $mvpBuilder `
    -ProjectName $ProjectName `
    -PetrelVersion $PetrelVersion `
    -ExportPackage $ExportPackage `
    -InventoryPackage $InventoryPackage `
    -WorkflowName $WorkflowName

Write-Output "Running zero-GUI native project export..."
$arguments = @{
    ProjectName = $ProjectName
    ProjectFile = $ProjectFile
    PetrelVersion = $PetrelVersion
    InventoryPackage = $InventoryPackage
    ExportPackage = $ExportPackage
    MaxTextProbeBytes = $MaxTextProbeBytes
    MaxCandidatesPerFile = $MaxCandidatesPerFile
}

if ($CreateNewPackage) {
    $arguments.CreateNewPackage = $true
}
if ($NoValidate -or -not $SkipSemanticExtraction) {
    $arguments.NoValidate = $true
}

& $nativeExporter @arguments
$lastExitCodeVariable = Get-Variable -Name LASTEXITCODE -ErrorAction SilentlyContinue
$exporterExitCode = if ($null -ne $lastExitCodeVariable) { $lastExitCodeVariable.Value } else { 0 }
if ($null -ne $exporterExitCode -and $exporterExitCode -ne 0) {
    exit $exporterExitCode
}

if (-not $SkipSemanticExtraction) {
    $repoRoot = Split-Path -Parent $scriptDir
    $resolvedPython = Resolve-PetrelMcpPython -ExplicitPath $PythonPath -ProjectRoot $repoRoot
    Write-Output "Running zero-GUI native semantic metadata extraction..."
    $semanticArguments = @{
        ProjectName = $ProjectName
        ProjectFile = $ProjectFile
        PetrelVersion = $PetrelVersion
        InventoryPackage = $InventoryPackage
        ExportPackage = $ExportPackage
        PythonPath = $resolvedPython
    }
    if ($NoValidate) {
        $semanticArguments.NoValidate = $true
    }

    & $semanticExporter @semanticArguments
    $lastExitCodeVariable = Get-Variable -Name LASTEXITCODE -ErrorAction SilentlyContinue
    $semanticExitCode = if ($null -ne $lastExitCodeVariable) { $lastExitCodeVariable.Value } else { 0 }
    if ($null -ne $semanticExitCode -and $semanticExitCode -ne 0) {
        exit $semanticExitCode
    }
}
