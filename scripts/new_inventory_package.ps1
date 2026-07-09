param(
    [Parameter(Mandatory=$true)]
    [string]$ProjectName,

    [string]$ProjectPath = "",

    [Parameter(Mandatory=$true)]
    [string]$OutputRoot,

    [string]$PetrelVersion = "unknown",
    [string]$Scope = "pilot_inventory",
    [string]$Operator = ""
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
$templateDir = Join-Path $repoRoot "build\templates"

if (-not (Test-Path -Path $templateDir)) {
    throw "Template directory not found: $templateDir"
}

$safeName = ($ProjectName -replace '[^A-Za-z0-9._-]+', '_').Trim('_')
if ([string]::IsNullOrWhiteSpace($safeName)) {
    throw "ProjectName does not contain any safe filename characters."
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$packageRoot = Join-Path $OutputRoot ($safeName + "_inventory_" + $stamp)

$dirs = @(
    "00_manifest",
    "01_project_metadata",
    "02_wells",
    "03_seismic",
    "04_surfaces_maps",
    "05_interpretation",
    "06_models_properties",
    "07_workflows_reports",
    "99_unexported_or_manual"
)

foreach ($dir in $dirs) {
    New-Item -ItemType Directory -Force -Path (Join-Path $packageRoot $dir) | Out-Null
}

Copy-Item -Path (Join-Path $templateDir "petrel_project_inventory.csv") -Destination (Join-Path $packageRoot "00_manifest\object_inventory.csv") -Force
Copy-Item -Path (Join-Path $templateDir "petrel_export_capability_map.csv") -Destination (Join-Path $packageRoot "00_manifest\export_capability_map.csv") -Force
Copy-Item -Path (Join-Path $templateDir "manual_capture_required.csv") -Destination (Join-Path $packageRoot "99_unexported_or_manual\manual_capture_required.csv") -Force
Copy-Item -Path (Join-Path $templateDir "inventory_capture_checklist.md") -Destination (Join-Path $packageRoot "00_manifest\inventory_capture_checklist.md") -Force

$nowUtc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
$summary = [ordered]@{
    name = $ProjectName
    petrel_version = $PetrelVersion
    project_path = $ProjectPath
    coordinate_reference_system = "unknown"
    units = [ordered]@{
        xy = "unknown"
        z = "unknown"
        time = "unknown"
        velocity = "unknown"
    }
    inventory = [ordered]@{
        inventory_id = $safeName + "_" + $stamp
        inventory_date_utc = $nowUtc
        scope = $Scope
        capture_method = "manual"
        operator = $Operator
    }
}

($summary | ConvertTo-Json -Depth 8) | Set-Content -Path (Join-Path $packageRoot "01_project_metadata\project_summary.json") -Encoding UTF8

if (-not [string]::IsNullOrWhiteSpace($ProjectPath)) {
    if (-not (Test-Path -Path $ProjectPath)) {
        throw "ProjectPath was provided but does not exist: $ProjectPath"
    }

    $resolvedProjectPath = (Resolve-Path -Path $ProjectPath).Path.TrimEnd('\')
    $storageRows = @()
    $files = Get-ChildItem -Path $resolvedProjectPath -Recurse -File -ErrorAction SilentlyContinue
    foreach ($file in $files) {
        $relativePath = $file.FullName.Substring($resolvedProjectPath.Length).TrimStart('\')
        $storageRows += [pscustomobject]@{
            relative_path = $relativePath
            extension = $file.Extension
            length_bytes = $file.Length
            last_write_time_utc = $file.LastWriteTimeUtc.ToString("yyyy-MM-ddTHH:mm:ssZ")
        }
    }

    $storageRows |
        Sort-Object relative_path |
        Export-Csv -Path (Join-Path $packageRoot "00_manifest\project_storage_file_inventory.csv") -NoTypeInformation -Encoding UTF8

    $storageRows |
        Group-Object extension |
        Sort-Object Count -Descending |
        Select-Object @{Name="extension";Expression={$_.Name}}, Count |
        Export-Csv -Path (Join-Path $packageRoot "00_manifest\project_storage_extension_summary.csv") -NoTypeInformation -Encoding UTF8
}

$log = @"
# Inventory Log

- Project: $ProjectName
- Petrel version: $PetrelVersion
- Scope: $Scope
- Project path: $ProjectPath
- Created UTC: $nowUtc
- Operator: $Operator

## Notes

- Fill 00_manifest/object_inventory.csv first.
- Add unsupported or unclear objects to 99_unexported_or_manual/manual_capture_required.csv.
- Use this inventory to drive the universal export workflow.
"@

$log | Set-Content -Path (Join-Path $packageRoot "00_manifest\inventory_log.md") -Encoding UTF8

Write-Output $packageRoot
