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

    [long]$Offset = 173201036,

    [string]$ExpectedTail = "_donor.sgy",

    [Parameter(Mandatory = $true)]
    [string]$ReplacementTail,

    [string]$OutputPrefix = "orig_amp_exportpilot",

    [string]$OutputSubfolder = "03_seismic\segy",

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
        throw "ReplacementTail must have same ASCII byte length as ExpectedTail. '$Expected'=$($expectedBytes.Length), '$Replacement'=$($replacementBytes.Length)."
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
        [string[]]$Arguments = @(),

        [int]$TimeoutSeconds = 3600
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
    $stderr = ""
    if ($null -ne $exitCode -and $exitCode -ne 0) {
        throw "Script failed with exit code $exitCode`: $Path`n$stdout"
    }

    return [ordered]@{
        exit_code = $exitCode
        stdout = $stdout
        stderr = $stderr
        output = $output
    }
}

if (-not $ExpectedTail.EndsWith(".sgy", [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "ExpectedTail must end with .sgy: $ExpectedTail"
}
if (-not $ReplacementTail.EndsWith(".sgy", [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "ReplacementTail must end with .sgy: $ReplacementTail"
}
if ($ReplacementTail -eq $ExpectedTail) {
    throw "ReplacementTail must differ from ExpectedTail."
}
Assert-SameAsciiLength -Expected $ExpectedTail -Replacement $ReplacementTail

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

$targetOutputFile = Join-Path (Join-Path $ExportPackage $OutputSubfolder) "$OutputPrefix$ReplacementTail"
$targetOutputName = [System.IO.Path]::GetFileNameWithoutExtension($targetOutputFile)
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$runRoot = Join-Path $OutputRoot "segy_filename_patch_export_$stamp"
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
$errorMessage = ""
$patchApplied = $false
$restoreAttempted = $false
$restored = $false
$petrelStatus = $null
$targetOutput = $null
$validationSummary = $null

try {
    $beforeResult = Invoke-PowerShellFile -Path $snapshotScript -TimeoutSeconds 300 -Arguments @(
        "-ProjectDirectory", $ProjectDirectory,
        "-ProjectStem", $ProjectStem,
        "-Label", "before_segy_filename_tool",
        "-OutputRoot", $OutputRoot
    )
    $beforeOutput = @($beforeResult.output)
    $beforeSnapshot = Get-PathFromOutput -Output $beforeOutput -Prefix "Snapshot:"
    if ([string]::IsNullOrWhiteSpace($beforeSnapshot)) {
        throw "Could not parse before snapshot from output: $($beforeOutput -join "`n")"
    }

    $patchResult = Invoke-PowerShellFile -Path $patchScript -TimeoutSeconds 300 -Arguments @(
        "-ProjectDirectory", $ProjectDirectory,
        "-ProjectStem", $ProjectStem,
        "-RelativeStoreFile", $StoreFile,
        "-Offset", [string]$Offset,
        "-Expected", $ExpectedTail,
        "-Replace", $ReplacementTail
    )
    $patchOutput = @($patchResult.output)
    $patchReportPath = Get-PathFromOutput -Output $patchOutput -Prefix "Report:"
    if ([string]::IsNullOrWhiteSpace($patchReportPath)) {
        throw "Could not parse patch report from output: $($patchOutput -join "`n")"
    }
    $patchApplied = $true

    $afterPatchResult = Invoke-PowerShellFile -Path $snapshotScript -TimeoutSeconds 300 -Arguments @(
        "-ProjectDirectory", $ProjectDirectory,
        "-ProjectStem", $ProjectStem,
        "-Label", "after_segy_filename_tool_patch",
        "-OutputRoot", $OutputRoot
    )
    $afterPatchOutput = @($afterPatchResult.output)
    $afterPatchSnapshot = Get-PathFromOutput -Output $afterPatchOutput -Prefix "Snapshot:"

    $patchCompareResult = Invoke-PowerShellFile -Path $compareScript -TimeoutSeconds 900 -Arguments @(
        "-BeforeSnapshot", $beforeSnapshot,
        "-AfterSnapshot", $afterPatchSnapshot,
        "-ProjectStem", $ProjectStem,
        "-TermsCsv", "$ExpectedTail|$ReplacementTail|ExportSeismicCmd|BXML|LZ4",
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
        $runResult = Invoke-PowerShellFile -Path $runScript -TimeoutSeconds 3600 -Arguments $runArgs
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
            if ($runLogText -notmatch [regex]::Escape($targetOutputName)) {
                throw "Petrel run log does not mention expected output name '$targetOutputName': $($petrelStatus.run_log_path)"
            }
        }

        if (-not (Test-Path -LiteralPath $targetOutputFile -PathType Leaf)) {
            throw "Expected patched output was not created: $targetOutputFile"
        }
        $targetItem = Get-Item -LiteralPath $targetOutputFile
        $targetHash = Get-FileHash -LiteralPath $targetOutputFile -Algorithm SHA256
        $targetOutput = [ordered]@{
            path = $targetItem.FullName
            length_bytes = $targetItem.Length
            last_write_time = $targetItem.LastWriteTime.ToString("o")
            sha256 = $targetHash.Hash.ToLowerInvariant()
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
            $restoreResult = Invoke-PowerShellFile -Path $patchScript -TimeoutSeconds 300 -Arguments @(
                "-ProjectDirectory", $ProjectDirectory,
                "-ProjectStem", $ProjectStem,
                "-RelativeStoreFile", $StoreFile,
                "-Offset", [string]$Offset,
                "-Expected", $ReplacementTail,
                "-Replace", $ExpectedTail
            )
            $restoreOutput = @($restoreResult.output)
            $restoreReportPath = Get-PathFromOutput -Output $restoreOutput -Prefix "Report:"
            $restored = $true

            $afterRestoreResult = Invoke-PowerShellFile -Path $snapshotScript -TimeoutSeconds 300 -Arguments @(
                "-ProjectDirectory", $ProjectDirectory,
                "-ProjectStem", $ProjectStem,
                "-Label", "after_segy_filename_tool_restore",
                "-OutputRoot", $OutputRoot
            )
            $afterRestoreOutput = @($afterRestoreResult.output)
            $afterRestoreSnapshot = Get-PathFromOutput -Output $afterRestoreOutput -Prefix "Snapshot:"

            if (-not [string]::IsNullOrWhiteSpace($beforeSnapshot) -and -not [string]::IsNullOrWhiteSpace($afterRestoreSnapshot)) {
                $restoreCompareResult = Invoke-PowerShellFile -Path $compareScript -TimeoutSeconds 900 -Arguments @(
                    "-BeforeSnapshot", $beforeSnapshot,
                    "-AfterSnapshot", $afterRestoreSnapshot,
                    "-ProjectStem", $ProjectStem,
                    "-TermsCsv", "$ExpectedTail|$ReplacementTail|ExportSeismicCmd|BXML|LZ4",
                    "-OutputRoot", $OutputRoot
                )
                $restoreCompareOutput = @($restoreCompareResult.output)
                $restoreCompareReportPath = Get-PathFromOutput -Output $restoreCompareOutput -Prefix "Report:"
            }
        } catch {
            if ([string]::IsNullOrWhiteSpace($errorMessage)) {
                $errorMessage = "Restore failed: $($_.Exception.Message)"
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
    expected_tail = $ExpectedTail
    replacement_tail = $ReplacementTail
    output_prefix = $OutputPrefix
    target_output_file = $targetOutputFile
    keep_patch = [bool]$KeepPatch
    skip_run = [bool]$SkipRun
    patch_applied = $patchApplied
    restore_attempted = $restoreAttempted
    restored = $restored
    before_snapshot = $beforeSnapshot
    after_patch_snapshot = $afterPatchSnapshot
    after_restore_snapshot = $afterRestoreSnapshot
    patch_report = $patchReportPath
    restore_report = $restoreReportPath
    patch_compare_report = $patchCompareReportPath
    restore_compare_report = $restoreCompareReportPath
    petrel_status_path = $petrelStatusPath
    petrel_status = $petrelStatus
    target_output = $targetOutput
    validation = $validationSummary
    error = $errorMessage
}

$reportPath = Join-Path $runRoot "segy_filename_patch_export_report.json"
$summaryPath = Join-Path $runRoot "segy_filename_patch_export_summary.md"
$report | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $reportPath -Encoding UTF8

$md = @(
    "# SEG-Y Filename Patch Export",
    "",
    "- Created UTC: $($report.created_at_utc)",
    "- Status: $($report.status)",
    "- Store file: $StoreFile",
    "- Offset: $Offset",
    "- Patch: $ExpectedTail -> $ReplacementTail",
    "- Target output: $targetOutputFile",
    "- Patch report: $patchReportPath",
    "- Restore report: $restoreReportPath",
    "- Petrel status: $petrelStatusPath",
    "- Validation report: $validationReportPath",
    "- Restored: $restored",
    "",
    "## Snapshots",
    "",
    "- Before: $beforeSnapshot",
    "- After patch: $afterPatchSnapshot",
    "- After restore: $afterRestoreSnapshot",
    "- Patch compare: $patchCompareReportPath",
    "- Restore compare: $restoreCompareReportPath"
)
if ($null -ne $targetOutput) {
    $md += @(
        "",
        "## Output",
        "",
        "- File: $($targetOutput.path)",
        "- Bytes: $($targetOutput.length_bytes)",
        "- SHA256: $($targetOutput.sha256)"
    )
}
if (-not [string]::IsNullOrWhiteSpace($errorMessage)) {
    $md += @("", "## Error", "", $errorMessage)
}
$md | Set-Content -LiteralPath $summaryPath -Encoding UTF8

Write-Output "SEG-Y filename patch export: $status"
Write-Output "Report: $reportPath"
Write-Output "Summary: $summaryPath"
Write-Output "Patch report: $patchReportPath"
Write-Output "Restore report: $restoreReportPath"
Write-Output "Petrel status: $petrelStatusPath"
Write-Output "Target output: $targetOutputFile"

if ($status -ne "passed") {
    exit 3
}
