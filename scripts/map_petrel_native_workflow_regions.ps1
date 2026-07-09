param(
    [string]$ProjectDirectory = "D:\Computer\Code\Petrel_project\Petrel_DemoData_project",

    [string]$ProjectStem = "Petrel2010 demo project ExportPilot",

    [string]$RelativeStoreFile = "Data.ptd",

    [string[]]$Terms = @(
        "SheetSaveCmd",
        "SimpleCmd",
        "SystemCmd",
        "powershell.exe",
        "petrel_export_mvp_bridge.ps1",
        "export_package",
        "cli_variable",
        "Commands",
        "BXML",
        "LZ4"
    ),

    [string]$TermsCsv = "",

    [string]$CompareStoreFile = "",

    [string]$OutputRoot = "D:\Computer\Code\Petrel_project\build\native_edit_experiments"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not [string]::IsNullOrWhiteSpace($TermsCsv)) {
    $Terms = @($TermsCsv -split "\|" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
}

function Find-TextOffsets {
    param(
        [string]$Text,
        [string]$Term
    )

    $offsets = New-Object System.Collections.Generic.List[int]
    $index = $Text.IndexOf($Term, [System.StringComparison]::Ordinal)
    while ($index -ge 0) {
        $offsets.Add($index)
        $index = $Text.IndexOf($Term, $index + 1, [System.StringComparison]::Ordinal)
    }
    return $offsets
}

function Find-NearestBefore {
    param(
        [int[]]$Offsets,
        [int]$Offset
    )

    $candidate = $null
    foreach ($item in $Offsets) {
        if ($item -le $Offset) {
            $candidate = $item
        } else {
            break
        }
    }
    return $candidate
}

function Find-NearestAfter {
    param(
        [int[]]$Offsets,
        [int]$Offset
    )

    foreach ($item in $Offsets) {
        if ($item -gt $Offset) {
            return $item
        }
    }
    return $null
}

function Get-PrintableContext {
    param(
        [byte[]]$Bytes,
        [int]$Offset,
        [int]$Before = 260,
        [int]$After = 760
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

function Get-CommandTypeGuess {
    param([string]$Context)

    $matches = [regex]::Matches($Context, "[A-Za-z][A-Za-z0-9_]{2,}Cmd")
    if ($matches.Count -eq 0) {
        return ""
    }

    return (($matches | ForEach-Object { $_.Value } | Select-Object -Unique) -join ";")
}

function Get-DiffRanges {
    param(
        [byte[]]$Left,
        [byte[]]$Right
    )

    $ranges = New-Object System.Collections.Generic.List[object]
    $max = [Math]::Max($Left.Length, $Right.Length)
    $start = $null
    $last = $null

    for ($i = 0; $i -lt $max; $i++) {
        $leftByte = if ($i -lt $Left.Length) { $Left[$i] } else { $null }
        $rightByte = if ($i -lt $Right.Length) { $Right[$i] } else { $null }
        if ($leftByte -ne $rightByte) {
            if ($null -eq $start) {
                $start = $i
            }
            $last = $i
        } elseif ($null -ne $start) {
            $ranges.Add([pscustomobject]@{
                start_offset = $start
                end_offset = $last
                length = $last - $start + 1
            })
            $start = $null
            $last = $null
        }
    }

    if ($null -ne $start) {
        $ranges.Add([pscustomobject]@{
            start_offset = $start
            end_offset = $last
            length = $last - $start + 1
        })
    }

    return $ranges
}

$projectPath = (Resolve-Path -LiteralPath $ProjectDirectory).Path
$ptdDirectory = Join-Path $projectPath "$ProjectStem.ptd"
$storePath = Join-Path $ptdDirectory $RelativeStoreFile
if (-not (Test-Path -LiteralPath $storePath -PathType Leaf)) {
    throw "Store file not found: $storePath"
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$reportDir = Join-Path $OutputRoot "native_workflow_region_map_$stamp"
New-Item -ItemType Directory -Force -Path $reportDir | Out-Null

$bytes = [System.IO.File]::ReadAllBytes($storePath)
$encoding = [System.Text.Encoding]::GetEncoding(28591)
$text = $encoding.GetString($bytes)

$bxmlOffsets = @(Find-TextOffsets -Text $text -Term "BXML" | Sort-Object)
$lz4Offsets = @(Find-TextOffsets -Text $text -Term "LZ4" | Sort-Object)

$termRows = @()
foreach ($term in $Terms) {
    $offsets = @(Find-TextOffsets -Text $text -Term $term)
    foreach ($offset in $offsets) {
        $context = Get-PrintableContext -Bytes $bytes -Offset $offset
        $prevBxml = Find-NearestBefore -Offsets $bxmlOffsets -Offset $offset
        $nextBxml = Find-NearestAfter -Offsets $bxmlOffsets -Offset $offset
        $prevLz4 = Find-NearestBefore -Offsets $lz4Offsets -Offset $offset
        $nextLz4 = Find-NearestAfter -Offsets $lz4Offsets -Offset $offset
        $termRows += [pscustomobject]@{
            term = $term
            offset = $offset
            previous_lz4_offset = $prevLz4
            previous_bxml_offset = $prevBxml
            next_bxml_offset = $nextBxml
            next_lz4_offset = $nextLz4
            command_type_guess = Get-CommandTypeGuess -Context $context
            context = $context
        }
    }
}

$chunkRows = @()
for ($i = 0; $i -lt $bxmlOffsets.Count; $i++) {
    $offset = $bxmlOffsets[$i]
    $next = if ($i + 1 -lt $bxmlOffsets.Count) { $bxmlOffsets[$i + 1] } else { $bytes.Length }
    $prevLz4 = Find-NearestBefore -Offsets $lz4Offsets -Offset $offset
    $context = Get-PrintableContext -Bytes $bytes -Offset $offset -Before 80 -After 520
    $chunkRows += [pscustomobject]@{
        bxml_index = $i
        bxml_offset = $offset
        previous_lz4_offset = $prevLz4
        next_bxml_offset = $next
        approx_span_to_next_bxml = $next - $offset
        command_type_guess = Get-CommandTypeGuess -Context $context
        context = $context
    }
}

$termCsvPath = Join-Path $reportDir "native_workflow_region_terms.csv"
$chunkCsvPath = Join-Path $reportDir "native_workflow_bxml_chunks.csv"
$summaryPath = Join-Path $reportDir "native_workflow_region_map_summary.md"
$termRows | Export-Csv -LiteralPath $termCsvPath -NoTypeInformation -Encoding UTF8
$chunkRows | Export-Csv -LiteralPath $chunkCsvPath -NoTypeInformation -Encoding UTF8

$diffCsvPath = ""
$diffRanges = @()
if (-not [string]::IsNullOrWhiteSpace($CompareStoreFile)) {
    $comparePath = (Resolve-Path -LiteralPath $CompareStoreFile).Path
    $compareBytes = [System.IO.File]::ReadAllBytes($comparePath)
    $diffRanges = @(Get-DiffRanges -Left $bytes -Right $compareBytes)
    $diffCsvPath = Join-Path $reportDir "native_workflow_byte_diff_ranges.csv"
    $diffRanges | Export-Csv -LiteralPath $diffCsvPath -NoTypeInformation -Encoding UTF8
}

$interesting = @(
    $termRows |
        Where-Object { $_.term -in @("SheetSaveCmd", "SystemCmd", "powershell.exe", "petrel_export_mvp_bridge.ps1", "export_package", "cli_variable") } |
        Sort-Object offset |
        Select-Object -First 40
)

$md = @(
    "# Native Workflow Region Map",
    "",
    "- Created UTC: $((Get-Date).ToUniversalTime().ToString("o"))",
    "- Store file: $storePath",
    "- Store bytes: $($bytes.Length)",
    "- BXML markers: $($bxmlOffsets.Count)",
    "- LZ4 markers: $($lz4Offsets.Count)",
    "",
    "## Key Hits",
    "",
    "| Term | Offset | Previous LZ4 | Previous BXML | Next BXML | Guess |",
    "| --- | ---: | ---: | ---: | ---: | --- |"
)

foreach ($row in $interesting) {
    $guess = ([string]$row.command_type_guess) -replace "\|", "/"
    $md += "| $($row.term) | $($row.offset) | $($row.previous_lz4_offset) | $($row.previous_bxml_offset) | $($row.next_bxml_offset) | $guess |"
}

$md += @(
    "",
    "## Outputs",
    "",
    "- Term map: $termCsvPath",
    "- BXML chunk map: $chunkCsvPath"
)

if ($diffCsvPath) {
    $md += "- Diff ranges: $diffCsvPath"
    $md += "- Diff range count: $($diffRanges.Count)"
}

$md | Set-Content -LiteralPath $summaryPath -Encoding UTF8

Write-Output "Native workflow region map complete"
Write-Output "Summary: $summaryPath"
Write-Output "Term map: $termCsvPath"
Write-Output "BXML chunk map: $chunkCsvPath"
if ($diffCsvPath) {
    Write-Output "Diff ranges: $diffCsvPath"
}
