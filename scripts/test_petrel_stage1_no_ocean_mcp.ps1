param(
    [string]$OutputRoot = "D:\Computer\Code\Petrel_project\build\stage1_no_ocean_mcp"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [scriptblock]$Command,

        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    Write-Output "Running: $Name"
    $output = & $Command
    $exitCode = $LASTEXITCODE
    if ($null -ne $exitCode -and $exitCode -ne 0) {
        throw "$Name failed with exit code $exitCode.`n$($output -join "`n")"
    }
    return @($output)
}

function Get-PathFromOutput {
    param(
        [string[]]$Output,
        [string]$Prefix
    )

    foreach ($line in $Output) {
        if ($line -match "^$([regex]::Escape($Prefix))\s*(.+)$") {
            return $Matches[1].Trim()
        }
    }
    throw "Could not find '$Prefix' in output:`n$($Output -join "`n")"
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
. (Join-Path $scriptDir "petrel_mcp_dependencies.ps1")
$python = Resolve-PetrelMcpPython -ProjectRoot $repoRoot

New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$serverSmokeOutput = Invoke-Checked -Name "MCP server smoke" -Command {
    & $python (Join-Path $scriptDir "test_petrel_mcp_server.py")
}

$configSmokeOutput = Invoke-Checked -Name "MCP client config smoke" -Command {
    & $python (Join-Path $scriptDir "test_petrel_mcp_client_configs.py")
}

$mvpOutput = Invoke-Checked -Name "MVP generation" -Command {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $scriptDir "build_petrel_full_export_mvp.ps1")
}

$openOutput = Invoke-Checked -Name "Petrel project open dry-run writable command" -Command {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $scriptDir "invoke_petrel_export_pilot.ps1") `
        -Mode OpenProject `
        -PetrelOptionStyle Slash `
        -OpenProjectWritable `
        -DryRun `
        -NoValidate
}
$openStatusPath = Get-PathFromOutput -Output $openOutput -Prefix "Status file:"
$openStatus = Get-Content -LiteralPath $openStatusPath -Raw | ConvertFrom-Json
if ($openStatus.launched -ne $false -or $openStatus.dry_run -ne $true -or $openStatus.validation_status -ne "skipped") {
    throw "OpenProject dry-run status did not match expected safe state: $openStatusPath"
}

$beforeOutput = Invoke-Checked -Name "Native snapshot before baseline" -Command {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $scriptDir "new_petrel_native_workflow_snapshot.ps1") `
        -Label "stage1_before_nochange"
}
$beforeSnapshot = Get-PathFromOutput -Output $beforeOutput -Prefix "Snapshot:"

$afterOutput = Invoke-Checked -Name "Native snapshot after baseline" -Command {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $scriptDir "new_petrel_native_workflow_snapshot.ps1") `
        -Label "stage1_after_nochange"
}
$afterSnapshot = Get-PathFromOutput -Output $afterOutput -Prefix "Snapshot:"

$compareOutput = Invoke-Checked -Name "Native snapshot compare baseline" -Command {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $scriptDir "compare_petrel_native_workflow_snapshots.ps1") `
        -BeforeSnapshot $beforeSnapshot `
        -AfterSnapshot $afterSnapshot
}
$compareReportPath = Get-PathFromOutput -Output $compareOutput -Prefix "Report:"
$compareReport = Get-Content -LiteralPath $compareReportPath -Raw | ConvertFrom-Json
$changedStores = @($compareReport.store_summaries | Where-Object { $_.changed -eq $true -or $_.diff_range_count -ne 0 })
if ($changedStores.Count -gt 0) {
    throw "Unchanged baseline snapshot compare found differences: $compareReportPath"
}

$result = [ordered]@{
    created_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    status = "passed"
    repo_root = $repoRoot
    mcp_server_smoke = "passed"
    mcp_client_config_smoke = "passed"
    mvp_generation = "passed"
    open_project_dry_run = [ordered]@{
        status_path = $openStatusPath
        launched = $openStatus.launched
        dry_run = $openStatus.dry_run
        open_project_writable = $openStatus.open_project_writable
        validation_status = $openStatus.validation_status
    }
    before_snapshot = $beforeSnapshot
    after_snapshot = $afterSnapshot
    compare_report = $compareReportPath
    store_summaries = $compareReport.store_summaries
}

$jsonPath = Join-Path $OutputRoot "stage1_no_ocean_mcp_validation_$stamp.json"
$mdPath = Join-Path $OutputRoot "stage1_no_ocean_mcp_validation_$stamp.md"
$result | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $jsonPath -Encoding UTF8

$md = @(
    "# Stage 1 No-Ocean MCP Validation",
    "",
    "- Created UTC: $($result.created_at_utc)",
    "- Status: $($result.status)",
    "- Repo root: $repoRoot",
    "- MCP server smoke: passed",
    "- MCP client config smoke: passed",
    "- MVP generation: passed",
    "- Open project dry-run status: $openStatusPath",
    "- Before snapshot: $beforeSnapshot",
    "- After snapshot: $afterSnapshot",
    "- Compare report: $compareReportPath",
    "",
    "## Store Baseline",
    "",
    "| Store | Changed | Length delta | Diff ranges |",
    "| --- | --- | ---: | ---: |"
)
foreach ($store in $compareReport.store_summaries) {
    $md += "| $($store.store_file) | $($store.changed) | $($store.length_delta) | $($store.diff_range_count) |"
}
$md | Set-Content -LiteralPath $mdPath -Encoding UTF8

Write-Output "Stage 1 no-Ocean MCP validation: passed"
Write-Output "Report: $jsonPath"
Write-Output "Summary: $mdPath"
