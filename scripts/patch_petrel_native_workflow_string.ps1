param(
    [string]$ProjectDirectory = "D:\Computer\Code\Petrel_project\Petrel_DemoData_project",

    [string]$ProjectStem = "Petrel2010 demo project ExportPilot",

    [string]$RelativeStoreFile = "Model.ptd",

    [string]$Search = "ExportPilot",

    [string]$Replace = "ExportPiloX",

    [string]$BackupRoot = "D:\Computer\Code\Petrel_project\build\native_edit_experiments",

    [switch]$AllowMultiple,

    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-AsciiBytes {
    param([string]$Value)
    return [System.Text.Encoding]::ASCII.GetBytes($Value)
}

function Find-BytePattern {
    param(
        [byte[]]$Bytes,
        [byte[]]$Pattern
    )

    $hits = New-Object System.Collections.Generic.List[int]
    for ($i = 0; $i -le $Bytes.Length - $Pattern.Length; $i++) {
        $matched = $true
        for ($j = 0; $j -lt $Pattern.Length; $j++) {
            if ($Bytes[$i + $j] -ne $Pattern[$j]) {
                $matched = $false
                break
            }
        }
        if ($matched) {
            $hits.Add($i)
        }
    }
    return $hits
}

function Find-AsciiPatternFast {
    param(
        [byte[]]$Bytes,
        [string]$Pattern
    )

    $encoding = [System.Text.Encoding]::GetEncoding(28591)
    $text = $encoding.GetString($Bytes)
    $hits = New-Object System.Collections.Generic.List[int]
    $index = $text.IndexOf($Pattern, [System.StringComparison]::Ordinal)
    while ($index -ge 0) {
        $hits.Add($index)
        $index = $text.IndexOf($Pattern, $index + 1, [System.StringComparison]::Ordinal)
    }
    return $hits
}

$projectPath = Resolve-Path -LiteralPath $ProjectDirectory
$ptdDirectory = Join-Path $projectPath.Path "$ProjectStem.ptd"
$targetPath = Join-Path $ptdDirectory $RelativeStoreFile
$petPath = Join-Path $projectPath.Path "$ProjectStem.pet"

if (-not (Test-Path -LiteralPath $targetPath -PathType Leaf)) {
    throw "Target store file not found: $targetPath"
}

$searchBytes = Get-AsciiBytes $Search
$replaceBytes = Get-AsciiBytes $Replace

if ($searchBytes.Length -ne $replaceBytes.Length) {
    throw "Search and replacement must be the same byte length. '$Search'=$($searchBytes.Length), '$Replace'=$($replaceBytes.Length)."
}

$bytes = [System.IO.File]::ReadAllBytes($targetPath)
if ($bytes.Length -gt 10MB) {
    $hits = @(Find-AsciiPatternFast -Bytes $bytes -Pattern $Search)
} else {
    $hits = @(Find-BytePattern -Bytes $bytes -Pattern $searchBytes)
}

if ($hits.Count -eq 0) {
    throw "Search string was not found in $targetPath"
}
if ($hits.Count -gt 1 -and -not $AllowMultiple) {
    throw "Search string was found $($hits.Count) times. Use -AllowMultiple only if every occurrence should be patched."
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupDir = Join-Path $BackupRoot "native_workflow_string_patch_$stamp"
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null

$targetBackup = Join-Path $backupDir ([System.IO.Path]::GetFileName($targetPath))
Copy-Item -LiteralPath $targetPath -Destination $targetBackup -Force
if (Test-Path -LiteralPath $petPath -PathType Leaf) {
    Copy-Item -LiteralPath $petPath -Destination (Join-Path $backupDir ([System.IO.Path]::GetFileName($petPath))) -Force
}

$beforeHash = (Get-FileHash -LiteralPath $targetPath -Algorithm SHA256).Hash.ToLowerInvariant()

if (-not $DryRun) {
    foreach ($hit in $hits) {
        [Array]::Copy($replaceBytes, 0, $bytes, $hit, $replaceBytes.Length)
    }
    [System.IO.File]::WriteAllBytes($targetPath, $bytes)
}

$afterHash = (Get-FileHash -LiteralPath $targetPath -Algorithm SHA256).Hash.ToLowerInvariant()
$reportPath = Join-Path $backupDir "native_workflow_string_patch_report.json"
$report = [ordered]@{
    created_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    project_directory = $projectPath.Path
    project_stem = $ProjectStem
    target_path = $targetPath
    target_backup = $targetBackup
    search = $Search
    replace = $Replace
    byte_length = $searchBytes.Length
    hit_count = $hits.Count
    offsets = $hits
    dry_run = [bool]$DryRun
    before_sha256 = $beforeHash
    after_sha256 = $afterHash
}
$report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $reportPath -Encoding UTF8

Write-Output "Native workflow string patch: $(if ($DryRun) { 'dry_run' } else { 'patched' })"
Write-Output "Target: $targetPath"
Write-Output "Search: $Search"
Write-Output "Replace: $Replace"
Write-Output "Hits: $($hits.Count)"
Write-Output "Offsets: $($hits -join ',')"
Write-Output "Backup: $backupDir"
Write-Output "Report: $reportPath"
