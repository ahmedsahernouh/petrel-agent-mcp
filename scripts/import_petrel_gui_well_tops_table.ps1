param(
    [Parameter(Mandatory = $true)]
    [string]$GuiTablePaste,

    [string]$ProjectName = "Petrel2010 demo project",

    [string]$PetrelVersion = "2018.2.0.5333",

    [string]$ExportPackage = "D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609",

    [string]$SourceAsciiCsv = "",

    [string]$PythonPath = "",

    [double]$NumericTolerance = 0.05
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptRoot
. (Join-Path $scriptRoot "petrel_mcp_dependencies.ps1")
$pythonScript = Join-Path $scriptRoot "import_petrel_gui_well_tops_table.py"
$pythonExe = Resolve-PetrelMcpPython -ExplicitPath $PythonPath -ProjectRoot $repoRoot

$arguments = @(
    $pythonScript,
    "--project-name", $ProjectName,
    "--petrel-version", $PetrelVersion,
    "--gui-table-paste", $GuiTablePaste,
    "--export-package", $ExportPackage,
    "--numeric-tolerance", ([string]::Format([System.Globalization.CultureInfo]::InvariantCulture, "{0}", $NumericTolerance))
)

if (-not [string]::IsNullOrWhiteSpace($SourceAsciiCsv)) {
    $arguments += @("--source-ascii-csv", $SourceAsciiCsv)
}

& $pythonExe @arguments
$exitCode = Get-PetrelMcpLastExitCode
if ($exitCode -ne 0) {
    exit $exitCode
}
