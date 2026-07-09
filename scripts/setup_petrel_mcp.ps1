# One-command bootstrap for the Petrel MCP server on a fresh clone or moved checkout.
# Creates the repo venv if missing, installs the optional geodata packages (fail-soft),
# regenerates the project-scoped .mcp.json, reports optional external dependencies
# (Tesseract, Petrel), and runs the protocol smoke test.
# This script does not launch Petrel and does not touch .pet/.ptd files.
#
# Usage:
#   powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\setup_petrel_mcp.ps1
#   powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\setup_petrel_mcp.ps1 -PythonPath "C:\path\to\python.exe"
#   powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\setup_petrel_mcp.ps1 -NoVenv -NoGeodata -NoSmoke   # config-only, old behavior
[CmdletBinding()]
param(
    [string]$PythonPath,

    [switch]$NoVenv,

    [switch]$NoGeodata,

    [switch]$NoSmoke
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

function Get-PythonVersionTuple {
    param([string]$Exe)
    $raw = & $Exe -c "import sys; print('%d.%d.%d' % sys.version_info[:3])" 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $raw) { return $null }
    return [version]$raw.Trim()
}

# 1. Resolve a base Python interpreter: explicit -> repo venv -> PATH python -> py launcher.
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not $PythonPath) {
    if (Test-Path -LiteralPath $venvPython) {
        $PythonPath = $venvPython
    } else {
        $pathPython = Get-Command python -ErrorAction SilentlyContinue
        if ($pathPython) {
            $PythonPath = $pathPython.Source
        } else {
            $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
            if ($pyLauncher) {
                $resolved = & $pyLauncher.Source -3 -c "import sys; print(sys.executable)" 2>$null
                if ($LASTEXITCODE -eq 0 -and $resolved) { $PythonPath = $resolved.Trim() }
            }
        }
    }
}
if (-not $PythonPath -or -not (Test-Path -LiteralPath $PythonPath)) {
    throw "No Python interpreter found. Install Python 3.10+ from https://www.python.org and rerun."
}
$PythonPath = (Resolve-Path -LiteralPath $PythonPath).Path

$pyVersion = Get-PythonVersionTuple -Exe $PythonPath
if (-not $pyVersion) {
    throw "Could not run $PythonPath to determine its version."
}
if ($pyVersion -lt [version]"3.10") {
    throw "Python $pyVersion at $PythonPath is too old; the MCP server needs Python 3.10+."
}
Write-Output "Python: $PythonPath ($pyVersion)"

# 2. Create the repo venv when missing so optional packages stay isolated from the system Python.
if (-not $NoVenv) {
    if (-not (Test-Path -LiteralPath $venvPython)) {
        Write-Output "Creating repo venv at .venv ..."
        & $PythonPath -m venv (Join-Path $repoRoot ".venv")
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $venvPython)) {
            Write-Warning "venv creation failed; continuing with $PythonPath. Optional packages will install into it instead."
        } else {
            $PythonPath = $venvPython
            Write-Output "venv created: $PythonPath"
        }
    } else {
        $PythonPath = $venvPython
    }
}

# 3. Install the optional geodata packages (surface/ZGY/grid/LAS chain tools). Fail-soft:
#    the MCP server itself is pure stdlib and works without them; affected tools preflight-fail.
$geodataStatus = "skipped (-NoGeodata)"
if (-not $NoGeodata) {
    $requirements = Join-Path $repoRoot "requirements-geodata.txt"
    if (Test-Path -LiteralPath $requirements) {
        Write-Output "Installing optional geodata packages (numpy/zmapio/pyzgy/lasio/pandas) ..."
        & $PythonPath -m pip install --disable-pip-version-check --quiet -r $requirements
        if ($LASTEXITCODE -eq 0) {
            $geodataStatus = "installed"
        } else {
            $geodataStatus = "FAILED (server still works; surface/ZGY/grid/LAS chain tools will preflight-fail until installed)"
            Write-Warning "Geodata package install failed. Retry later with: `"$PythonPath`" -m pip install -r requirements-geodata.txt"
        }
    } else {
        $geodataStatus = "requirements-geodata.txt not found"
    }
}

# 4. Write the project-scoped .mcp.json for this checkout.
$serverPath = Join-Path $repoRoot "mcp\petrel_mcp_server.py"
if (-not (Test-Path -LiteralPath $serverPath)) {
    throw "Petrel MCP server not found at $serverPath"
}

$config = [ordered]@{
    mcpServers = [ordered]@{
        "petrel-no-ocean-control" = [ordered]@{
            type    = "stdio"
            command = $PythonPath
            args    = @($serverPath)
            env     = [ordered]@{
                PETREL_MCP_PROJECT_ROOT = $repoRoot
                PETREL_MCP_PYTHON       = $PythonPath
            }
        }
    }
}

$targetPath = Join-Path $repoRoot ".mcp.json"
$json = ConvertTo-Json -InputObject $config -Depth 5
[System.IO.File]::WriteAllText($targetPath, $json + "`n", (New-Object System.Text.UTF8Encoding($false)))

# Fail closed if PowerShell JSON serialization flattened the args array to a scalar.
$parsed = Get-Content -LiteralPath $targetPath -Raw | ConvertFrom-Json
$serverEntry = $parsed.mcpServers.'petrel-no-ocean-control'
if ($serverEntry.args -is [string]) {
    throw ".mcp.json args serialized as a scalar instead of an array; fix the serialization before using this config."
}
if ($serverEntry.command -ne $PythonPath) {
    throw ".mcp.json command does not match the resolved Python path."
}

# 5. Report optional external dependencies without failing; only some tools need them.
$tesseract = $null
foreach ($candidate in @(
    $env:PETREL_TESSERACT_PATH,
    $env:TESSERACT_PATH,
    "$env:ProgramFiles\Tesseract-OCR\tesseract.exe"
)) {
    if ($candidate -and (Test-Path -LiteralPath $candidate)) { $tesseract = $candidate; break }
}
if (-not $tesseract) {
    $tesseractCmd = Get-Command tesseract -ErrorAction SilentlyContinue
    if ($tesseractCmd) { $tesseract = $tesseractCmd.Source }
}
$petrelExe = Get-ChildItem "$env:ProgramFiles\Schlumberger\Petrel *\Petrel.exe" -ErrorAction SilentlyContinue | Select-Object -First 1

Write-Output ""
Write-Output "Petrel MCP project config written: $targetPath"
Write-Output "Server: $serverPath (pure stdlib; no packages required to run)"
Write-Output "Optional geodata packages: $geodataStatus"
if ($tesseract) {
    Write-Output "Tesseract OCR: $tesseract (deterministic GUI tools available)"
} else {
    Write-Output "Tesseract OCR: not found (only deterministic GUI tools need it; they will preflight-fail closed)"
}
if ($petrelExe) {
    Write-Output "Petrel: $($petrelExe.FullName)"
} else {
    Write-Output "Petrel: not found (only the 9 tools that launch or drive Petrel need it)"
}

# 6. Prove the install with the protocol-level smoke test.
if (-not $NoSmoke) {
    Write-Output ""
    Write-Output "Running MCP smoke test ..."
    & $PythonPath (Join-Path $repoRoot "scripts\test_petrel_mcp_server.py")
    if ($LASTEXITCODE -ne 0) {
        throw "MCP smoke test failed; see output above."
    }
}

Write-Output ""
Write-Output "Setup complete. Approve the project MCP server inside your client (Claude Code: /mcp)."
Write-Output "Optional next check: powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\doctor_petrel_mcp.ps1"
