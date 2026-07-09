# Installing on a Fresh Windows Machine

Step-by-step guide for a machine with **nothing installed** — no Git, no Python. Total time is typically 10–15 minutes, most of it downloads.

## 0. What you need

- Windows 10/11 with internet access and permission to install software
- ~2 GB free disk space
- Petrel 2018.2 only if you intend to run the live-Petrel tools; 32 of the 41 tools work without it

## 1. Install Git

Open PowerShell and run:

```powershell
winget install --id Git.Git -e --source winget
```

(No winget? Download the installer from https://git-scm.com/download/win and accept the defaults.)

Close PowerShell, open a **new** PowerShell window, and verify:

```powershell
git --version
```

## 2. Install Python 3.10+ (3.11–3.13 recommended)

```powershell
winget install --id Python.Python.3.13 -e --source winget
```

(Or download from https://www.python.org/downloads/ — on the first installer screen, **check "Add python.exe to PATH"**.)

Open a **new** PowerShell window and verify:

```powershell
python --version
```

> If `python` opens the Microsoft Store instead of printing a version, disable the alias under **Settings → Apps → Advanced app settings → App execution aliases** (turn off both `python.exe` entries), or install from python.org.

## 3. Clone the repository

```powershell
cd $env:USERPROFILE\Code   # or wherever you keep code; create the folder first if needed
git clone https://github.com/ahmedsahernouh/petrel-agent-mcp
cd petrel-agent-mcp
```

## 4. Run the one-command setup

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\setup_petrel_mcp.ps1
```

This single command:

1. verifies Python is 3.10+
2. creates a local `.venv` (nothing touches your system Python)
3. installs the optional geodata packages into it (numpy, zmapio, pyzgy, lasio, pandas)
4. writes the project `.mcp.json` with absolute paths for this checkout
5. reports whether Tesseract and Petrel are present (informational — nothing fails without them)
6. runs the 41-tool protocol smoke test

**Success looks like** `Petrel MCP smoke test passed` near the end. Lines starting with `SKIP:` and the `NOTE: ... using mini fixture package` line are **normal** on a fresh machine — they mark checks that need machine-local Petrel evidence you don't have yet. If the geodata install fails (e.g., a temporary network issue), setup continues with a warning; the server still works and only the surface/ZGY/grid/LAS chain tools are affected — rerun setup later to retry.

## 5. Connect your MCP client

**Claude Code**: open the repo folder and start `claude`; it detects the project `.mcp.json` — approve the server when prompted (`/mcp` shows its status).

**Claude Desktop**: add to `%APPDATA%\Claude\claude_desktop_config.json` (adjust the checkout path):

```json
{
  "mcpServers": {
    "petrel-no-ocean-control": {
      "command": "C:\\path\\to\\petrel-agent-mcp\\.venv\\Scripts\\python.exe",
      "args": ["C:\\path\\to\\petrel-agent-mcp\\mcp\\petrel_mcp_server.py"]
    }
  }
}
```

**Any other MCP client**: stdio transport, command = the `.venv` python, args = the server script. `.mcp.json` in the repo root is a working reference.

## 6. Optional external tools

- **Tesseract OCR** (deterministic GUI tools only): installer at https://github.com/UB-Mannheim/tesseract/wiki — the default `C:\Program Files\Tesseract-OCR` location is auto-detected. Rerun setup afterwards to confirm it is seen.
- **Petrel 2018.2** (the 9 live-Petrel tools only): your licensed install; the default `C:\Program Files\Schlumberger\Petrel 2018` location is auto-detected.

## 7. First agent session

Ask your agent to call, in order:

```text
petrel_agent_readiness   → server version, tool maturity, dependency report
petrel_status            → package/manifest state (fixture package on a fresh machine)
petrel_tool_creation_hierarchy
petrel_tool_failure_policy
```

To work on **your own Petrel project**: `petrel_prepare_mvp` with your `.pet` path, then the zero-GUI exporters, then `petrel_project_audit_report` for the HTML audit. See the README's "Quickstart (your own Petrel project)".

## 8. Updates: getting new tools and fixes

```powershell
cd <checkout>\petrel-agent-mcp
git pull
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\setup_petrel_mcp.ps1
```

`git pull` brings new/fixed tools; rerunning setup is **idempotent and safe** — it reuses the existing venv, installs any newly added packages, refreshes `.mcp.json`, and re-proves the install with the smoke test. Restart your MCP client (or `/mcp` reconnect) so it picks up the new tool list. Confirm the version with `petrel_agent_readiness` → `server.version`.

If you have local edits that block `git pull`, stash them first: `git stash`, pull, `git stash pop`.

## 9. When something fails: logs and diagnostics

**Usage log (watch behavior, success and failure).** Every tool call is appended as one JSON line to a per-day file:

```text
build\mcp_usage\petrel_mcp_usage_YYYYMMDD.jsonl
```

Each line records the UTC timestamp, server version, tool name, duration in ms, scalar arguments, `outcome` (`ok`/`error`), the tool's `status`, the fail-closed `audit_status`, and `failure_class` when something failed. Watch it live in a second PowerShell window while the agent works:

```powershell
Get-Content "build\mcp_usage\petrel_mcp_usage_$((Get-Date).ToUniversalTime().ToString('yyyyMMdd')).jsonl" -Wait -Tail 20
```

Count successes vs failures for a session:

```powershell
Get-Content build\mcp_usage\*.jsonl | ConvertFrom-Json | Group-Object outcome | Select-Object Name, Count
```

Set `PETREL_MCP_USAGE_LOG=0` in the server's environment to disable logging.

**Per-call audit.** Every tool response embeds `mcp_result_audit` (status, evidence, failure class, fallback chain, next safe action) — the agent sees it, and it is the first thing to read on a failure.

**Diagnostics, in order:**

```powershell
python scripts\test_petrel_mcp_server.py                                              # protocol-level: is the server itself healthy?
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\doctor_petrel_mcp.ps1 # environment: writes a JSON report under build\mcp_doctor\
```

**Reporting a failure for a fix.** Collect three things: the relevant usage-log lines, the `mcp_result_audit` JSON from the failing response, and the latest `build\mcp_doctor\*.json` report. With those, the failure is usually reproducible and fixable in the main repo — then this machine just runs step 8 to receive the fix.
