# AI Coder Handover - Petrel Project

Date: 2026-07-08

Repo:

```text
D:\Computer\Code\Petrel_project
```

Primary goal:

```text
Build no-Ocean, AI-agent-controlled Petrel automation through MCP, tools, workflows, native project evidence, deterministic GUI fallbacks, and an agent-first OKF/wiki.
```

## Executive State

The project is ready for an AI coder to continue from the local repo and MCP surface.

Verified on 2026-07-09:

```text
OKF validation: passed, 0 warnings
MCP server smoke: passed
MCP tools: 41
Client configs: codex ok, vscode ok, opencode ok, claude_code_project ok, claude ok, claude_2 ok
MCP doctor: ready
Manifest rows reported by smoke test: 805
Doctor report: build\mcp_doctor\petrel_mcp_doctor_20260709_040852.json
```

The project is not finished as full Petrel automation. It is a strong Stage 1/early Stage 2 control surface with proven zero-GUI export/package work, saved Workflow Editor command execution, guarded native parameter mutation, and deterministic GUI fallback for one difficult confirmed export class.

## Read Order For A New AI Coder

Read this sequence:

1. `CLAUDE.md`
2. `AGENTS.md`
3. `README.md`
4. `docs\NO_OCEAN_MCP_CONTROL.md`
5. `docs\PETREL_TOOL_CREATION_HIERARCHY.md`
6. `docs\MCP_FAILURE_POLICY.md`
7. `docs\FULL_PROJECT_EXPORT_MVP.md`
8. `docs\DETERMINISTIC_PETREL_GUI_WORKFLOWS.md`
9. `docs\PETREL_NATIVE_WORKFLOW_EDITING.md`
10. `vault\Petrel Knowledge Wiki\50 Concepts\Agent First OKF Contract.md`

Do not start by reading every OCR/manual note. Use the routing docs and MCP tools first.

## Environment

Validated local dependencies:

```text
Python: D:\Computer\Code\Petrel_project\.venv\Scripts\python.exe
Tesseract: C:\Program Files\Tesseract-OCR\tesseract.exe
Repo root: D:\Computer\Code\Petrel_project
MCP server: D:\Computer\Code\Petrel_project\mcp\petrel_mcp_server.py
```

Safe readiness commands:

```powershell
cd "D:\Computer\Code\Petrel_project"
python scripts\validate_okf_bundle.py "vault\Petrel Knowledge Wiki"
python scripts\test_petrel_mcp_server.py
python scripts\test_petrel_mcp_client_configs.py
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\doctor_petrel_mcp.ps1
```

These commands do not launch Petrel.

## MCP Setup For Claude Code

The repo has a project-scoped `.mcp.json`:

```text
D:\Computer\Code\Petrel_project\.mcp.json
```

Claude Code may ask the user to trust the workspace and approve the project MCP server.

Manual Claude Code setup, if needed:

```powershell
cd "D:\Computer\Code\Petrel_project"
claude mcp add --transport stdio --scope project petrel-no-ocean-control -- "D:\Computer\Code\Petrel_project\.venv\Scripts\python.exe" "D:\Computer\Code\Petrel_project\mcp\petrel_mcp_server.py"
claude mcp list
```

Then inside Claude Code:

```text
/mcp
```

The official Claude Code MCP docs, checked 2026-07-08, describe local stdio servers with:

```text
claude mcp add [options] <name> -- <command> [args...]
```

Source:

```text
https://code.claude.com/docs/en/mcp
```

## First MCP Calls

Use the MCP surface to orient before file edits:

```text
petrel_agent_readiness
petrel_status
petrel_tool_creation_hierarchy
petrel_tool_failure_policy
petrel_query_kb
```

If working on Well Tops:

```text
petrel_export_well_tops_native_probe
petrel_run_deterministic_gui_workflow
petrel_import_gui_well_tops_table
```

If working on native workflow mapping:

```text
petrel_native_snapshot
petrel_native_compare_snapshots
petrel_native_map_workflow
petrel_analyze_exportseismiccmd_records
petrel_analyze_systemcmd_records
petrel_analyze_workflow_command_clone_readiness
petrel_analyze_workflow_clone_side_effects
petrel_analyze_workflow_clone_storage_blocks
petrel_extract_workflow_command_clone_recipe
```

If working on package/manifest validation:

```text
petrel_register_and_validate
petrel_validate_workflow_coverage
petrel_run_zero_gui_export_mvp
petrel_export_native_zero_gui
petrel_export_native_semantic_zero_gui
petrel_export_well_tables_zero_gui
```

## Tool Surface Summary

Stable/read-only or low-risk tools include:

```text
petrel_agent_readiness
petrel_tool_creation_hierarchy
petrel_tool_failure_policy
petrel_status
petrel_query_kb
petrel_prepare_mvp
petrel_register_and_validate
petrel_export_native_zero_gui
petrel_run_zero_gui_export_mvp
petrel_export_native_semantic_zero_gui
petrel_export_well_tables_zero_gui
petrel_export_well_tops_native_probe
petrel_import_gui_well_tops_table
petrel_validate_workflow_coverage
petrel_native_map_workflow
petrel_native_snapshot
petrel_native_compare_snapshots
petrel_analyze_exportseismiccmd_records
petrel_analyze_systemcmd_records
petrel_analyze_workflow_command_clone_readiness
petrel_analyze_workflow_clone_side_effects
petrel_analyze_workflow_clone_storage_blocks
petrel_extract_workflow_command_clone_recipe
petrel_generate_workflow_from_okf
petrel_export_surfaces_zero_gui
petrel_survey_geometry
petrel_grid_convert
petrel_export_seismic_zgy_zero_gui
petrel_write_well_tops_ascii
petrel_las_convert
petrel_project_audit_report
```

Beta tools require Petrel runtime state, saved donor commands, or deterministic GUI preconditions:

```text
petrel_open_project
petrel_run_mvp
petrel_export_well_logs_ui
petrel_export_well_tops_ui
petrel_run_deterministic_gui_workflow
petrel_export_segy_filename_patch
petrel_export_segy_token_patch
petrel_export_systemcmd_token_patch
```

Experimental low-level primitives:

```text
petrel_native_patch_string
petrel_native_patch_offset
```

Use the patch-run-restore wrappers for real proof. A raw low-level applied patch is not enough.

## Tool Creation Hierarchy

Every new tool must use the highest viable tier:

1. `zero_gui_python`: direct file/package parsing, no Petrel launch, no desktop GUI.
2. `zero_gui_petrel_workflow_editor`: saved Workflow Editor commands, CLI workflow runs, variables, or guarded native parameter edits.
3. `deterministic_gui`: named fixed GUI micro-workflow, fail-closed, with output validation.
4. `discovery_only`: donor capture or mapping, not production automation.

Every new tool needs:

```text
task
inputs
outputs
runtime_boundary
validation
failure modes
evidence paths
dry-run behavior where mutating
manifest registration behavior
```

## Current Export Capability

Achieved:

- Raw native project-store package to `08_native_project`.
- Semantic zero-GUI extraction for safe native stores: SMD faults/horizons/zones/frameworks, GMS properties, SQLite, XML/BXML metadata, ZGY inventory.
- LAS-derived well headers and curve inventory.
- Conservative zero-GUI well-top/native/source evidence.
- Petrel-authored Well Tops ASCII export parsing with 84 confirmed marker-pick rows.
- LAS logs exported through mapped UI fallback.
- SEG-Y exported through saved Workflow Editor donor commands.
- Same-length SEG-Y output token mutation through MCP patch-run-restore.
- Same-length saved SystemCmd bridge StepName mutation through MCP patch-run-restore.
- Manifest registration and validation pipeline.
- OKF/wiki query and workflow generation scaffolding.

Not achieved:

- Full universal-format decoding of proprietary native stores.
- Zero-GUI native binary decoding of actual Well Tops marker-pick depth payload.
- Zero-GUI insertion of new Petrel Workflow Editor commands.
- New workflow creation in native `.pet/.ptd` storage.
- Generalized Petrel export automation for every object class and every Petrel version.
- Stable broad desktop GUI agent behavior.

## Well Tops Boundary

Confirmed:

```text
Petrel-authored ASCII export -> parsed CSV -> 84 actual marker-pick rows -> GUI comparison matched=84 -> manifest validation passed
```

Important output:

```text
build\export_pilots\petrel2010_demo_project_export_20260701_060609\02_wells\well_tops\well_tops_from_petrel_ascii_export.csv
```

Not confirmed:

```text
Native binary marker-pick payload decoding
Zero-GUI creation/insertion of the Well Tops export command
```

The deterministic GUI helper was updated to distinguish the Explorer `Input` tab strip from `Processes > Input`. A valid `Input` target must be in the tab strip with sibling labels:

```text
Models
Results
Templates
```

If the helper only sees `Processes > Input`, it must fail closed.

## Native Workflow Boundary

Proven:

- Same-length workflow-name and payload-token edits can affect Petrel execution when offsets are known.
- Saved `ExportSeismicCmd` donors can be executed externally.
- Saved `SystemCmd` bridge can call back to external PowerShell during a workflow run.
- Same-length parameter patches can be run, validated, and restored through MCP wrappers.

Blocked:

- Command clone/insert patcher.
- Record resizing.
- GUID/tag/object-reference/index semantics.
- Model.ptd UI/object-reference side-effect mapping.
- Applied clone recovery proof.

Expected current analyzer result:

```text
clone_safe=false
recipe_safe_to_apply=false
status=blocked
```

That is a good result. It means the analyzer is enforcing the boundary.

## Deterministic GUI Boundary

GUI is allowed only through named deterministic workflows under:

```text
petrel_gui_workflows\
```

Current specs:

```text
petrel_gui_workflows\export_well_tops_ascii.json
petrel_gui_workflows\export_well_tops_table_clipboard.json
```

Dry run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\invoke_petrel_deterministic_gui_workflow.ps1 -WorkflowId export_well_tops_ascii
```

Live run requires explicit execution and a visible Petrel session:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\invoke_petrel_deterministic_gui_workflow.ps1 -WorkflowId export_well_tops_ascii -Execute
```

Do not use GUI automation as a free-form clicker. Every GUI run must write a runner report and validate outputs.

## Key Paths

MCP:

```text
mcp\petrel_mcp_server.py
mcp\petrel_tool_creation_hierarchy.json
mcp\petrel_mcp_failure_policies.json
```

Core docs:

```text
docs\NO_OCEAN_MCP_CONTROL.md
docs\FULL_PROJECT_EXPORT_MVP.md
docs\PETREL_TOOL_CREATION_HIERARCHY.md
docs\MCP_FAILURE_POLICY.md
docs\DETERMINISTIC_PETREL_GUI_WORKFLOWS.md
docs\PETREL_NATIVE_WORKFLOW_EDITING.md
docs\STAGE_1_NO_OCEAN_MCP_BASELINE.md
```

Export package:

```text
build\export_pilots\petrel2010_demo_project_export_20260701_060609
```

Workflow specs:

```text
petrel_gui_workflows\
```

Vault:

```text
vault\Petrel Knowledge Wiki\
```

## Safe Workflows For A New Agent

### Confirm readiness

```powershell
cd "D:\Computer\Code\Petrel_project"
python scripts\test_petrel_mcp_server.py
python scripts\test_petrel_mcp_client_configs.py
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\doctor_petrel_mcp.ps1
```

### Query the KB before designing a tool

Use MCP:

```text
petrel_query_kb
petrel_generate_workflow_from_okf
petrel_validate_workflow_coverage
```

### Validate without Petrel

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\run_petrel_zero_gui_export_mvp.ps1
```

### Register and validate current package

Use MCP:

```text
petrel_register_and_validate
```

Or script:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\validate_export_package.ps1
```

### Analyze native commands without mutation

Use MCP:

```text
petrel_analyze_exportseismiccmd_records
petrel_analyze_systemcmd_records
petrel_extract_workflow_command_clone_recipe
```

## Known Practical Gaps (2026-07-08 Review, updated same day)

Resolved by the 2026-07-08 hardening pass (server `0.7.0`):

- **`petrel_run_mvp` is now safe by default.** `dry_run` defaults to `true` (applied server-side, so clients that omit the argument get dry-run behavior); a live Petrel workflow run requires an explicit `dry_run=false`. See [docs/MCP_FAILURE_POLICY.md](MCP_FAILURE_POLICY.md).

- **`petrel_status` is now compact by default.** It previously inlined all 766 manifest rows (~834 KB per call) even though it is a recommended first call for agents. It now returns manifest counts plus a bounded `rows_preview` (default 10 rows, ~18 KB total) with `rows_omitted` and a note; pass `include_manifest_rows=true` for the full list. The smoke test asserts the default response stays under 64 KB.
- **Safe-defaults audit is generalized.** `scripts\test_petrel_mcp_server.py` now scans every registered tool: risky boolean flags (`launch`, `execute`, `writable`, `wait`, `apply`, `keep_patch`, `open_project_writable`) must default to `false`, and every tool whose policy sets `petrel_process_expected=true` must have a launch/execute gate, required inputs, or an explicit WARNING in its description. This forced WARNING text onto `petrel_export_well_logs_ui` and `petrel_export_well_tops_ui`, whose bare calls attempt a live GUI run.
- **Failure-policy coverage is complete and enforced.** `petrel_agent_readiness` was the one tool silently falling back to the default policy; it now has an explicit entry, and the smoke test asserts exact two-way coverage between the tool registry and `mcp\petrel_mcp_failure_policies.json`.
- **Smoke-test patch fixtures are vendored.** The two patch-report JSONs the smoke test audits now live in `tests\fixtures\native_edit_experiments\` instead of hardcoded timestamped `build\` paths. The pass-audit assertions skip with an explicit message on a machine that lacks the on-disk snapshot evidence those reports reference.
- **`.mcp.json` is regenerable.** `scripts\setup_petrel_mcp.ps1` rewrites the project MCP config for the current checkout path; README no longer points at a machine-specific Codex runtime Python.

Resolved later the same day: the full surface was committed as `7da35f0` ("Petrel no-Ocean MCP v0.7.0: agent-surface hardening, safe defaults, portable setup", 162 files) via a delegated Codex CLI session, verified clean of `build/`/corpora/`.pet`/`.ptd` paths.

Still open:

- **No git remote is configured.** The history now exists locally (`8a4943c` → `7da35f0`), but everything still lives on this one machine. Add a private remote and push before treating the project as shareable.
- ~~A fresh clone cannot run the full smoke test green~~ — resolved later on 2026-07-08: the smoke test now degrades gracefully on a fresh clone. `petrel_status` falls back to the synthetic mini package under `tests\fixtures\export_package_mini\` when the real export package is absent, and the machine-local evidence blocks (native-store analyzers needing `Petrel_DemoData_project\`, workflow generation needing `agent-index\`, coverage validation needing the real manifest) print explicit `SKIP:` lines instead of failing. On this machine, with all evidence present, the test still runs every assertion with zero skips.

## Common Failure Modes

`python` not found:

- Use the repo venv path, not `python` from PATH.
- Run `scripts\doctor_petrel_mcp.ps1`.

Tesseract not found:

- GUI OCR tools should preflight fail before touching Petrel.
- Valid local path is `C:\Program Files\Tesseract-OCR\tesseract.exe`.

Claude sees no tools:

- Run `claude mcp list`.
- Use `/mcp` inside Claude Code.
- Approve the project `.mcp.json` if pending.
- On this machine, Claude Desktop also has a Microsoft Store config path:
  `C:\Users\Ahmed\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\claude_desktop_config.json`.

GUI tool clicks wrong place:

- Do not retry blindly.
- Check the workflow spec and trace.
- For Well Tops, valid `Input` is Explorer/Input with sibling tabs `Models`, `Results`, `Templates`, not `Processes > Input`.

Native analyzer returns blocked:

- This is expected for command cloning.
- Do not patch. Continue mapping side effects, storage blocks, GUID/tag behavior, object references, and recovery proof.

## Definition Of Done For Future Agent Changes

For documentation-only changes:

```text
paths updated
links correct
README/AGENTS/CLAUDE handover still points to current docs
```

For OKF/wiki changes:

```powershell
python scripts\validate_okf_bundle.py "vault\Petrel Knowledge Wiki"
```

For MCP changes:

```powershell
python -m py_compile mcp\petrel_mcp_server.py
python scripts\test_petrel_mcp_server.py
python scripts\test_petrel_mcp_client_configs.py
```

For PowerShell tool changes:

```powershell
$parseErrors = $null
[System.Management.Automation.PSParser]::Tokenize((Get-Content -LiteralPath "path\to\script.ps1" -Raw), [ref]$parseErrors) | Out-Null
if ($parseErrors) { $parseErrors | Format-List *; exit 1 }
```

For GUI workflow changes:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\invoke_petrel_deterministic_gui_workflow.ps1 -WorkflowId export_well_tops_ascii
python scripts\test_petrel_mcp_server.py
```

For native mutation changes:

```text
dry-run first
snapshot before
apply only on automation copy
run Petrel wrapper only when explicitly required
register and validate
restore
compare clean
write report
```

## Paste-Ready Prompt For Claude Code

```text
You are continuing D:\Computer\Code\Petrel_project. Use the local Petrel MCP server petrel-no-ocean-control and repo evidence, not memory. First call petrel_agent_readiness, petrel_status, petrel_tool_creation_hierarchy, and petrel_tool_failure_policy. Then read CLAUDE.md, AGENTS.md, and docs\AI_CODER_HANDOVER_2026-07-08.md. Do not launch Petrel or mutate .pet/.ptd files unless explicitly required and protected by dry-run, snapshot, validation, and restore evidence. Prefer zero-GUI Python/direct file tools first, saved Workflow Editor/native control second, deterministic GUI only as a named fail-closed workflow, and discovery-only when automation is not proven.
```

## Best Next Technical Milestones

1. Keep MCP/doctor/readiness checks green as the public demo surface.
2. Add better agent examples around `petrel_agent_readiness`, `petrel_export_well_tops_native_probe`, and `petrel_register_and_validate`.
3. Improve deterministic GUI workflows only as fixed micro-tools, not broad desktop driving.
4. Continue native command-clone mapping until the analyzers can safely move from `blocked` to a dry-run clone recipe.
5. Add more Petrel-authored donor commands for surfaces/maps, data tables, interpretation, and models/properties.
6. Keep OKF notes version-aware and use `petrel_generate_workflow_from_okf` for new workflow/tool drafts.
7. Optional remote-access gateway (evaluated 2026-07-09, not built): a thin FastMCP 2.x proxy (`https://gofastmcp.com`) can wrap the existing stdio server and re-expose it over Streamable HTTP so agents on another machine can drive the Petrel box remotely. If built, it must be a separate opt-in script with its own `requirements-remote.txt` (FastMCP pulls pydantic/httpx/authlib and more), never imported by the core server — the stdlib-only server contract stands. Minimum security: bearer-token auth and localhost/VPN-only binding, because the endpoint can trigger GUI automation. Migrating the core server itself to FastMCP was evaluated and rejected: pure churn, dependency risk, no new capability.
