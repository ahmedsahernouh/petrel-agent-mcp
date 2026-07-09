# Stage 1 No-Ocean MCP Baseline

Stage 1 means the project has a working LLM/tool control surface that does not depend on an Ocean developer license.

## Completion Criteria

- The no-Ocean MCP server is implemented and smoke-tested.
- Codex, VS Code, OpenCode, and Claude configs launch the same server.
- The server exposes Petrel status, MVP generation, project-open dry-run/writable launch, validation, KB query, native snapshot/compare, native map, and guarded patch tools.
- The stage can be validated without launching Petrel or mutating `.pet/.ptd` files.
- A native before/after snapshot baseline proves unchanged files compare cleanly.

## Main Files

- `mcp/petrel_mcp_server.py`
- `scripts/test_petrel_mcp_server.py`
- `scripts/test_petrel_mcp_client_configs.py`
- `scripts/test_petrel_stage1_no_ocean_mcp.ps1`
- `scripts/new_petrel_native_workflow_snapshot.ps1`
- `scripts/compare_petrel_native_workflow_snapshots.ps1`
- `scripts/compare_petrel_native_workflow_snapshots.py`
- `docs/NO_OCEAN_MCP_CONTROL.md`

## Validation

Run:

```powershell
cd "D:\Computer\Code\Petrel_project"
.\scripts\test_petrel_stage1_no_ocean_mcp.ps1
```

This command does not launch Petrel. It verifies:

1. MCP protocol smoke test.
2. Codex, VS Code, OpenCode, and Claude MCP config launchability.
3. MVP artifact generation.
4. Petrel project-open command generation in dry-run writable mode.
5. Native before/after snapshot creation.
6. Native snapshot comparison with zero differences.

Latest confirmed validation:

```text
D:\Computer\Code\Petrel_project\build\stage1_no_ocean_mcp\stage1_no_ocean_mcp_validation_20260702_223224.md
```

Result:

```text
Status: passed
Model.ptd changed: False, diff ranges: 0
Data.ptd changed: False, diff ranges: 0
```

## Stage 2 Status

The first Stage 2 Petrel-authored workflow edit is complete. A `System command` was added manually in `ExportPiloX`, saved into native `.ptd` storage, mapped by before/after snapshot diff, and executed from the external runner. The saved `SystemCmd` argument payload is now also controllable from MCP through a guarded same-length patch-run-restore tool.

Evidence:

```text
Before snapshot: D:\Computer\Code\Petrel_project\build\native_edit_experiments\native_workflow_snapshot_20260704_085738_before_manual_system_command_donor
After snapshot: D:\Computer\Code\Petrel_project\build\native_edit_experiments\native_workflow_snapshot_20260704_092035_after_manual_system_command_donor
Compare report: D:\Computer\Code\Petrel_project\build\native_edit_experiments\native_workflow_snapshot_compare_20260704_092053\snapshot_compare_report.json
Run status: D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\automation_runs\petrel_automation_20260704_092507.json
Bridge status: D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\automation_runs\petrel_export_mvp_bridge_20260704_092550.json
Validation: D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\validation_reports\export_validation_20260704_092609.md
```

Guarded SystemCmd patch proof:

```text
Analyzer report: D:\Computer\Code\Petrel_project\build\native_edit_experiments\systemcmd_record_map_20260704_100011\systemcmd_record_map.json
Tool: petrel_export_systemcmd_token_patch
Patch: Data.ptd post -> p0st at offset 173185535
Target bridge step: p0st_export_register_validate
Report: D:\Computer\Code\Petrel_project\build\native_edit_experiments\systemcmd_token_patch_export_20260704_100224\systemcmd_token_patch_export_report.json
Run status: D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\automation_runs\petrel_automation_20260704_100230.json
Bridge status: D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\automation_runs\petrel_export_mvp_bridge_20260704_100312.json
Validation rows: 735, failed: 0
Restore compare clean: true
```

Stage 2 now proves saved donor execution and same-length donor-argument mutation through MCP. Zero-GUI command insertion, record resizing, and new workflow creation are still not proven.
