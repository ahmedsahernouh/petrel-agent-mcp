param(
    [string]$RepoRoot = "",
    [string]$PythonPath = "",
    [string]$TesseractPath = "",
    [switch]$SkipSmoke,
    [switch]$JsonOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = Split-Path -Parent $scriptDir
}
$RepoRoot = (Resolve-Path -LiteralPath $RepoRoot).Path
. (Join-Path $scriptDir "petrel_mcp_dependencies.ps1")

function Add-DoctorCheck {
    param(
        [System.Collections.Generic.List[object]]$Checks,
        [string]$Name,
        [string]$Status,
        [object]$Detail = $null
    )
    $Checks.Add([ordered]@{
        name = $Name
        status = $Status
        detail = $Detail
    }) | Out-Null
}

function Invoke-DoctorCommand {
    param(
        [string]$FilePath,
        [string[]]$Arguments,
        [int]$TimeoutSeconds = 120
    )

    $stdoutPath = [IO.Path]::GetTempFileName()
    $stderrPath = [IO.Path]::GetTempFileName()
    $process = Start-Process `
        -FilePath $FilePath `
        -ArgumentList $Arguments `
        -WorkingDirectory $RepoRoot `
        -NoNewWindow `
        -PassThru `
        -RedirectStandardOutput $stdoutPath `
        -RedirectStandardError $stderrPath
    try {
        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
            try { $process.Kill() } catch { }
            return [ordered]@{
                exit_code = 124
                stdout = ""
                stderr = "Timed out after $TimeoutSeconds seconds."
            }
        }
        $stdout = Get-Content -LiteralPath $stdoutPath -Raw -ErrorAction SilentlyContinue
        $stderr = Get-Content -LiteralPath $stderrPath -Raw -ErrorAction SilentlyContinue
        return [ordered]@{
            exit_code = [int]$process.ExitCode
            stdout = if ($null -eq $stdout) { "" } else { $stdout.Trim() }
            stderr = if ($null -eq $stderr) { "" } else { $stderr.Trim() }
        }
    } finally {
        Remove-Item -LiteralPath $stdoutPath -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $stderrPath -Force -ErrorAction SilentlyContinue
    }
}

$checks = New-Object System.Collections.Generic.List[object]
$warnings = New-Object System.Collections.Generic.List[string]
$failures = New-Object System.Collections.Generic.List[string]
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$serverPath = Join-Path $RepoRoot "mcp\petrel_mcp_server.py"
$serverSmokePath = Join-Path $RepoRoot "scripts\test_petrel_mcp_server.py"
$clientSmokePath = Join-Path $RepoRoot "scripts\test_petrel_mcp_client_configs.py"

$python = ""
try {
    $python = Resolve-PetrelMcpPython -ExplicitPath $PythonPath -ProjectRoot $RepoRoot
    Add-DoctorCheck -Checks $checks -Name "python" -Status "passed" -Detail $python
} catch {
    $failures.Add($_.Exception.Message) | Out-Null
    Add-DoctorCheck -Checks $checks -Name "python" -Status "failed" -Detail $_.Exception.Message
}

try {
    $tesseract = Resolve-PetrelMcpTesseract -ExplicitPath $TesseractPath
    Add-DoctorCheck -Checks $checks -Name "tesseract" -Status "passed" -Detail $tesseract
} catch {
    $warnings.Add($_.Exception.Message) | Out-Null
    Add-DoctorCheck -Checks $checks -Name "tesseract" -Status "warning" -Detail $_.Exception.Message
}

foreach ($pathCheck in @(
    @{ Name = "repo_root"; Path = $RepoRoot; Type = "Container" },
    @{ Name = "mcp_server"; Path = $serverPath; Type = "Leaf" },
    @{ Name = "server_smoke_test"; Path = $serverSmokePath; Type = "Leaf" },
    @{ Name = "client_config_smoke_test"; Path = $clientSmokePath; Type = "Leaf" }
)) {
    $exists = Test-Path -LiteralPath $pathCheck.Path -PathType $pathCheck.Type
    if ($exists) {
        Add-DoctorCheck -Checks $checks -Name $pathCheck.Name -Status "passed" -Detail $pathCheck.Path
    } else {
        $message = "$($pathCheck.Name) missing: $($pathCheck.Path)"
        $failures.Add($message) | Out-Null
        Add-DoctorCheck -Checks $checks -Name $pathCheck.Name -Status "failed" -Detail $message
    }
}

$claudeStoreCandidates = @()
$claudePackageRoot = Join-Path $env:LOCALAPPDATA "Packages"
if (Test-Path -LiteralPath $claudePackageRoot -PathType Container) {
    $claudeStoreCandidates = @(Get-ChildItem -LiteralPath $claudePackageRoot -Directory -Filter "Claude_*" -ErrorAction SilentlyContinue |
        ForEach-Object { Join-Path $_.FullName "LocalCache\Roaming\Claude\claude_desktop_config.json" })
}

$configCandidates = @(
    [ordered]@{ client = "codex"; path = Join-Path $env:USERPROFILE ".codex\config.toml" },
    [ordered]@{ client = "vscode"; path = Join-Path $env:APPDATA "Code\User\mcp.json" },
    [ordered]@{ client = "opencode"; path = Join-Path $env:USERPROFILE ".config\opencode\opencode.jsonc" },
    [ordered]@{ client = "claude_roaming"; path = Join-Path $env:APPDATA "Claude\claude_desktop_config.json" }
)
foreach ($candidate in $claudeStoreCandidates) {
    $configCandidates += [ordered]@{ client = "claude_store"; path = $candidate }
}

$configStatus = @()
foreach ($candidate in $configCandidates) {
    $exists = Test-Path -LiteralPath $candidate.path -PathType Leaf
    $containsServer = $false
    if ($exists) {
        $containsServer = (Select-String -LiteralPath $candidate.path -Pattern "petrel-no-ocean-control" -Quiet)
    }
    $status = if ($exists -and $containsServer) { "passed" } elseif ($exists) { "missing_server" } else { "missing_config" }
    if ($status -ne "passed") {
        $warnings.Add("$($candidate.client): $status at $($candidate.path)") | Out-Null
    }
    $configStatus += [ordered]@{
        client = $candidate.client
        path = $candidate.path
        exists = $exists
        contains_petrel_server = $containsServer
        status = $status
    }
}
Add-DoctorCheck -Checks $checks -Name "client_config_files" -Status "inspected" -Detail $configStatus

$serverSmoke = $null
$clientSmoke = $null
if (-not $SkipSmoke -and -not [string]::IsNullOrWhiteSpace($python) -and (Test-Path -LiteralPath $serverSmokePath -PathType Leaf)) {
    $serverSmoke = Invoke-DoctorCommand -FilePath $python -Arguments @($serverSmokePath) -TimeoutSeconds 180
    if ([int]$serverSmoke.exit_code -eq 0) {
        Add-DoctorCheck -Checks $checks -Name "mcp_server_smoke" -Status "passed" -Detail $serverSmoke.stdout
    } else {
        $failures.Add("MCP server smoke failed with exit code $($serverSmoke.exit_code).") | Out-Null
        Add-DoctorCheck -Checks $checks -Name "mcp_server_smoke" -Status "failed" -Detail $serverSmoke
    }
}
if (-not $SkipSmoke -and -not [string]::IsNullOrWhiteSpace($python) -and (Test-Path -LiteralPath $clientSmokePath -PathType Leaf)) {
    $clientSmoke = Invoke-DoctorCommand -FilePath $python -Arguments @($clientSmokePath) -TimeoutSeconds 180
    if ([int]$clientSmoke.exit_code -eq 0) {
        Add-DoctorCheck -Checks $checks -Name "mcp_client_config_smoke" -Status "passed" -Detail $clientSmoke.stdout
    } else {
        $failures.Add("MCP client config smoke failed with exit code $($clientSmoke.exit_code).") | Out-Null
        Add-DoctorCheck -Checks $checks -Name "mcp_client_config_smoke" -Status "failed" -Detail $clientSmoke
    }
}

$status = if ($failures.Count -gt 0) {
    "failed"
} elseif ($warnings.Count -gt 0) {
    "ready_with_warnings"
} else {
    "ready"
}

$report = New-Object System.Collections.Specialized.OrderedDictionary
$report["created_at_utc"] = (Get-Date).ToUniversalTime().ToString("o")
$report["status"] = $status
$report["repo_root"] = $RepoRoot
$report["server"] = $serverPath
$report["python"] = $python
$report["checks"] = @($checks.ToArray())
$report["warnings"] = @($warnings.ToArray())
$report["failures"] = @($failures.ToArray())
$report["client_configs"] = @($configStatus)
$report["server_smoke"] = $serverSmoke
$report["client_smoke"] = $clientSmoke

$reportDir = Join-Path $RepoRoot "build\mcp_doctor"
New-Item -ItemType Directory -Force -Path $reportDir | Out-Null
$reportPath = Join-Path $reportDir "petrel_mcp_doctor_$stamp.json"
$report | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $reportPath -Encoding UTF8

if ($JsonOnly) {
    $report | ConvertTo-Json -Depth 10
} else {
    Write-Output "Petrel MCP doctor: $status"
    Write-Output "Report: $reportPath"
    if ($warnings.Count -gt 0) {
        Write-Output "Warnings:"
        foreach ($warning in $warnings) { Write-Output "- $warning" }
    }
    if ($failures.Count -gt 0) {
        Write-Output "Failures:"
        foreach ($failure in $failures) { Write-Output "- $failure" }
        exit 1
    }
}
