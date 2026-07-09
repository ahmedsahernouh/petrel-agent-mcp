param(
    [string]$ProjectDirectory = "D:\Computer\Code\Petrel_project\Petrel_DemoData_project",

    [string]$ProjectStem = "Petrel2010 demo project ExportPilot",

    [string]$ProjectFile = "D:\Computer\Code\Petrel_project\Petrel_DemoData_project\Petrel2010 demo project ExportPilot.pet",

    [string]$ProjectName = "Petrel2010 demo project",

    [string]$PetrelVersion = "2018.2.0.5333",

    [string]$InventoryPackage = "D:\Computer\Code\Petrel_project\build\inventory_pilots\Petrel2010_demo_project_inventory_20260701_055128",

    [string]$ExportPackage = "D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609",

    [string]$WorkflowName = "ExportPiloX",

    [string]$LicensePackage = "BatchProfile",

    [string]$StoreFile = "Data.ptd",

    [Parameter(Mandatory = $true)]
    [long]$Offset,

    [Parameter(Mandatory = $true)]
    [string]$ExpectedToken,

    [Parameter(Mandatory = $true)]
    [string]$ReplacementToken,

    [string]$ExpectedBridgeStepName = "post_export_register_validate",

    [string]$TargetBridgeStepName = "",

    [string]$OutputRoot = "D:\Computer\Code\Petrel_project\build\native_edit_experiments",

    [switch]$KeepPatch,

    [switch]$SkipRun,

    [switch]$NoValidate
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Assert-SameAsciiLength {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Expected,

        [Parameter(Mandatory = $true)]
        [string]$Replacement
    )

    $expectedBytes = [System.Text.Encoding]::ASCII.GetBytes($Expected)
    $replacementBytes = [System.Text.Encoding]::ASCII.GetBytes($Replacement)
    if ($expectedBytes.Length -ne $replacementBytes.Length) {
        throw "ReplacementToken must have same ASCII byte length as ExpectedToken. '$Expected'=$($expectedBytes.Length), '$Replacement'=$($replacementBytes.Length)."
    }
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
    return ""
}

function Read-JsonFile {
    param([Parameter(Mandatory = $true)][string]$Path)

    return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
}

function Invoke-PowerShellFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [AllowEmptyCollection()]
        [string[]]$Arguments = @()
    )

    Push-Location -LiteralPath $repoRoot
    try {
        $command = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $Path) + $Arguments
        $output = @(& powershell.exe @command 2>&1 | ForEach-Object { [string]$_ })
        $exitCode = $LASTEXITCODE
    } finally {
        Pop-Location
    }

    $stdout = $output -join "`n"
    if ($null -ne $exitCode -and $exitCode -ne 0) {
        throw "Script failed with exit code $exitCode`: $Path`n$stdout"
    }

    return [ordered]@{
        exit_code = $exitCode
        stdout = $stdout
        output = $output
    }
}

function Get-LatestBridgeStatusFile {
    param([Parameter(Mandatory = $true)][string]$RunDirectory)

    if (-not (Test-Path -LiteralPath $RunDirectory -PathType Container)) {
        return $null
    }

    return Get-ChildItem -LiteralPath $RunDirectory -Filter "petrel_export_mvp_bridge_*.json" |
        Sort-Object LastWriteTimeUtc -Descending |
        Select-Object -First 1
}

function Get-BridgeProbeStepName {
    param([string]$ProbePath)

    if ([string]::IsNullOrWhiteSpace($ProbePath) -or -not (Test-Path -LiteralPath $ProbePath -PathType Leaf)) {
        return ""
    }

    $row = Import-Csv -LiteralPath $ProbePath | Where-Object { $_.key -eq "step_name" } | Select-Object -First 1
    if ($null -eq $row) {
        return ""
    }
    return [string]$row.value
}

if ($ReplacementToken -eq $ExpectedToken) {
    throw "ReplacementToken must differ from ExpectedToken."
}
Assert-SameAsciiLength -Expected $ExpectedToken -Replacement $ReplacementToken

if ([string]::IsNullOrWhiteSpace($TargetBridgeStepName)) {
    if (-not [string]::IsNullOrWhiteSpace($ExpectedBridgeStepName) -and
        $ExpectedBridgeStepName.IndexOf($ExpectedToken, [System.StringComparison]::Ordinal) -ge 0) {
        $TargetBridgeStepName = $ExpectedBridgeStepName.Replace($ExpectedToken, $ReplacementToken)
    } else {
        $TargetBridgeStepName = $ExpectedBridgeStepName
    }
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
$snapshotScript = Join-Path $scriptDir "new_petrel_native_workflow_snapshot.ps1"
$compareScript = Join-Path $scriptDir "compare_petrel_native_workflow_snapshots.ps1"
$patchScript = Join-Path $scriptDir "patch_petrel_native_workflow_offset.ps1"
$runScript = Join-Path $scriptDir "run_petrel_full_export_mvp.ps1"

foreach ($requiredScript in @($snapshotScript, $compareScript, $patchScript, $runScript)) {
    if (-not (Test-Path -LiteralPath $requiredScript -PathType Leaf)) {
        throw "Required script not found: $requiredScript"
    }
}

$ProjectDirectory = (Resolve-Path -LiteralPath $ProjectDirectory).Path
$ProjectFile = (Resolve-Path -LiteralPath $ProjectFile).Path
$InventoryPackage = (Resolve-Path -LiteralPath $InventoryPackage).Path
$ExportPackage = (Resolve-Path -LiteralPath $ExportPackage).Path
$OutputRoot = if (Test-Path -LiteralPath $OutputRoot) { (Resolve-Path -LiteralPath $OutputRoot).Path } else { $OutputRoot }
New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null

$automationRunDir = Join-Path $ExportPackage "07_workflows_reports\automation_runs"
$bridgeBefore = Get-LatestBridgeStatusFile -RunDirectory $automationRunDir
$bridgeBeforePath = if ($null -ne $bridgeBefore) { $bridgeBefore.FullName } else { "" }
$bridgeBeforeWriteUtc = if ($null -ne $bridgeBefore) { $bridgeBefore.LastWriteTimeUtc } else { [datetime]::MinValue }

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$runRoot = Join-Path $OutputRoot "systemcmd_token_patch_export_$stamp"
New-Item -ItemType Directory -Force -Path $runRoot | Out-Null

$beforeSnapshot = ""
$afterPatchSnapshot = ""
$afterRestoreSnapshot = ""
$patchReportPath = ""
$restoreReportPath = ""
$patchCompareReportPath = ""
$restoreCompareReportPath = ""
$petrelStatusPath = ""
$validationReportPath = ""
$bridgeStatusPath = ""
$bridgeProbePath = ""
$bridgeProbeStepName = ""
$errorMessage = ""
$patchApplied = $false
$restoreAttempted = $false
$restored = $false
$restoreCompareClean = $null
$petrelStatus = $null
$bridgeStatus = $null
$validationSummary = $null

try {
    $beforeResult = Invoke-PowerShellFile -Path $snapshotScript -Arguments @(
        "-ProjectDirectory", $ProjectDirectory,
        "-ProjectStem", $ProjectStem,
        "-Label", "before_systemcmd_token_tool",
        "-OutputRoot", $OutputRoot
    )
    $beforeOutput = @($beforeResult.output)
    $beforeSnapshot = Get-PathFromOutput -Output $beforeOutput -Prefix "Snapshot:"
    if ([string]::IsNullOrWhiteSpace($beforeSnapshot)) {
        throw "Could not parse before snapshot from output: $($beforeOutput -join "`n")"
    }

    $patchResult = Invoke-PowerShellFile -Path $patchScript -Arguments @(
        "-ProjectDirectory", $ProjectDirectory,
        "-ProjectStem", $ProjectStem,
        "-RelativeStoreFile", $StoreFile,
        "-Offset", [string]$Offset,
        "-Expected", $ExpectedToken,
        "-Replace", $ReplacementToken
    )
    $patchOutput = @($patchResult.output)
    $patchReportPath = Get-PathFromOutput -Output $patchOutput -Prefix "Report:"
    if ([string]::IsNullOrWhiteSpace($patchReportPath)) {
        throw "Could not parse patch report from output: $($patchOutput -join "`n")"
    }
    $patchApplied = $true

    $afterPatchResult = Invoke-PowerShellFile -Path $snapshotScript -Arguments @(
        "-ProjectDirectory", $ProjectDirectory,
        "-ProjectStem", $ProjectStem,
        "-Label", "after_systemcmd_token_tool_patch",
        "-OutputRoot", $OutputRoot
    )
    $afterPatchOutput = @($afterPatchResult.output)
    $afterPatchSnapshot = Get-PathFromOutput -Output $afterPatchOutput -Prefix "Snapshot:"

    $patchCompareResult = Invoke-PowerShellFile -Path $compareScript -Arguments @(
        "-BeforeSnapshot", $beforeSnapshot,
        "-AfterSnapshot", $afterPatchSnapshot,
        "-ProjectStem", $ProjectStem,
        "-TermsCsv", "$ExpectedToken|$ReplacementToken|SystemCmd|powershell.exe|StepName|BXML|LZ4",
        "-OutputRoot", $OutputRoot
    )
    $patchCompareOutput = @($patchCompareResult.output)
    $patchCompareReportPath = Get-PathFromOutput -Output $patchCompareOutput -Prefix "Report:"

    if (-not $SkipRun) {
        $runArgs = @(
            "-ProjectFile", $ProjectFile,
            "-ProjectName", $ProjectName,
            "-PetrelVersion", $PetrelVersion,
            "-InventoryPackage", $InventoryPackage,
            "-ExportPackage", $ExportPackage,
            "-WorkflowName", $WorkflowName,
            "-LicensePackage", $LicensePackage
        )
        if ($NoValidate) {
            $runArgs += "-NoValidate"
        }
        $runResult = Invoke-PowerShellFile -Path $runScript -Arguments $runArgs
        $runOutput = @($runResult.output)
        $petrelStatusPath = Get-PathFromOutput -Output $runOutput -Prefix "Status file:"
        if ([string]::IsNullOrWhiteSpace($petrelStatusPath)) {
            throw "Could not parse Petrel status path from output: $($runOutput -join "`n")"
        }
        $petrelStatus = Read-JsonFile -Path $petrelStatusPath
        if ($petrelStatus.workflow_execution_status -ne "confirmed" -or $petrelStatus.validation_status -notin @("passed", "skipped")) {
            throw "Petrel workflow did not complete cleanly. Status: $petrelStatusPath"
        }

        if (Test-Path -LiteralPath $petrelStatus.run_log_path -PathType Leaf) {
            $runLogText = Get-Content -LiteralPath $petrelStatus.run_log_path -Raw
            if ($runLogText -notmatch "Status:\s+Workflow run OK") {
                throw "Petrel run log does not contain workflow OK status: $($petrelStatus.run_log_path)"
            }
            if ($runLogText -notmatch "Executing System command") {
                throw "Petrel run log does not show the System command execution: $($petrelStatus.run_log_path)"
            }
        }

        $bridgeAfter = Get-ChildItem -LiteralPath $automationRunDir -Filter "petrel_export_mvp_bridge_*.json" |
            Where-Object { $_.LastWriteTimeUtc -gt $bridgeBeforeWriteUtc -or $_.FullName -ne $bridgeBeforePath } |
            Sort-Object LastWriteTimeUtc -Descending |
            Select-Object -First 1
        if ($null -eq $bridgeAfter) {
            throw "No new bridge status JSON was written by the patched System command."
        }

        $bridgeStatusPath = $bridgeAfter.FullName
        $bridgeStatus = Read-JsonFile -Path $bridgeStatusPath
        if ($bridgeStatus.step_name -ne $TargetBridgeStepName) {
            throw "Bridge step_name mismatch. Expected '$TargetBridgeStepName', got '$($bridgeStatus.step_name)'. Status: $bridgeStatusPath"
        }
        if ($bridgeStatus.validation_status -notin @("passed", "skipped")) {
            throw "Bridge validation did not pass. Status: $bridgeStatusPath"
        }
        $bridgeProbePath = [string]$bridgeStatus.probe_file
        $bridgeProbeStepName = Get-BridgeProbeStepName -ProbePath $bridgeProbePath
        if ($bridgeProbeStepName -ne $TargetBridgeStepName) {
            throw "Bridge probe step_name mismatch. Expected '$TargetBridgeStepName', got '$bridgeProbeStepName'. Probe: $bridgeProbePath"
        }

        $latestValidation = Get-ChildItem -LiteralPath (Join-Path $ExportPackage "07_workflows_reports\validation_reports") -Filter "export_validation_*.json" |
            Sort-Object LastWriteTimeUtc -Descending |
            Select-Object -First 1
        if ($null -ne $latestValidation) {
            $validationReportPath = $latestValidation.FullName
            $validationJson = Read-JsonFile -Path $validationReportPath
            $validationSummary = [ordered]@{
                report_path = $validationReportPath
                row_count = $validationJson.row_count
                validated_count = $validationJson.validated_count
                failed_count = $validationJson.failed_count
                status = $validationJson.status
            }
        }
    }
} catch {
    $errorMessage = $_.Exception.Message
} finally {
    if ($patchApplied -and -not $KeepPatch) {
        $restoreAttempted = $true
        try {
            $restoreResult = Invoke-PowerShellFile -Path $patchScript -Arguments @(
                "-ProjectDirectory", $ProjectDirectory,
                "-ProjectStem", $ProjectStem,
                "-RelativeStoreFile", $StoreFile,
                "-Offset", [string]$Offset,
                "-Expected", $ReplacementToken,
                "-Replace", $ExpectedToken
            )
            $restoreOutput = @($restoreResult.output)
            $restoreReportPath = Get-PathFromOutput -Output $restoreOutput -Prefix "Report:"
            $restored = $true

            $afterRestoreResult = Invoke-PowerShellFile -Path $snapshotScript -Arguments @(
                "-ProjectDirectory", $ProjectDirectory,
                "-ProjectStem", $ProjectStem,
                "-Label", "after_systemcmd_token_tool_restore",
                "-OutputRoot", $OutputRoot
            )
            $afterRestoreOutput = @($afterRestoreResult.output)
            $afterRestoreSnapshot = Get-PathFromOutput -Output $afterRestoreOutput -Prefix "Snapshot:"

            if (-not [string]::IsNullOrWhiteSpace($beforeSnapshot) -and -not [string]::IsNullOrWhiteSpace($afterRestoreSnapshot)) {
                $restoreCompareResult = Invoke-PowerShellFile -Path $compareScript -Arguments @(
                    "-BeforeSnapshot", $beforeSnapshot,
                    "-AfterSnapshot", $afterRestoreSnapshot,
                    "-ProjectStem", $ProjectStem,
                    "-TermsCsv", "$ExpectedToken|$ReplacementToken|SystemCmd|powershell.exe|StepName|BXML|LZ4",
                    "-OutputRoot", $OutputRoot
                )
                $restoreCompareOutput = @($restoreCompareResult.output)
                $restoreCompareReportPath = Get-PathFromOutput -Output $restoreCompareOutput -Prefix "Report:"
                if (-not [string]::IsNullOrWhiteSpace($restoreCompareReportPath)) {
                    $restoreCompare = Read-JsonFile -Path $restoreCompareReportPath
                    $changedStores = @($restoreCompare.store_summaries | Where-Object { $_.changed })
                    $restoreCompareClean = ($changedStores.Count -eq 0)
                }
            }
        } catch {
            if ([string]::IsNullOrWhiteSpace($errorMessage)) {
                $errorMessage = "Restore failed: $($_.Exception.Message)"
            } else {
                $errorMessage = "$errorMessage`nRestore failed: $($_.Exception.Message)"
            }
        }
    }
}

$status = if ([string]::IsNullOrWhiteSpace($errorMessage) -and ($KeepPatch -or $restored -or -not $patchApplied)) { "passed" } else { "failed" }
$report = [ordered]@{
    created_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    status = $status
    project_directory = $ProjectDirectory
    project_stem = $ProjectStem
    project_file = $ProjectFile
    export_package = $ExportPackage
    workflow_name = $WorkflowName
    store_file = $StoreFile
    offset = $Offset
    expected_token = $ExpectedToken
    replacement_token = $ReplacementToken
    expected_bridge_step_name = $ExpectedBridgeStepName
    target_bridge_step_name = $TargetBridgeStepName
    keep_patch = [bool]$KeepPatch
    skip_run = [bool]$SkipRun
    patch_applied = $patchApplied
    restore_attempted = $restoreAttempted
    restored = $restored
    restore_compare_clean = $restoreCompareClean
    before_snapshot = $beforeSnapshot
    after_patch_snapshot = $afterPatchSnapshot
    after_restore_snapshot = $afterRestoreSnapshot
    patch_report = $patchReportPath
    restore_report = $restoreReportPath
    patch_compare_report = $patchCompareReportPath
    restore_compare_report = $restoreCompareReportPath
    petrel_status_path = $petrelStatusPath
    petrel_status = $petrelStatus
    bridge_status_path = $bridgeStatusPath
    bridge_status = $bridgeStatus
    bridge_probe_path = $bridgeProbePath
    bridge_probe_step_name = $bridgeProbeStepName
    validation = $validationSummary
    error = $errorMessage
}

$reportPath = Join-Path $runRoot "systemcmd_token_patch_export_report.json"
$summaryPath = Join-Path $runRoot "systemcmd_token_patch_export_summary.md"
$report | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $reportPath -Encoding UTF8

$md = @(
    "# SystemCmd Token Patch Export",
    "",
    "- Created UTC: $($report.created_at_utc)",
    "- Status: $($report.status)",
    "- Store file: $StoreFile",
    "- Offset: $Offset",
    "- Patch: $ExpectedToken -> $ReplacementToken",
    "- Expected bridge step: $ExpectedBridgeStepName",
    "- Target bridge step: $TargetBridgeStepName",
    "- Patch report: $patchReportPath",
    "- Restore report: $restoreReportPath",
    "- Petrel status: $petrelStatusPath",
    "- Bridge status: $bridgeStatusPath",
    "- Bridge probe: $bridgeProbePath",
    "- Restored: $restored",
    "- Restore compare clean: $restoreCompareClean",
    "",
    "## Snapshots",
    "",
    "- Before: $beforeSnapshot",
    "- After patch: $afterPatchSnapshot",
    "- After restore: $afterRestoreSnapshot",
    "- Patch compare: $patchCompareReportPath",
    "- Restore compare: $restoreCompareReportPath"
)
if ($null -ne $validationSummary) {
    $md += @(
        "",
        "## Validation",
        "",
        "- Report: $($validationSummary.report_path)",
        "- Status: $($validationSummary.status)",
        "- Rows: $($validationSummary.row_count)",
        "- Failed: $($validationSummary.failed_count)"
    )
}
if (-not [string]::IsNullOrWhiteSpace($errorMessage)) {
    $md += @("", "## Error", "", $errorMessage)
}
$md | Set-Content -LiteralPath $summaryPath -Encoding UTF8

Write-Output "SystemCmd token patch export: $status"
Write-Output "Report: $reportPath"
Write-Output "Summary: $summaryPath"
Write-Output "Patch report: $patchReportPath"
Write-Output "Restore report: $restoreReportPath"
Write-Output "Petrel status: $petrelStatusPath"
Write-Output "Bridge status: $bridgeStatusPath"
Write-Output "Bridge probe: $bridgeProbePath"

if ($status -ne "passed") {
    exit 3
}
