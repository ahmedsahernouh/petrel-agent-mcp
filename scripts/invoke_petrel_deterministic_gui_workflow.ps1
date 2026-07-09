param(
    [string]$WorkflowId = "export_well_tops_ascii",
    [string]$SpecPath = "",
    [string]$ProjectName = "Petrel2010 demo project",
    [string]$ProjectFile = "D:\Computer\Code\Petrel_project\Petrel_DemoData_project\Petrel2010 demo project ExportPilot.pet",
    [string]$ProjectPath = "D:\Computer\Code\Petrel_project\Petrel_DemoData_project",
    [string]$PetrelVersion = "2018.2.0.5333",
    [string]$InventoryPackage = "",
    [string]$ExportPackage = "",
    [int]$PetrelProcessId = 0,
    [string]$LicenseProfile = "",

    [string]$LicensePackage = "",
    [ValidateSet("Dash", "Slash")]
    [string]$PetrelOptionStyle = "Slash",
    [string]$TargetSubfolder = "",
    [string]$Extension = "",
    [string]$OutputFileName = "",
    [string]$FormatPattern = "",
    [string]$TesseractPath = "",
    [string]$PythonPath = "",
    [string]$DriveLetter = "",
    [int]$TimeoutSeconds = 0,
    [int]$LicenseDialogTimeoutSeconds = 0,
    [int]$StableFileTicks = 0,
    [int]$FilePollSeconds = 0,
    [int]$WellTopsRelativeX = 0,
    [int]$WellTopsRelativeY = 0,
    [int]$ExportObjectRelativeX = 0,
    [int]$ExportObjectRelativeY = 0,
    [switch]$Execute,
    [switch]$OpenProjectWritable,
    [switch]$AllowExistingTarget,
    [switch]$NoRegister,
    [switch]$NoValidate,
    [switch]$KeepDriveMapping,
    [switch]$CoordinateFallback,
    [switch]$SkipImport,
    [switch]$ContextMenuKeyboard
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-LatestPackage {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$Pattern
    )

    if (-not (Test-Path -LiteralPath $Root -PathType Container)) {
        return ""
    }

    $item = Get-ChildItem -LiteralPath $Root -Directory -Filter $Pattern |
        Sort-Object LastWriteTimeUtc -Descending |
        Select-Object -First 1
    if ($null -eq $item) {
        return ""
    }
    return $item.FullName
}

function Invoke-External {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [int]$Timeout = 900
    )

    $tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("petrel_det_gui_" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Force -Path $tempRoot | Out-Null
    $stdoutPath = Join-Path $tempRoot "stdout.txt"
    $stderrPath = Join-Path $tempRoot "stderr.txt"
    $argumentLine = Join-ProcessArguments -Arguments $Arguments
    try {
        $process = Start-Process -FilePath $FilePath -ArgumentList $argumentLine -WorkingDirectory $script:RepoRoot -NoNewWindow -PassThru -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
        if (-not $process.WaitForExit($Timeout * 1000)) {
            try { $process.Kill() } catch { }
            throw "Timed out after $Timeout seconds running $FilePath"
        }
        $stdout = if (Test-Path -LiteralPath $stdoutPath) { Get-Content -LiteralPath $stdoutPath -Raw } else { "" }
        $stderr = if (Test-Path -LiteralPath $stderrPath) { Get-Content -LiteralPath $stderrPath -Raw } else { "" }
        $stdoutText = ConvertTo-SafeTrimmedString -Value $stdout
        $stderrText = ConvertTo-SafeTrimmedString -Value $stderr
        $exitCode = $process.ExitCode
        if ($null -eq $exitCode) {
            $exitCode = if ([string]::IsNullOrWhiteSpace($stderrText)) { 0 } else { 1 }
        }
        return [ordered]@{
            command = @($FilePath) + $Arguments
            exit_code = [int]$exitCode
            stdout = $stdoutText
            stderr = $stderrText
        }
    } finally {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function ConvertTo-SafeTrimmedString {
    param([AllowNull()][object]$Value)

    if ($null -eq $Value) {
        return ""
    }
    $text = [System.Management.Automation.LanguagePrimitives]::ConvertTo($Value, [string])
    if ($null -eq $text) {
        return ""
    }
    return $text.Trim()
}

function ConvertTo-ProcessArgument {
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$Value)

    if ($Value -ne "" -and $Value -notmatch '[\s"]') {
        return $Value
    }

    return '"' + ($Value -replace '"', '\"') + '"'
}

function Join-ProcessArguments {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)
    return (($Arguments | ForEach-Object { ConvertTo-ProcessArgument -Value $_ }) -join " ")
}

function Get-LabeledValue {
    param(
        [string]$Text,
        [string]$Label
    )

    $prefix = "$Label`:"
    foreach ($line in ($Text -split "`r?`n")) {
        if ($line.StartsWith($prefix)) {
            return $line.Substring($prefix.Length).Trim()
        }
    }
    return ""
}

function Add-SwitchArgument {
    param(
        [System.Collections.Generic.List[string]]$Arguments,
        [bool]$Enabled,
        [string]$Name
    )
    if ($Enabled) {
        $Arguments.Add("-$Name") | Out-Null
    }
}

function Read-JsonFile {
    param([string]$Path)
    return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$script:RepoRoot = Split-Path -Parent $scriptDir
. (Join-Path $scriptDir "petrel_mcp_dependencies.ps1")
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"

if ([string]::IsNullOrWhiteSpace($SpecPath)) {
    $SpecPath = Join-Path $script:RepoRoot ("petrel_gui_workflows\{0}.json" -f $WorkflowId)
}
if (-not (Test-Path -LiteralPath $SpecPath -PathType Leaf)) {
    throw "Deterministic GUI workflow spec not found: $SpecPath"
}

$spec = Read-JsonFile -Path $SpecPath
if ([string]$spec.id -ne $WorkflowId) {
    throw "Spec id '$($spec.id)' does not match requested WorkflowId '$WorkflowId'."
}
$adapterScript = [string]$spec.gui.adapter
$supportedAdapters = @("export_petrel_well_tops_ui.ps1", "export_petrel_well_tops_table_ui.ps1")
if ($supportedAdapters -notcontains $adapterScript) {
    throw "Unsupported deterministic GUI adapter: $adapterScript"
}
$isGuiTableAdapter = ($adapterScript -eq "export_petrel_well_tops_table_ui.ps1")

if ([string]::IsNullOrWhiteSpace($InventoryPackage)) {
    $InventoryPackage = Get-LatestPackage -Root (Join-Path $script:RepoRoot "build\inventory_pilots") -Pattern "*_inventory_*"
}
if ([string]::IsNullOrWhiteSpace($ExportPackage)) {
    $ExportPackage = Get-LatestPackage -Root (Join-Path $script:RepoRoot "build\export_pilots") -Pattern "*_export_*"
}
if ([string]::IsNullOrWhiteSpace($InventoryPackage)) {
    throw "Inventory package was not supplied and no latest inventory package was found."
}
if ([string]::IsNullOrWhiteSpace($ExportPackage)) {
    throw "Export package was not supplied and no latest export package was found."
}

$ProjectFile = (Resolve-Path -LiteralPath $ProjectFile).Path
$ProjectPath = (Resolve-Path -LiteralPath $ProjectPath).Path
$InventoryPackage = (Resolve-Path -LiteralPath $InventoryPackage).Path
$ExportPackage = (Resolve-Path -LiteralPath $ExportPackage).Path
$pythonExe = ""
if ($Execute -and -not $SkipImport) {
    $pythonExe = Resolve-PetrelMcpPython -ExplicitPath $PythonPath -ProjectRoot $script:RepoRoot
}

$defaults = $spec.gui.default_arguments
if ([string]::IsNullOrWhiteSpace($TargetSubfolder)) { $TargetSubfolder = [string]$defaults.target_subfolder }
if ([string]::IsNullOrWhiteSpace($Extension)) { $Extension = [string]$defaults.extension }
if ([string]::IsNullOrWhiteSpace($FormatPattern)) { $FormatPattern = [string]$defaults.format_pattern }
if ([string]::IsNullOrWhiteSpace($LicenseProfile)) { $LicenseProfile = [string]$defaults.license_profile }
if ([string]::IsNullOrWhiteSpace($LicensePackage)) { $LicensePackage = $LicenseProfile }
if ([string]::IsNullOrWhiteSpace($DriveLetter)) { $DriveLetter = [string]$defaults.drive_letter }
if ($TimeoutSeconds -le 0) { $TimeoutSeconds = [int]$defaults.timeout_seconds }
if ($LicenseDialogTimeoutSeconds -le 0) {
    $defaultLicenseTimeout = $defaults.PSObject.Properties["license_dialog_timeout_seconds"]
    if ($null -ne $defaultLicenseTimeout) { $LicenseDialogTimeoutSeconds = [int]$defaultLicenseTimeout.Value } else { $LicenseDialogTimeoutSeconds = 3 }
}
if ($StableFileTicks -le 0) {
    $defaultStableFileTicks = $defaults.PSObject.Properties["stable_file_ticks"]
    if ($null -ne $defaultStableFileTicks) { $StableFileTicks = [int]$defaultStableFileTicks.Value } else { $StableFileTicks = 1 }
}
if ($FilePollSeconds -le 0) {
    $defaultFilePollSeconds = $defaults.PSObject.Properties["file_poll_seconds"]
    if ($null -ne $defaultFilePollSeconds) { $FilePollSeconds = [int]$defaultFilePollSeconds.Value } else { $FilePollSeconds = 1 }
}
if ($WellTopsRelativeX -le 0) {
    $defaultValue = $defaults.PSObject.Properties["well_tops_relative_x"]
    if ($null -ne $defaultValue) { $WellTopsRelativeX = [int]$defaultValue.Value } else { $WellTopsRelativeX = 91 }
}
if ($WellTopsRelativeY -le 0) {
    $defaultValue = $defaults.PSObject.Properties["well_tops_relative_y"]
    if ($null -ne $defaultValue) { $WellTopsRelativeY = [int]$defaultValue.Value } else { $WellTopsRelativeY = 546 }
}
if ($ExportObjectRelativeX -le 0) {
    $defaultValue = $defaults.PSObject.Properties["export_object_relative_x"]
    if ($null -ne $defaultValue) { $ExportObjectRelativeX = [int]$defaultValue.Value } else { $ExportObjectRelativeX = 221 }
}
if ($ExportObjectRelativeY -le 0) {
    $defaultValue = $defaults.PSObject.Properties["export_object_relative_y"]
    if ($null -ne $defaultValue) { $ExportObjectRelativeY = [int]$defaultValue.Value } else { $ExportObjectRelativeY = 415 }
}
if (-not $ContextMenuKeyboard) {
    $defaultValue = $defaults.PSObject.Properties["context_menu_keyboard"]
    if ($null -ne $defaultValue -and [bool]$defaultValue.Value) { $ContextMenuKeyboard = $true }
}
if ([string]::IsNullOrWhiteSpace($OutputFileName)) {
    if ($isGuiTableAdapter) {
        $OutputFileName = "well_tops_project_data_table_detgui_$stamp.$Extension"
    } else {
        $OutputFileName = "well_tops_exportpilot_detgui_$stamp.$Extension"
    }
}
if ([IO.Path]::GetExtension($OutputFileName) -eq "") {
    $OutputFileName = "$OutputFileName.$Extension"
}

$runDir = Join-Path $ExportPackage "07_workflows_reports\automation_runs"
New-Item -ItemType Directory -Force -Path $runDir | Out-Null
$reportPath = Join-Path $runDir ("deterministic_gui_{0}_{1}.json" -f $WorkflowId, $stamp)
$targetFolder = Join-Path $ExportPackage $TargetSubfolder
$expectedOutput = Join-Path $targetFolder $OutputFileName

$petrelProcesses = @(Get-Process -Name "Petrel" -ErrorAction SilentlyContinue | ForEach-Object {
    [ordered]@{
        id = $_.Id
        main_window_title = $_.MainWindowTitle
        has_main_window = ($_.MainWindowHandle -ne 0)
    }
})

$report = [ordered]@{
    run_id = "deterministic_gui_${WorkflowId}_$stamp"
    created_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    workflow_id = $WorkflowId
    mode = if ($Execute) { "execute" } else { "dry_run" }
    spec_path = $SpecPath
    strategy = [string]$spec.strategy
    zero_gui_status = $spec.zero_gui
    project_name = $ProjectName
    petrel_version = $PetrelVersion
    project_file = $ProjectFile
    inventory_package = $InventoryPackage
    export_package = $ExportPackage
    target_subfolder = $TargetSubfolder
    output_file_name = $OutputFileName
    expected_output = $expectedOutput
    actual_output = $null
    actual_output_bytes = 0
    ui_status_path = ""
    ui_trace_path = ""
    ascii_import_report_path = ""
    parsed_csv = ""
    validation_report_path = ""
    deterministic_contract = [ordered]@{
        adapter = [string]$spec.gui.adapter
        fail_closed = [bool]$spec.gui.failure_policy.fail_closed
        preconditions = $spec.gui.preconditions
        state_anchors = $spec.gui.state_anchors
        actions = $spec.gui.actions
        postconditions = $spec.gui.postconditions
    }
    preflight = [ordered]@{
        project_file_exists = (Test-Path -LiteralPath $ProjectFile -PathType Leaf)
        project_path_exists = (Test-Path -LiteralPath $ProjectPath -PathType Container)
        export_package_exists = (Test-Path -LiteralPath $ExportPackage -PathType Container)
        inventory_package_exists = (Test-Path -LiteralPath $InventoryPackage -PathType Container)
        target_folder = $targetFolder
        ui_driver_exists = (Test-Path -LiteralPath (Join-Path $scriptDir $adapterScript) -PathType Leaf)
        importer_exists = if ($isGuiTableAdapter) {
            (Test-Path -LiteralPath (Join-Path $scriptDir "import_petrel_gui_well_tops_table.ps1") -PathType Leaf)
        } else {
            (Test-Path -LiteralPath (Join-Path $scriptDir "import_petrel_well_tops_ascii_export.py") -PathType Leaf)
        }
        petrel_processes = $petrelProcesses
        python_required = ($Execute -and -not $SkipImport)
        python_path = $pythonExe
    }
    command_preview = $null
    ui_driver_result = $null
    ui_driver_status = $null
    ascii_import_result = $null
    ascii_import_report = $null
    register_result = $null
    validation_result = $null
    postcondition_results = @()
    status = "pending"
    error = ""
    error_details = $null
}

$uiArgsList = New-Object System.Collections.Generic.List[string]
foreach ($item in @(
    "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $scriptDir $adapterScript),
    "-ProjectName", $ProjectName,
    "-ProjectFile", $ProjectFile,
    "-ProjectPath", $ProjectPath,
    "-PetrelVersion", $PetrelVersion,
    "-InventoryPackage", $InventoryPackage,
    "-ExportPackage", $ExportPackage,
    "-LicenseProfile", $LicenseProfile,
    "-LicensePackage", $LicensePackage,
    "-PetrelOptionStyle", $PetrelOptionStyle,
    "-TargetSubfolder", $TargetSubfolder,
    "-Extension", $Extension,
    "-OutputFileName", $OutputFileName,
    "-FormatPattern", $FormatPattern,
    "-DriveLetter", $DriveLetter,
    "-TimeoutSeconds", [string]$TimeoutSeconds,
    "-LicenseDialogTimeoutSeconds", [string]$LicenseDialogTimeoutSeconds,
    "-StableFileTicks", [string]$StableFileTicks,
    "-FilePollSeconds", [string]$FilePollSeconds
)) {
    $uiArgsList.Add([string]$item) | Out-Null
}
foreach ($item in @(
    "-WellTopsRelativeX", [string]$WellTopsRelativeX,
    "-WellTopsRelativeY", [string]$WellTopsRelativeY,
    "-ExportObjectRelativeX", [string]$ExportObjectRelativeX,
    "-ExportObjectRelativeY", [string]$ExportObjectRelativeY
)) {
    $uiArgsList.Add([string]$item) | Out-Null
}
if ($PetrelProcessId -gt 0) {
    $uiArgsList.Add("-PetrelProcessId") | Out-Null
    $uiArgsList.Add([string]$PetrelProcessId) | Out-Null
}
if (-not [string]::IsNullOrWhiteSpace($TesseractPath)) {
    $uiArgsList.Add("-TesseractPath") | Out-Null
    $uiArgsList.Add($TesseractPath) | Out-Null
}
Add-SwitchArgument -Arguments $uiArgsList -Enabled ([bool]$OpenProjectWritable) -Name "OpenProjectWritable"
Add-SwitchArgument -Arguments $uiArgsList -Enabled ([bool]$AllowExistingTarget) -Name "AllowExistingTarget"
# The deterministic runner owns final import, registration, and validation. Suppress
# the UI driver's duplicate manifest pass unless the whole runner is skipping it.
Add-SwitchArgument -Arguments $uiArgsList -Enabled $true -Name "NoRegister"
Add-SwitchArgument -Arguments $uiArgsList -Enabled $true -Name "NoValidate"
Add-SwitchArgument -Arguments $uiArgsList -Enabled ([bool]$KeepDriveMapping) -Name "KeepDriveMapping"
Add-SwitchArgument -Arguments $uiArgsList -Enabled ([bool]$CoordinateFallback) -Name "CoordinateFallback"
Add-SwitchArgument -Arguments $uiArgsList -Enabled ([bool]$ContextMenuKeyboard) -Name "ContextMenuKeyboard"
$report.command_preview = [ordered]@{
    file = "powershell.exe"
    arguments = @($uiArgsList)
}

try {
    if (-not $Execute) {
        $report.status = "dry_run"
        $report.postcondition_results = @(
            [ordered]@{ id = "would_launch_or_attach_petrel"; status = "not_executed"; reason = "Execute switch was not provided." },
            [ordered]@{ id = "would_export_ascii"; status = "not_executed"; expected_output = $expectedOutput },
            [ordered]@{ id = "would_parse_register_validate"; status = "not_executed"; reason = "Dry run only." }
        )
    } else {
        New-Item -ItemType Directory -Force -Path $targetFolder | Out-Null
        $uiResult = Invoke-External -FilePath "powershell.exe" -Arguments @($uiArgsList) -Timeout ($TimeoutSeconds + 240)
        $report.ui_driver_result = $uiResult
        $uiStatusPath = Get-LabeledValue -Text ([string]$uiResult["stdout"]) -Label "Status file"
        if (-not [string]::IsNullOrWhiteSpace($uiStatusPath) -and (Test-Path -LiteralPath $uiStatusPath -PathType Leaf)) {
            $report["ui_status_path"] = $uiStatusPath
            $report.ui_driver_status = Read-JsonFile -Path $uiStatusPath
            if ($null -ne $report.ui_driver_status -and $null -ne $report.ui_driver_status.run_id) {
                $traceCandidate = Join-Path $runDir ("{0}.trace.log" -f $report.ui_driver_status.run_id)
                if (Test-Path -LiteralPath $traceCandidate -PathType Leaf) {
                    $report["ui_trace_path"] = $traceCandidate
                }
            }
        }

        if ([int]$uiResult["exit_code"] -ne 0) {
            throw "UI driver failed with exit code $($uiResult["exit_code"])."
        }

        $exportedFiles = @()
        if ($null -ne $report.ui_driver_status -and $null -ne $report.ui_driver_status.files) {
            $exportedFiles = @($report.ui_driver_status.files | ForEach-Object { [string]$_ } | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf })
        }
        if ($exportedFiles.Count -eq 0 -and (Test-Path -LiteralPath $expectedOutput -PathType Leaf)) {
            $exportedFiles = @($expectedOutput)
        }
        if ($exportedFiles.Count -eq 0) {
            throw "UI driver returned success but no exported Well Tops ASCII file was found."
        }

        $asciiExport = [string]($exportedFiles | Where-Object { [IO.Path]::GetExtension($_) -ieq ".$Extension" } | Select-Object -First 1)
        if ([string]::IsNullOrWhiteSpace($asciiExport)) {
            $asciiExport = [string]($exportedFiles | Select-Object -First 1)
        }
        $asciiInfo = Get-Item -LiteralPath $asciiExport
        $report["actual_output"] = $asciiExport
        $report["actual_output_bytes"] = [int64]$asciiInfo.Length

        if (-not $SkipImport) {
            if ($isGuiTableAdapter) {
                $importArgs = @(
                    "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $scriptDir "import_petrel_gui_well_tops_table.ps1"),
                    "-GuiTablePaste", $asciiExport,
                    "-ProjectName", $ProjectName,
                    "-PetrelVersion", $PetrelVersion,
                    "-ExportPackage", $ExportPackage,
                    "-PythonPath", $pythonExe
                )
                $importResult = Invoke-External -FilePath "powershell.exe" -Arguments $importArgs -Timeout 300
            } else {
                $importer = Join-Path $scriptDir "import_petrel_well_tops_ascii_export.py"
                $importArgs = @(
                    $importer,
                    "--project-name", $ProjectName,
                    "--petrel-version", $PetrelVersion,
                    "--export-package", $ExportPackage,
                    "--ascii-export", $asciiExport,
                    "--creation-method", "deterministic_gui"
                )
                $importResult = Invoke-External -FilePath $pythonExe -Arguments $importArgs -Timeout 300
            }
            $report.ascii_import_result = $importResult
            $importReportPath = Get-LabeledValue -Text ([string]$importResult["stdout"]) -Label "Report"
            if (-not [string]::IsNullOrWhiteSpace($importReportPath) -and (Test-Path -LiteralPath $importReportPath -PathType Leaf)) {
                $report["ascii_import_report_path"] = $importReportPath
                $report.ascii_import_report = Read-JsonFile -Path $importReportPath
                if ($null -ne $report.ascii_import_report -and
                    $null -ne $report.ascii_import_report.outputs -and
                    $null -ne $report.ascii_import_report.outputs.parsed_csv) {
                    $report["parsed_csv"] = [string]$report.ascii_import_report.outputs.parsed_csv
                }
            }
            if ([int]$importResult["exit_code"] -ne 0) {
                throw "Well Tops importer failed with exit code $($importResult["exit_code"])."
            }
        }

        if (-not $NoRegister) {
            $registrarArgs = @(
                "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $scriptDir "register_petrel_file_exports.ps1"),
                "-ExportPackage", $ExportPackage,
                "-ProjectName", $ProjectName,
                "-PetrelVersion", $PetrelVersion,
                "-InventoryPackage", $InventoryPackage
            )
            $report.register_result = Invoke-External -FilePath "powershell.exe" -Arguments $registrarArgs -Timeout 300
        }

        if (-not $NoValidate) {
            $validatorArgs = @(
                "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $scriptDir "validate_export_package.ps1"),
                "-ExportPackage", $ExportPackage,
                "-UpdateManifest",
                "-WriteChecksums"
            )
            $report.validation_result = Invoke-External -FilePath "powershell.exe" -Arguments $validatorArgs -Timeout 600
            $validationReportPath = Get-LabeledValue -Text ([string]$report.validation_result["stdout"]) -Label "Report"
            if (-not [string]::IsNullOrWhiteSpace($validationReportPath)) {
                $report["validation_report_path"] = $validationReportPath
            }
        }

        $rowCount = 0
        if ($null -ne $report.ascii_import_report -and $null -ne $report.ascii_import_report.row_count) {
            $rowCount = [int]$report.ascii_import_report.row_count
        } elseif ($null -ne $report.ascii_import_report -and $null -ne $report.ascii_import_report.summary -and $null -ne $report.ascii_import_report.summary.gui_row_count) {
            $rowCount = [int]$report.ascii_import_report.summary.gui_row_count
        }
        $artifactPostconditionId = if ($isGuiTableAdapter) { "gui_table_file_written" } else { "ascii_file_written" }
        $importPostconditionId = if ($isGuiTableAdapter) { "gui_table_import_rows_gt_zero" } else { "ascii_import_rows_gt_zero" }
        $validationStatus = if ($NoValidate) { "skipped" } else { Get-LabeledValue -Text ([string]$report.validation_result["stdout"]) -Label "Validation status" }
        $report.postcondition_results = @(
            [ordered]@{ id = "ui_driver_exit_zero"; status = "passed"; exit_code = [int]$uiResult["exit_code"] },
            [ordered]@{ id = $artifactPostconditionId; status = "passed"; path = $asciiExport; bytes = $asciiInfo.Length },
            [ordered]@{ id = $importPostconditionId; status = if ($SkipImport) { "skipped" } elseif ($rowCount -gt 0) { "passed" } else { "failed" }; row_count = $rowCount },
            [ordered]@{ id = "manifest_validation"; status = if ($validationStatus -eq "failed") { "failed" } else { "passed" }; validation_status = $validationStatus }
        )
        $failedPostconditions = @($report.postcondition_results | Where-Object { $_.status -eq "failed" })
        if ($failedPostconditions.Count -gt 0) {
            throw "One or more deterministic GUI workflow postconditions failed."
        }
        $report.status = "passed"
    }
} catch {
    $report.status = "failed"
    $report.error = $_.Exception.Message
    $report.error_details = [ordered]@{
        position = $_.InvocationInfo.PositionMessage
        script_stack_trace = $_.ScriptStackTrace
        category = [string]$_.CategoryInfo
        fully_qualified_error_id = [string]$_.FullyQualifiedErrorId
    }
} finally {
    $report | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $reportPath -Encoding UTF8
}

Write-Output "Deterministic GUI workflow: $($report.status)"
Write-Output "Workflow: $WorkflowId"
Write-Output "Mode: $($report.mode)"
Write-Output "Report: $reportPath"
Write-Output "Expected output: $expectedOutput"
if (-not [string]::IsNullOrWhiteSpace([string]$report.actual_output)) {
    Write-Output "Actual output: $($report.actual_output)"
}

if ($report.status -eq "failed") {
    Write-Output "Error: $($report.error)"
    exit 1
}
