# Regenerate the project-scoped .mcp.json for this checkout so the Petrel MCP server
# works after cloning or moving the repository to a new path or machine.
# This script does not launch Petrel and does not touch .pet/.ptd files.
#
# Usage:
#   powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\setup_petrel_mcp.ps1
#   powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\setup_petrel_mcp.ps1 -PythonPath "C:\path\to\python.exe"
[CmdletBinding()]
param(
    [string]$PythonPath
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

if (-not $PythonPath) {
    $venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $venvPython) {
        $PythonPath = $venvPython
    } else {
        $pathPython = Get-Command python -ErrorAction SilentlyContinue
        if ($pathPython) {
            $PythonPath = $pathPython.Source
            Write-Warning "Repo venv not found; falling back to PATH python at $PythonPath. Create the venv with: py -m venv .venv"
        }
    }
}
if (-not $PythonPath -or -not (Test-Path -LiteralPath $PythonPath)) {
    throw "No Python interpreter found. Create the repo venv first: py -m venv .venv"
}
$PythonPath = (Resolve-Path -LiteralPath $PythonPath).Path

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

Write-Output "Petrel MCP project config written: $targetPath"
Write-Output "Python: $PythonPath"
Write-Output "Server: $serverPath"
Write-Output "Next steps:"
Write-Output "  python scripts\test_petrel_mcp_client_configs.py"
Write-Output "  powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\doctor_petrel_mcp.ps1"
Write-Output "Then approve the project MCP server inside your client (Claude Code: /mcp)."
