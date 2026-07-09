param(
    [string]$ProjectDirectory = "D:\Computer\Code\Petrel_project\Petrel_DemoData_project",

    [string]$ProjectStem = "Petrel2010 demo project ExportPilot",

    [string[]]$Terms = @(
        "ExportPiloX",
        "ExportPilot",
        "export_package",
        "inventory",
        "manifest",
        "cli_variable",
        "Commands",
        "SheetSaveCmd",
        "BXML"
    ),

    [string]$OutputRoot = "D:\Computer\Code\Petrel_project\build\native_edit_experiments"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Find-TextOffsets {
    param(
        [string]$Text,
        [string]$Term,
        [System.StringComparison]$Comparison = [System.StringComparison]::Ordinal
    )

    $offsets = New-Object System.Collections.Generic.List[int]
    $index = $Text.IndexOf($Term, $Comparison)
    while ($index -ge 0) {
        $offsets.Add($index)
        $index = $Text.IndexOf($Term, $index + 1, $Comparison)
    }
    return $offsets
}

function Get-PrintableContext {
    param(
        [byte[]]$Bytes,
        [int]$Offset,
        [int]$Before = 220,
        [int]$After = 520
    )

    $start = [Math]::Max(0, $Offset - $Before)
    $length = [Math]::Min($Before + $After, $Bytes.Length - $start)
    $slice = $Bytes[$start..($start + $length - 1)]
    return (($slice | ForEach-Object {
        if ($_ -ge 32 -and $_ -le 126) {
            [char]$_
        } else {
            "."
        }
    }) -join "")
}

$projectPath = (Resolve-Path -LiteralPath $ProjectDirectory).Path
$ptdDirectory = Join-Path $projectPath "$ProjectStem.ptd"
if (-not (Test-Path -LiteralPath $ptdDirectory -PathType Container)) {
    throw "PTD directory not found: $ptdDirectory"
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$reportDir = Join-Path $OutputRoot "native_workflow_payload_inspection_$stamp"
New-Item -ItemType Directory -Force -Path $reportDir | Out-Null

$encoding = [System.Text.Encoding]::GetEncoding(28591)
$storeFiles = @(
    (Join-Path $ptdDirectory "Model.ptd"),
    (Join-Path $ptdDirectory "Data.ptd")
)

$hits = @()
foreach ($storeFile in $storeFiles) {
    if (-not (Test-Path -LiteralPath $storeFile -PathType Leaf)) {
        continue
    }

    $bytes = [System.IO.File]::ReadAllBytes($storeFile)
    $text = $encoding.GetString($bytes)
    foreach ($term in $Terms) {
        $offsets = @(Find-TextOffsets -Text $text -Term $term)
        foreach ($offset in $offsets) {
            $hits += [pscustomobject]@{
                store_file = $storeFile
                store_name = [System.IO.Path]::GetFileName($storeFile)
                term = $term
                offset = $offset
                context = Get-PrintableContext -Bytes $bytes -Offset $offset
            }
        }
    }
}

$csvPath = Join-Path $reportDir "native_workflow_payload_hits.csv"
$jsonPath = Join-Path $reportDir "native_workflow_payload_hits.json"
$mdPath = Join-Path $reportDir "native_workflow_payload_summary.md"

$hits | Export-Csv -LiteralPath $csvPath -NoTypeInformation -Encoding UTF8
$hits | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $jsonPath -Encoding UTF8

$summaryRows = $hits |
    Group-Object store_name, term |
    ForEach-Object {
        $parts = $_.Name -split ", "
        [pscustomobject]@{
            store_name = $parts[0]
            term = $parts[1]
            count = $_.Count
            first_offsets = (($_.Group | Select-Object -First 8 -ExpandProperty offset) -join ",")
        }
    } |
    Sort-Object store_name, term

$md = @(
    "# Native Workflow Payload Inspection",
    "",
    "- Created UTC: $((Get-Date).ToUniversalTime().ToString("o"))",
    "- Project: $ProjectStem",
    "- PTD directory: $ptdDirectory",
    "",
    "## Summary",
    "",
    "| Store | Term | Count | First offsets |",
    "| --- | --- | ---: | --- |"
)

foreach ($row in $summaryRows) {
    $md += "| $($row.store_name) | $($row.term) | $($row.count) | $($row.first_offsets) |"
}

$md += @(
    "",
    "## Notable Payload Region",
    "",
    "The Data.ptd SheetSaveCmd payload for the CLI variable probe currently contains export_package near offset 173166025 and the output filename path fragments near the same region.",
    "",
    "Full contexts are in:",
    "",
    "- $csvPath",
    "- $jsonPath"
)

$md | Set-Content -LiteralPath $mdPath -Encoding UTF8

Write-Output "Native workflow payload inspection complete"
Write-Output "CSV: $csvPath"
Write-Output "JSON: $jsonPath"
Write-Output "Summary: $mdPath"
