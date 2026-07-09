#!/usr/bin/env python3
"""Validate Petrel MCP client config entries and launch each configured server."""

from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_TOOLS = {
    "petrel_agent_readiness",
    "petrel_tool_creation_hierarchy",
    "petrel_tool_failure_policy",
    "petrel_status",
    "petrel_open_project",
    "petrel_native_snapshot",
    "petrel_native_compare_snapshots",
    "petrel_native_patch_string",
    "petrel_native_patch_offset",
    "petrel_export_well_tables_zero_gui",
    "petrel_export_well_tops_native_probe",
    "petrel_export_well_logs_ui",
    "petrel_export_well_tops_ui",
    "petrel_run_deterministic_gui_workflow",
    "petrel_export_segy_filename_patch",
    "petrel_export_segy_token_patch",
    "petrel_analyze_exportseismiccmd_records",
    "petrel_analyze_systemcmd_records",
    "petrel_analyze_workflow_command_clone_readiness",
    "petrel_analyze_workflow_clone_side_effects",
    "petrel_analyze_workflow_clone_storage_blocks",
    "petrel_extract_workflow_command_clone_recipe",
}

HOME = Path.home()
CONFIGS = {
    "codex": HOME / ".codex" / "config.toml",
    "vscode": HOME / "AppData" / "Roaming" / "Code" / "User" / "mcp.json",
    "opencode": HOME / ".config" / "opencode" / "opencode.jsonc",
    "claude_code_project": REPO_ROOT / ".mcp.json",
}
CLAUDE_CONFIG_CANDIDATES = [
    HOME / "AppData" / "Roaming" / "Claude" / "claude_desktop_config.json",
]
_packages_root = HOME / "AppData" / "Local" / "Packages"
if _packages_root.exists():
    CLAUDE_CONFIG_CANDIDATES.extend(
        sorted(_packages_root.glob(r"Claude_*\LocalCache\Roaming\Claude\claude_desktop_config.json"))
    )


def request(proc: subprocess.Popen[str], payload: dict[str, Any]) -> dict[str, Any]:
    assert proc.stdin is not None
    assert proc.stdout is not None
    proc.stdin.write(json.dumps(payload) + "\n")
    proc.stdin.flush()
    line = proc.stdout.readline()
    if not line:
        stderr = proc.stderr.read() if proc.stderr else ""
        raise RuntimeError(f"MCP server returned no response. stderr={stderr}")
    return json.loads(line)


def smoke(command: list[str], cwd: str | None = None) -> set[str]:
    proc = subprocess.Popen(
        command,
        cwd=cwd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        init = request(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "petrel-config-smoke", "version": "0"},
                },
            },
        )
        if init["result"]["serverInfo"]["name"] != "petrel-no-ocean-control":
            raise AssertionError(init)
        tools = request(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        return {tool["name"] for tool in tools["result"]["tools"]}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def codex_command() -> tuple[list[str], str | None]:
    with CONFIGS["codex"].open("rb") as handle:
        data = tomllib.load(handle)
    server = data["mcp_servers"]["petrel-no-ocean-control"]
    return [server["command"], *server.get("args", [])], None


def vscode_command() -> tuple[list[str], str | None]:
    data = json.loads(CONFIGS["vscode"].read_text(encoding="utf-8-sig"))
    server = data["servers"]["petrel-no-ocean-control"]
    return [server["command"], *server.get("args", [])], server.get("cwd")


def opencode_command() -> tuple[list[str], str | None]:
    data = json.loads(CONFIGS["opencode"].read_text(encoding="utf-8-sig"))
    server = data["mcp"]["petrel-no-ocean-control"]
    return list(server["command"]), None


def claude_command(config_path: Path) -> tuple[list[str], str | None]:
    data = json.loads(config_path.read_text(encoding="utf-8-sig"))
    server = data["mcpServers"]["petrel-no-ocean-control"]
    return [server["command"], *server.get("args", [])], server.get("cwd")


def claude_code_project_command() -> tuple[list[str], str | None]:
    data = json.loads(CONFIGS["claude_code_project"].read_text(encoding="utf-8-sig"))
    server = data["mcpServers"]["petrel-no-ocean-control"]
    return [server["command"], *server.get("args", [])], server.get("cwd")


def main() -> int:
    resolvers = {}
    for name, builder in (("codex", codex_command), ("vscode", vscode_command), ("opencode", opencode_command)):
        if CONFIGS[name].exists():
            resolvers[name] = builder
        else:
            print(f"SKIP: {name} config not found ({CONFIGS[name]})")
    if CONFIGS["claude_code_project"].exists():
        resolvers["claude_code_project"] = claude_code_project_command
    else:
        print("SKIP: project .mcp.json not found; run scripts\\setup_petrel_mcp.ps1 to generate it")
    seen_claude_paths: set[Path] = set()
    for path in CLAUDE_CONFIG_CANDIDATES:
        if path in seen_claude_paths or not path.exists():
            continue
        seen_claude_paths.add(path)
        name = "claude" if len(seen_claude_paths) == 1 else f"claude_{len(seen_claude_paths)}"
        resolvers[name] = lambda config_path=path: claude_command(config_path)
    if not seen_claude_paths:
        print("SKIP: no Claude Desktop config found in the standard Roaming or Microsoft Store paths")

    verified = 0
    for name, resolver in resolvers.items():
        try:
            command, cwd = resolver()
        except KeyError:
            print(f"SKIP: {name} config exists but has no petrel-no-ocean-control entry")
            continue
        if not Path(command[0]).exists():
            raise FileNotFoundError(f"{name} command not found: {command[0]}")
        tool_names = smoke(command, cwd)
        missing = REQUIRED_TOOLS - tool_names
        if missing:
            raise AssertionError(f"{name} missing tools: {sorted(missing)}")
        print(f"{name}: ok ({len(tool_names)} tools)")
        verified += 1
    if verified == 0:
        raise AssertionError(
            "No client config with a petrel-no-ocean-control entry was verified. "
            "Run scripts\\setup_petrel_mcp.ps1 to generate the project .mcp.json, then rerun."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
