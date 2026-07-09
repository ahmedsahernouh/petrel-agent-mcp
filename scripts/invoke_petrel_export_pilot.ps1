param(
    [string]$ProjectName = "Petrel2010 demo project",

    [string]$ProjectFile = "D:\Computer\Code\Petrel_project\Petrel_DemoData_project\Petrel2010 demo project.pet",

    [string]$ProjectPath = "D:\Computer\Code\Petrel_project\Petrel_DemoData_project",

    [string]$PetrelExe = "",

    [string]$PetrelVersion = "2018.2.0.5333",

    [string]$InventoryRoot = "D:\Computer\Code\Petrel_project\build\inventory_pilots",

    [string]$ExportRoot = "D:\Computer\Code\Petrel_project\build\export_pilots",

    [string]$InventoryPackage = "",

    [string]$ExportPackage = "",

    [switch]$CreateNewPackages,

    [ValidateSet("Prepare", "OpenProject", "RunWorkflow", "ExecMethod", "ValidateOnly")]
    [string]$Mode = "Prepare",

    [string]$WorkflowName = "",

    [string]$ExecAssembly = "",

    [string]$ExecMethod = "",

    [string]$LicensePackage = "",

    [ValidateSet("Dash", "Slash")]
    [string]$PetrelOptionStyle = "Dash",

    [string]$StringParameters = "",

    [string]$NumericParameters = "",

    [switch]$DryRun,

    [switch]$Wait,

    [switch]$NoValidate,

    [switch]$OpenProjectWritable
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Find-PetrelExecutable {
    param([string]$RequestedPath)

    $candidates = @()
    if (-not [string]::IsNullOrWhiteSpace($RequestedPath)) {
        $candidates += $RequestedPath
    }

    $pathCommand = Get-Command "Petrel.exe" -ErrorAction SilentlyContinue
    if ($null -ne $pathCommand) {
        $candidates += $pathCommand.Source
    }

    $candidates += @(
        "C:\Program Files\Schlumberger\Petrel 2018\Petrel.exe",
        "C:\Program Files\SLB\Petrel 2018\Petrel.exe",
        "C:\Program Files (x86)\Schlumberger\Petrel 2018\Petrel.exe"
    )

    foreach ($candidate in $candidates) {
        if (-not [string]::IsNullOrWhiteSpace($candidate) -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }

    throw "Could not find Petrel.exe. Pass -PetrelExe with the full path."
}

function Get-LatestPackage {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Root,

        [Parameter(Mandatory = $true)]
        [string]$Pattern
    )

    if (-not (Test-Path -LiteralPath $Root)) {
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

function Add-PetrelOption {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [System.Collections.Generic.List[string]]$Arguments,

        [Parameter(Mandatory = $true)]
        [string]$Name,

        [string]$Value = "",

        [ValidateSet("Dash", "Slash")]
        [string]$Style = "Dash"
    )

    $prefix = if ($Style -eq "Slash") { "/" } else { "-" }
    $Arguments.Add("$prefix$Name")
    if (-not [string]::IsNullOrWhiteSpace($Value)) {
        $Arguments.Add($Value)
    }
}

function Quote-CmdArgument {
    param([Parameter(Mandatory = $true)][string]$Value)

    if ($Value -match '[\s"&|<>]') {
        return '"' + ($Value -replace '"', '\"') + '"'
    }

    return $Value
}

function Escape-CmdSetValue {
    param([Parameter(Mandatory = $true)][string]$Value)

    return $Value -replace '"', '\"'
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir

$ProjectFile = (Resolve-Path -LiteralPath $ProjectFile).Path
$ProjectPath = (Resolve-Path -LiteralPath $ProjectPath).Path
$PetrelExe = Find-PetrelExecutable -RequestedPath $PetrelExe

if ($Mode -eq "RunWorkflow" -and [string]::IsNullOrWhiteSpace($WorkflowName)) {
    throw "-WorkflowName is required when -Mode RunWorkflow is used."
}

if ($Mode -eq "ExecMethod" -and ([string]::IsNullOrWhiteSpace($ExecAssembly) -or [string]::IsNullOrWhiteSpace($ExecMethod))) {
    throw "-ExecAssembly and -ExecMethod are required when -Mode ExecMethod is used."
}

if ($CreateNewPackages -or [string]::IsNullOrWhiteSpace($InventoryPackage)) {
    if (-not $CreateNewPackages) {
        $InventoryPackage = Get-LatestPackage -Root $InventoryRoot -Pattern "*_inventory_*"
    }

    if ($CreateNewPackages -or [string]::IsNullOrWhiteSpace($InventoryPackage)) {
        $newInventoryScript = Join-Path $scriptDir "new_inventory_package.ps1"
        $InventoryPackage = & $newInventoryScript `
            -ProjectName $ProjectName `
            -ProjectPath $ProjectPath `
            -OutputRoot $InventoryRoot `
            -PetrelVersion $PetrelVersion `
            -Scope "automated_export_pilot" `
            -Operator $env:USERNAME
    }
}

if ($CreateNewPackages -or [string]::IsNullOrWhiteSpace($ExportPackage)) {
    if (-not $CreateNewPackages) {
        $ExportPackage = Get-LatestPackage -Root $ExportRoot -Pattern "*_export_*"
    }

    if ($CreateNewPackages -or [string]::IsNullOrWhiteSpace($ExportPackage)) {
        $newExportScript = Join-Path $scriptDir "new_export_package.ps1"
        $ExportPackage = (& $newExportScript `
            -ProjectName $ProjectName `
            -ProjectPath $ProjectPath `
            -OutputRoot $ExportRoot `
            -PetrelVersion $PetrelVersion `
            -InventoryPackage $InventoryPackage) -replace '^Created export package:\s*', ''
    }
}

$InventoryPackage = (Resolve-Path -LiteralPath $InventoryPackage).Path
$ExportPackage = (Resolve-Path -LiteralPath $ExportPackage).Path

$manifestDir = Join-Path $ExportPackage "00_manifest"
$runDir = Join-Path $ExportPackage "07_workflows_reports\automation_runs"
New-Item -ItemType Directory -Force -Path $runDir | Out-Null

$standardStringParameters = @(
    "export_package=$ExportPackage",
    "inventory_package=$InventoryPackage",
    "export_manifest=$(Join-Path $ExportPackage '00_manifest\export_manifest.csv')"
)

if ([string]::IsNullOrWhiteSpace($StringParameters)) {
    $StringParameters = $standardStringParameters -join ","
} else {
    $StringParameters = (($standardStringParameters + $StringParameters) -join ",")
}

$petrelArgs = [System.Collections.Generic.List[string]]::new()

if ($Mode -eq "RunWorkflow") {
    Add-PetrelOption -Arguments $petrelArgs -Name "exit" -Style $PetrelOptionStyle
    Add-PetrelOption -Arguments $petrelArgs -Name "quiet" -Style $PetrelOptionStyle
    Add-PetrelOption -Arguments $petrelArgs -Name "nosplashscreen" -Style $PetrelOptionStyle
    Add-PetrelOption -Arguments $petrelArgs -Name "nodialogs" -Style $PetrelOptionStyle
    Add-PetrelOption -Arguments $petrelArgs -Name "runWorkflow" -Value $WorkflowName -Style $PetrelOptionStyle
} elseif ($Mode -eq "ExecMethod") {
    Add-PetrelOption -Arguments $petrelArgs -Name "exit" -Style $PetrelOptionStyle
    Add-PetrelOption -Arguments $petrelArgs -Name "quiet" -Style $PetrelOptionStyle
    Add-PetrelOption -Arguments $petrelArgs -Name "nosplashscreen" -Style $PetrelOptionStyle
    Add-PetrelOption -Arguments $petrelArgs -Name "nodialogs" -Style $PetrelOptionStyle
    $petrelExecAssembly = $ExecAssembly
    if ([System.IO.Path]::IsPathRooted($petrelExecAssembly) -and (Test-Path -LiteralPath $petrelExecAssembly -PathType Leaf)) {
        $petrelExecAssembly = [System.IO.Path]::GetFileNameWithoutExtension($petrelExecAssembly)
    }
    if ($petrelExecAssembly.EndsWith(".dll", [System.StringComparison]::OrdinalIgnoreCase)) {
        $petrelExecAssembly = $petrelExecAssembly.Substring(0, $petrelExecAssembly.Length - 4)
    }
    Add-PetrelOption -Arguments $petrelArgs -Name "exec" -Value $petrelExecAssembly -Style $PetrelOptionStyle
    $petrelArgs.Add($ExecMethod)
} elseif ($Mode -eq "OpenProject") {
    if (-not $OpenProjectWritable) {
        Add-PetrelOption -Arguments $petrelArgs -Name "readonly" -Style $PetrelOptionStyle
    }
}

if ($Mode -in @("OpenProject", "RunWorkflow", "ExecMethod")) {
    if (-not [string]::IsNullOrWhiteSpace($LicensePackage)) {
        Add-PetrelOption -Arguments $petrelArgs -Name "licensePackage" -Value $LicensePackage -Style $PetrelOptionStyle
    }
}

if ($Mode -in @("RunWorkflow", "ExecMethod")) {
    if (-not [string]::IsNullOrWhiteSpace($StringParameters)) {
        Add-PetrelOption -Arguments $petrelArgs -Name "sparm" -Value $StringParameters -Style $PetrelOptionStyle
    }
    if (-not [string]::IsNullOrWhiteSpace($NumericParameters)) {
        Add-PetrelOption -Arguments $petrelArgs -Name "nparm" -Value $NumericParameters -Style $PetrelOptionStyle
    }
}

if ($Mode -ne "Prepare" -and $Mode -ne "ValidateOnly") {
    $petrelArgs.Add($ProjectFile)
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$commandLine = (Quote-CmdArgument $PetrelExe) + " " + (($petrelArgs | ForEach-Object { Quote-CmdArgument $_ }) -join " ")
$commandPath = Join-Path $manifestDir "petrel_command_line.txt"
$cmdPath = Join-Path $manifestDir "run_petrel_export_pilot.cmd"
$runLogPath = Join-Path $runDir "petrel_automation_$stamp.log"
$statusPath = Join-Path $runDir "petrel_automation_$stamp.json"
$launchWorkingDirectory = Split-Path -Parent $PetrelExe
if ($Mode -eq "ExecMethod" -and [System.IO.Path]::IsPathRooted($ExecAssembly) -and (Test-Path -LiteralPath $ExecAssembly -PathType Leaf)) {
    $launchWorkingDirectory = Split-Path -Parent (Resolve-Path -LiteralPath $ExecAssembly).Path
}

if ($Mode -eq "Prepare" -or $Mode -eq "ValidateOnly") {
    @(
        "No Petrel command was generated because mode is $Mode.",
        "Use -Mode RunWorkflow -WorkflowName <name> or -Mode ExecMethod -ExecAssembly <dll> -ExecMethod <method> when the Petrel-side driver exists."
    ) | Set-Content -LiteralPath $commandPath -Encoding UTF8

    @(
        "@echo off",
        "echo No Petrel command was generated because mode is $Mode.",
        "echo Use invoke_petrel_export_pilot.ps1 with -Mode RunWorkflow or -Mode ExecMethod."
    ) | Set-Content -LiteralPath $cmdPath -Encoding ASCII
} else {
    $commandLine | Set-Content -LiteralPath $commandPath -Encoding UTF8
    $cmdLines = @(
        "@echo off",
        "cd /d $(Quote-CmdArgument $launchWorkingDirectory)"
    )
    if ($Mode -in @("RunWorkflow", "ExecMethod")) {
        $cmdLines += @(
            "set `"PETREL_EXPORT_PACKAGE=$(Escape-CmdSetValue $ExportPackage)`"",
            "set `"PETREL_INVENTORY_PACKAGE=$(Escape-CmdSetValue $InventoryPackage)`"",
            "set `"PETREL_EXPORT_MANIFEST=$(Escape-CmdSetValue (Join-Path $ExportPackage '00_manifest\export_manifest.csv'))`""
        )
    }
    $cmdLines += "$commandLine > $(Quote-CmdArgument $runLogPath) 2>&1"
    $cmdLines | Set-Content -LiteralPath $cmdPath -Encoding ASCII
}

$processExitCode = $null
$launched = $false

if ($Mode -in @("OpenProject", "RunWorkflow", "ExecMethod") -and -not $DryRun) {
    $launched = $true
    # Petrel 2018 can write to stdout during shutdown. Running through
    # the generated command file keeps stdout/stderr redirected like the local
    # HelpCenter command-line examples recommend.
    $process = Start-Process -FilePath "cmd.exe" -ArgumentList @("/c", $cmdPath) -PassThru -Wait:$Wait
    if ($Wait) {
        $processExitCode = $process.ExitCode
    }
}

$petrelRunFailed = $false
if ($Mode -in @("RunWorkflow", "ExecMethod") -and $Wait -and $null -ne $processExitCode -and $processExitCode -ne 0) {
    $petrelRunFailed = $true
}

$workflowExecutionStatus = "not_applicable"
if ($Mode -eq "RunWorkflow" -and $Wait -and -not $DryRun) {
    if (Test-Path -LiteralPath $runLogPath -PathType Leaf) {
        $runLogText = Get-Content -LiteralPath $runLogPath -Raw
        if ($runLogText -match "Status:\s*Workflow run OK") {
            $workflowExecutionStatus = "confirmed"
        } elseif ($runLogText -match "Running workflow") {
            $workflowExecutionStatus = "started_without_ok"
        } else {
            $workflowExecutionStatus = "not_detected"
        }
    } else {
        $workflowExecutionStatus = "log_missing"
    }

    if ($workflowExecutionStatus -ne "confirmed") {
        $petrelRunFailed = $true
    }
}

$artifactRegistrationStatus = "skipped"
if ($Mode -eq "RunWorkflow" -and $petrelRunFailed) {
    $artifactRegistrationStatus = "skipped_petrel_workflow_$workflowExecutionStatus"
} elseif ($Mode -in @("RunWorkflow", "ValidateOnly")) {
    $artifactRegistrar = Join-Path $scriptDir "register_petrel_workflow_artifacts.ps1"
    if (Test-Path -LiteralPath $artifactRegistrar -PathType Leaf) {
        $artifactWorkflowName = $WorkflowName
        if ([string]::IsNullOrWhiteSpace($artifactWorkflowName)) {
            $artifactWorkflowName = "ExportPiloX"
        }
        $artifactRegistrationOutput = & $artifactRegistrar `
            -ExportPackage $ExportPackage `
            -WorkflowName $artifactWorkflowName `
            -ProjectName $ProjectName `
            -PetrelVersion $PetrelVersion `
            -InventoryPackage $InventoryPackage
        $artifactRegistrationStatus = (($artifactRegistrationOutput | Select-Object -First 1) -replace '^Artifact registration:\s*', '')
    }
}

$fileExportRegistrationStatus = "skipped"
if ($Mode -in @("RunWorkflow", "ExecMethod") -and $petrelRunFailed) {
    $fileExportRegistrationStatus = "skipped_petrel_workflow_$workflowExecutionStatus"
} elseif ($Mode -in @("Prepare", "RunWorkflow", "ExecMethod", "ValidateOnly")) {
    $fileExportRegistrar = Join-Path $scriptDir "register_petrel_file_exports.ps1"
    if (Test-Path -LiteralPath $fileExportRegistrar -PathType Leaf) {
        $fileExportRegistrationOutput = & $fileExportRegistrar `
            -ExportPackage $ExportPackage `
            -ProjectName $ProjectName `
            -PetrelVersion $PetrelVersion `
            -InventoryPackage $InventoryPackage
        $fileExportRegistrationStatus = (($fileExportRegistrationOutput | Select-Object -First 1) -replace '^File export registration:\s*', '')
    }
}

$validationStatus = "skipped"
if ($petrelRunFailed) {
    $validationStatus = "skipped_petrel_workflow_$workflowExecutionStatus"
} elseif ($Mode -in @("Prepare", "RunWorkflow", "ExecMethod", "ValidateOnly") -and -not $NoValidate) {
    $validator = Join-Path $scriptDir "validate_export_package.ps1"
    $validationOutput = & $validator -ExportPackage $ExportPackage -UpdateManifest -WriteChecksums
    $validationStatus = (($validationOutput | Select-Object -First 1) -replace '^Validation status:\s*', '')
}

$status = [ordered]@{
    run_id = "petrel_automation_$stamp"
    created_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    mode = $Mode
    petrel_exe = $PetrelExe
    project_file = $ProjectFile
    inventory_package = $InventoryPackage
    export_package = $ExportPackage
    workflow_name = $WorkflowName
    exec_assembly = $ExecAssembly
    exec_method = $ExecMethod
    license_package = $LicensePackage
    petrel_option_style = $PetrelOptionStyle
    command_line_path = $commandPath
    cmd_path = $cmdPath
    run_log_path = $runLogPath
    launched = $launched
    dry_run = [bool]$DryRun
    waited = [bool]$Wait
    open_project_writable = [bool]$OpenProjectWritable
    process_exit_code = $processExitCode
    workflow_execution_status = $workflowExecutionStatus
    artifact_registration_status = $artifactRegistrationStatus
    file_export_registration_status = $fileExportRegistrationStatus
    validation_status = $validationStatus
}

$status | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $statusPath -Encoding UTF8

Write-Output "Mode: $Mode"
Write-Output "Petrel: $PetrelExe"
Write-Output "Inventory package: $InventoryPackage"
Write-Output "Export package: $ExportPackage"
Write-Output "Command file: $cmdPath"
Write-Output "Status file: $statusPath"
if ($Wait -and $null -ne $processExitCode) {
    Write-Output "Petrel exit: $processExitCode"
}
Write-Output "Workflow execution: $workflowExecutionStatus"
Write-Output "Artifact registration: $artifactRegistrationStatus"
Write-Output "File export registration: $fileExportRegistrationStatus"
Write-Output "Validation: $validationStatus"

if ($petrelRunFailed) {
    if ($null -ne $processExitCode -and $processExitCode -ne 0) {
        exit $processExitCode
    }
    exit 3
}
