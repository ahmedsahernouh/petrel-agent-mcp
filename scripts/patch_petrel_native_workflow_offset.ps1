param(
    [string]$ProjectDirectory = "D:\Computer\Code\Petrel_project\Petrel_DemoData_project",

    [string]$ProjectStem = "Petrel2010 demo project ExportPilot",

    [string]$RelativeStoreFile = "Data.ptd",

    [Parameter(Mandatory = $true)]
    [long]$Offset,

    [Parameter(Mandatory = $true)]
    [string]$Expected,

    [Parameter(Mandatory = $true)]
    [string]$Replace,

    [string]$BackupRoot = "D:\Computer\Code\Petrel_project\build\native_edit_experiments",

    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-AsciiBytes {
    param([string]$Value)
    return [System.Text.Encoding]::ASCII.GetBytes($Value)
}

$projectPath = Resolve-Path -LiteralPath $ProjectDirectory
$ptdDirectory = Join-Path $projectPath.Path "$ProjectStem.ptd"
$targetPath = Join-Path $ptdDirectory $RelativeStoreFile
$petPath = Join-Path $projectPath.Path "$ProjectStem.pet"

if (-not (Test-Path -LiteralPath $targetPath -PathType Leaf)) {
    throw "Target store file not found: $targetPath"
}

$expectedBytes = Get-AsciiBytes $Expected
$replaceBytes = Get-AsciiBytes $Replace

if ($expectedBytes.Length -ne $replaceBytes.Length) {
    throw "Expected and replacement strings must be the same byte length. '$Expected'=$($expectedBytes.Length), '$Replace'=$($replaceBytes.Length)."
}

$bytes = [System.IO.File]::ReadAllBytes($targetPath)
if ($Offset -lt 0 -or ($Offset + $expectedBytes.Length) -gt $bytes.LongLength) {
    throw "Offset $Offset with length $($expectedBytes.Length) is outside $targetPath length $($bytes.LongLength)."
}

$actualBytes = New-Object byte[] $expectedBytes.Length
[Array]::Copy($bytes, $Offset, $actualBytes, 0, $expectedBytes.Length)
$actual = [System.Text.Encoding]::ASCII.GetString($actualBytes)

if ($actual -ne $Expected) {
    throw "Expected '$Expected' at offset $Offset, but found '$actual'. No patch was written."
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupDir = Join-Path $BackupRoot "native_workflow_offset_patch_$stamp"
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null

$targetBackup = Join-Path $backupDir ([System.IO.Path]::GetFileName($targetPath))
Copy-Item -LiteralPath $targetPath -Destination $targetBackup -Force
if (Test-Path -LiteralPath $petPath -PathType Leaf) {
    Copy-Item -LiteralPath $petPath -Destination (Join-Path $backupDir ([System.IO.Path]::GetFileName($petPath))) -Force
}

$beforeHash = (Get-FileHash -LiteralPath $targetPath -Algorithm SHA256).Hash.ToLowerInvariant()

if (-not $DryRun) {
    [Array]::Copy($replaceBytes, 0, $bytes, $Offset, $replaceBytes.Length)
    [System.IO.File]::WriteAllBytes($targetPath, $bytes)
}

$afterHash = (Get-FileHash -LiteralPath $targetPath -Algorithm SHA256).Hash.ToLowerInvariant()
$reportPath = Join-Path $backupDir "native_workflow_offset_patch_report.json"
$report = [ordered]@{
    created_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    project_directory = $projectPath.Path
    project_stem = $ProjectStem
    target_path = $targetPath
    target_backup = $targetBackup
    offset = $Offset
    expected = $Expected
    replace = $Replace
    byte_length = $expectedBytes.Length
    dry_run = [bool]$DryRun
    before_sha256 = $beforeHash
    after_sha256 = $afterHash
}
$report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $reportPath -Encoding UTF8

Write-Output "Native workflow offset patch: $(if ($DryRun) { 'dry_run' } else { 'patched' })"
Write-Output "Target: $targetPath"
Write-Output "Offset: $Offset"
Write-Output "Expected: $Expected"
Write-Output "Replace: $Replace"
Write-Output "Backup: $backupDir"
Write-Output "Report: $reportPath"
