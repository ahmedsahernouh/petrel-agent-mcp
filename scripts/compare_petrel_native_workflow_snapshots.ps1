param(
    [Parameter(Mandatory = $true)]
    [string]$BeforeSnapshot,

    [Parameter(Mandatory = $true)]
    [string]$AfterSnapshot,

    [string]$ProjectStem = "Petrel2010 demo project ExportPilot",

    [string[]]$StoreFiles = @("Model.ptd", "Data.ptd"),

    [string]$StoreFilesCsv = "",

    [string]$TermsCsv = "SheetSaveCmd|SystemCmd|powershell.exe|petrel_export_mvp_bridge.ps1|export_package|cli_variable|BXML|LZ4",

    [string]$PythonPath = "",

    [string]$OutputRoot = "D:\Computer\Code\Petrel_project\build\native_edit_experiments"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not [string]::IsNullOrWhiteSpace($StoreFilesCsv)) {
    $StoreFiles = @($StoreFilesCsv -split "\|" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
. (Join-Path $scriptDir "petrel_mcp_dependencies.ps1")
$pythonScript = Join-Path $scriptDir "compare_petrel_native_workflow_snapshots.py"
$python = Resolve-PetrelMcpPython -ExplicitPath $PythonPath -ProjectRoot $repoRoot

if (-not (Test-Path -LiteralPath $pythonScript -PathType Leaf)) {
    throw "Python compare helper not found: $pythonScript"
}

& $python $pythonScript `
    --before-snapshot $BeforeSnapshot `
    --after-snapshot $AfterSnapshot `
    --project-stem $ProjectStem `
    --store-files (($StoreFiles | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }) -join "|") `
    --terms $TermsCsv `
    --output-root $OutputRoot

$exitCode = Get-PetrelMcpLastExitCode
exit $exitCode
