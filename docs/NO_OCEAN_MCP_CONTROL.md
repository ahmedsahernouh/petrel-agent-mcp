# No-Ocean MCP Control Path

This project should not depend on an Ocean developer license. The immediate automation route is a local MCP server that wraps the tested Petrel command-line, Workflow Editor, manifest, validation, knowledge-index, and native-workflow mapping scripts.

## What The MCP Server Does

Server:

```text
D:\Computer\Code\Petrel_project\mcp\petrel_mcp_server.py
```

New MCP/CLI tools follow the project tool-creation hierarchy:

```text
D:\Computer\Code\Petrel_project\docs\PETREL_TOOL_CREATION_HIERARCHY.md
D:\Computer\Code\Petrel_project\docs\MCP_FAILURE_POLICY.md
D:\Computer\Code\Petrel_project\mcp\petrel_tool_creation_hierarchy.json
D:\Computer\Code\Petrel_project\mcp\petrel_mcp_failure_policies.json
```

The order is:

```text
1. Zero-GUI Python/direct file processing
2. Zero-GUI Petrel Workflow Editor native control
3. Reusable deterministic GUI workflow
4. Discovery or donor capture only
```

It exposes these tools:

- `petrel_agent_readiness` - return the agent-facing readiness contract: stable/beta/experimental tool registry, dependency preflight rules, client config paths, known boundaries, and recommended first tool sequence.
- `petrel_tool_creation_hierarchy` - return the required hierarchy for creating new Petrel MCP/CLI tools: zero-GUI Python, zero-GUI Workflow Editor/native control, deterministic GUI fallback, or discovery-only donor capture.
- `petrel_tool_failure_policy` - return the fail-closed evidence, failure scenarios, retry policy, and fallback chain for one tool or all registered tools. Every MCP tool response also includes an `mcp_failure_policy` summary and an `mcp_result_audit` per-run enforcement summary.
- All tools expose `petrel_version`, `version_scope`, and `target_versions`. The default is `2018.2.0.5333` with the scope `Petrel 2018.2 local help with Petrel 2010 demo-project automation copy`. Do not treat a workflow or export package as compatible with another Petrel version until it is rerun or revalidated for that version.
- `petrel_status` - summarize latest run status, manifest rows, and file counts.
- `petrel_prepare_mvp` - regenerate the KB-derived export plan, workflow JSON, MCP tool spec, and Petrel Workflow Editor build sheet without launching Petrel.
- `petrel_run_mvp` - run the existing `ExportPiloX` workflow wrapper; use `dry_run` or `validate_only` when Petrel should not launch.
- `petrel_open_project` - prepare or launch Petrel for UI workflow editing; dry-run/read-only by default.
- `petrel_export_native_zero_gui` - copy and index the full `.pet/.ptd` native project store without launching Petrel or using GUI, then register and validate it.
- `petrel_run_zero_gui_export_mvp` - run the complete zero-GUI MVP: build KB artifacts, copy/index the native store, extract semantic native metadata, and validate.
- `petrel_export_native_semantic_zero_gui` - extract semantic metadata from copied native stores without Petrel: SMD faults/horizons/zones/frameworks, GMS property metadata, SQLite schema/values, XML/BXML metadata, and ZGY inventory.
- `petrel_export_well_tables_zero_gui` - derive well headers, LAS curve inventory, and conservative well-top/top-reference rows from the current package without launching Petrel, then register and validate.
- `petrel_export_surfaces_zero_gui` - decode native `.zhz` surface arrays to XYZ CSV and ZMAP+ with mask-gated layout validation and SEG-Y-derived georeferencing, then register and validate.
- `petrel_export_seismic_zgy_zero_gui` - read native ZGY cubes with pyzgy: per-cube geometry/statistics reports, mid-slice `.npy` exports, optional full-volume `.npy`, then register and validate.
- `petrel_survey_geometry` - read-only seismic survey geometry report (origin, inline/xline vectors, rotation, bin size, CRS sidecar) from a Petrel-authored SEG-Y export.
- `petrel_grid_convert` - convert gridded surface files between ZMAP+ and XYZ CSV in the project's zmapio dialect as part of the extract-process-import chain.
- `petrel_project_audit_report` - generate a self-contained HTML + JSON audit of the whole project from export-package evidence (wells/logs, well tops, decoded surfaces, ZGY seismic, native-store semantics, manifest breakdown, QC flags) without launching Petrel; sections degrade to explicit not-available notes when evidence is missing, then register and validate.
- `petrel_export_well_tops_native_probe` - probe native/package files for clean well-top evidence and source-ASCII fallback rows without launching Petrel.
- `petrel_import_gui_well_tops_table` - import a pasted Petrel GUI Well Tops table as a validation artifact, compare it to the source-ASCII fallback, then register and validate without launching Petrel.
- Petrel-authored Well Tops ASCII exports can be parsed after save with `scripts\import_petrel_well_tops_ascii_export.py`, then registered and validated with the normal MCP/package validation path.
- `petrel_export_well_logs_ui` - fallback/discovery tool for the mapped UI LAS export path.
- `petrel_run_deterministic_gui_workflow` - run a named declarative GUI fallback workflow such as `export_well_tops_ascii`; dry-run by default and requires `execute: true` before Petrel can launch.
- `petrel_register_and_validate` - register workflow artifacts and Petrel-written files, then validate and checksum the export package.
- `petrel_native_map_workflow` - map BXML/LZ4/native workflow regions.
- `petrel_native_snapshot` - create a timestamped `.pet/Model.ptd/Data.ptd` snapshot with hashes.
- `petrel_native_compare_snapshots` - compare before/after snapshots, emit diff ranges/previews, and map after `Data.ptd` against before.
- `petrel_native_patch_string` - dry-run or apply same-length string patches; dry-run is default.
- `petrel_native_patch_offset` - dry-run or apply exact-offset patches; dry-run is default.
- `petrel_export_segy_filename_patch` - patch the saved `ExportSeismicCmd` SEG-Y filename tail, run `ExportPiloX`, register/validate, and restore the patch.
- `petrel_export_segy_token_patch` - patch a same-length token inside a saved `ExportSeismicCmd` payload by exact offset, run `ExportPiloX`, register/validate, and restore the patch.
- `petrel_analyze_exportseismiccmd_records` - read-only map of saved `ExportSeismicCmd` records, BXML/LZ4 envelopes, and nearby output-token candidates.
- `petrel_analyze_workflow_command_clone_readiness` - read-only promotion gate for zero-GUI command cloning; it combines donor diffs, live command records, and patch-run-restore proof, and can pass MCP audit while still returning `clone_safe=false`.
- `petrel_analyze_workflow_clone_side_effects` - read-only analyzer that classifies donor-diff side effects into command payload, neighbor record, store/index churn, Model.ptd UI/object churn, and required actions before any clone patcher is allowed.
- `petrel_analyze_workflow_clone_storage_blocks` - read-only analyzer that splits mixed command payload bytes from Data.ptd store-growth blocks and reports the remaining blocker classes before any clone patcher is allowed.
- `petrel_extract_workflow_command_clone_recipe` - read-only extractor that saves candidate command payload binaries from Petrel-authored donor diffs, writes clone recipe gates plus payload-mutation, side-effect, payload-signal, and negative-control refusal evidence, and can pass MCP audit while still returning `recipe_safe_to_apply=false`.
- `petrel_export_systemcmd_token_patch` - patch a same-length token inside the saved `SystemCmd` bridge payload by exact offset, run `ExportPiloX`, verify the changed bridge proof, and restore the patch.
- `petrel_analyze_systemcmd_records` - read-only map of saved `SystemCmd` records, BXML/LZ4 envelopes, and nearby command/argument token candidates.
- `petrel_generate_workflow_from_okf` - generate a version-aware Workflow Editor workflow scaffold from OKF/wiki retrieval evidence; optional draft writing stays under the wiki vault.
- `petrel_validate_workflow_coverage` - validate manifest coverage by expected object type, required universal format, validation status, and Petrel version.
- `petrel_query_kb` - query the local Petrel knowledge index with version/review/confidence terms before planning an automation action.

Native workflow tools are audited fail-closed. Read-only tools must produce map/snapshot/compare/analyzer evidence. Low-level same-length patch tools are considered complete only for dry-run checks; a raw applied patch is not complete until runtime validation is provided. Use the SEG-Y and SystemCmd patch-run-restore wrappers when the required proof is patch, Petrel execution, validation, and clean restoration.

## Smoke Test

This does not launch Petrel:

```powershell
cd "D:\Computer\Code\Petrel_project"
python .\scripts\test_petrel_mcp_server.py
```

Expected result:

```text
Petrel MCP smoke test passed
```

Validate the registered Codex, VS Code, OpenCode, and Claude client config entries:

```powershell
cd "D:\Computer\Code\Petrel_project"
python .\scripts\test_petrel_mcp_client_configs.py
```

Run the MCP doctor for a single readiness report:

```powershell
cd "D:\Computer\Code\Petrel_project"
.\scripts\doctor_petrel_mcp.ps1
```

The doctor checks Python, Tesseract, the MCP server file, Codex/VS Code/OpenCode/Claude config files, both normal and Microsoft Store Claude config locations, and the MCP smoke tests. It writes a JSON report under `build\mcp_doctor`.

## Runtime Dependency Contract

The MCP server itself (`mcp\petrel_mcp_server.py`) is pure Python standard library: it imports nothing outside stdlib, so any Python 3.10+ interpreter can run it with no `pip install` step (validated on Python 3.11 via the repo `.venv`). The `.venv` and the requirements files matter only for child tools the server shells out to, not for the server process: `requirements-conversion.txt` (Docling/corpus parsing), `requirements-ocr.txt`, and `requirements-geodata.txt` (numpy/zmapio/pyzgy for the surface, grid-convert, and ZGY exporters).

The MCP server must be launched by a real Python interpreter. Use an absolute `python.exe` in client configs whenever possible, because desktop clients such as Claude may not inherit the same `PATH` as an interactive PowerShell session.

MCP tools that run Python helpers now resolve Python in this order:

```text
python_path tool argument -> PETREL_MCP_PYTHON -> PYTHON -> MCP server sys.executable -> repo .venv -> PATH python/py
```

If `python_path` is supplied, it is authoritative: a bad explicit path fails preflight instead of falling back silently.

A remote-access option was evaluated on 2026-07-09 and noted for the roadmap, not built: a FastMCP 2.x proxy can wrap this stdio server unchanged and re-expose it over Streamable HTTP for agents running on a different machine than Petrel. If ever built, it lives in its own opt-in script plus `requirements-remote.txt` and must never be imported by `mcp\petrel_mcp_server.py`; the server stays pure stdlib. Any such gateway needs bearer-token auth and localhost/VPN-only binding because the tool surface can launch GUI automation. Rewriting the server itself on FastMCP was rejected.

Semantic GUI tools that locate rows by OCR resolve Tesseract in this order:

```text
tesseract_path tool argument -> PETREL_TESSERACT_PATH -> TESSERACT_PATH -> default Program Files install -> PATH tesseract
```

Execution-mode GUI tools fail before touching Petrel when a required dependency is missing. The MCP result uses:

```json
{
  "status": "preflight_failed",
  "petrel_not_touched": true
}
```

## Client Configuration

Use stdio transport with an absolute Python path:

```json
{
  "mcpServers": {
    "petrel-no-ocean-control": {
      "command": "D:\\Computer\\Code\\Petrel_project\\.venv\\Scripts\\python.exe",
      "args": [
        "D:\\Computer\\Code\\Petrel_project\\mcp\\petrel_mcp_server.py"
      ],
      "cwd": "D:\\Computer\\Code\\Petrel_project"
    }
  }
}
```

If the target machine does not use the repo virtual environment, point `command` to that machine's known Python executable:

```json
{
  "mcpServers": {
    "petrel-no-ocean-control": {
      "command": "C:\\Path\\To\\python.exe",
      "args": [
        "D:\\Computer\\Code\\Petrel_project\\mcp\\petrel_mcp_server.py"
      ],
      "cwd": "D:\\Computer\\Code\\Petrel_project"
    }
  }
}
```

## Control Boundary

This server gives an LLM controlled access to the parts that are proven now:

1. Build export plans from the local Petrel KB.
2. Run the current Petrel Workflow Editor bridge.
3. Pass paths into the workflow with `-sparm`.
4. Register files Petrel writes into the package folders.
5. Validate and checksum package contents.
6. Map native `.ptd` workflow regions.
7. Snapshot and compare before/after native workflow stores.
8. Dry-run guarded same-length binary edits.
9. Export the full native `.pet/.ptd` project store without GUI or Petrel launch.
10. Extract safe semantic metadata from copied native stores without GUI, Petrel launch, or Ocean.
11. Run the saved `ExportPiloX` Workflow Editor SEG-Y donor from outside Petrel and validate the generated file.
12. Mutate the saved SEG-Y donor filename tail through a guarded same-length `Data.ptd` patch, run it externally, validate the generated file, then restore the patch.
13. Derive well headers, LAS curve inventory, and conservative well-top/top-reference CSVs from already exported LAS/native-store metadata without launching Petrel.
14. Mutate the saved `SystemCmd` bridge argument through a guarded same-length `Data.ptd` patch, run Petrel externally, verify the changed bridge JSON/probe, validate, then restore the patch.
15. Describe and run deterministic GUI fallback workflows from `petrel_gui_workflows\*.json` when a confirmed Petrel export cannot yet be produced through zero-GUI native decoding or a saved Workflow Editor command.
16. Classify command-clone donor side effects into Data.ptd payload/index/churn and Model.ptd UI/object-reference groups before any clone patcher is allowed.

It does not solve these yet:

- Universal-format decoding of proprietary Petrel native stores.
- Workflow step insertion or new workflow creation from binary records.
- Petrel-generated LAS/SEG-Y/ZMAP/RESQML exports for every object class without adding Petrel-side operations or decoding native layouts. LAS logs are exported through a UI-discovered fallback, SEG-Y donors are proven, LAS-derived well tables are now zero-GUI, and a Petrel-authored 84-row Well Tops ASCII table is parsed after save. Full binary well-top marker pick-depth decoding and generalized command insertion are not proven.

## Deterministic GUI Fallback Workflows

The deterministic GUI layer is defined by JSON specs under:

```text
D:\Computer\Code\Petrel_project\petrel_gui_workflows
```

Current first spec:

```text
petrel_gui_workflows\export_well_tops_ascii.json
```

Dry-run locally:

```powershell
.\scripts\invoke_petrel_deterministic_gui_workflow.ps1 -WorkflowId export_well_tops_ascii
```

MCP dry-run:

```json
{
  "workflow_id": "export_well_tops_ascii"
}
```

MCP execution requires:

```json
{
  "workflow_id": "export_well_tops_ascii",
  "execute": true,
  "coordinate_fallback": true,
  "license_dialog_timeout_seconds": 3,
  "stable_file_ticks": 1,
  "file_poll_seconds": 1
}
```

The runner must prove the exported ASCII file exists, parse it with `import_petrel_well_tops_ascii_export.py`, register generated artifacts, and validate the package. If any anchor, dialog, file, parse, or validation condition fails, the workflow fails closed and writes a report under `07_workflows_reports\automation_runs`.

Latest verified execution:

```text
MCP result audit: passed
Runner report: 07_workflows_reports\automation_runs\deterministic_gui_export_well_tops_ascii_20260706_053532.json
Raw ASCII: 02_wells\well_tops\well_tops_exportpilot_detgui_20260706_053532.txt
CRS sidecar: 02_wells\well_tops\well_tops_exportpilot_detgui_20260706_053532.txt.crsmeta.xml
Rows parsed: 84
GUI comparison: matched=84
Validation: passed, rows=750, failed=0
Audit gates: process_exit_zero, execution_requested, runner_report_loaded, runner_report_status_passed, ui_driver_exit_zero, raw_petrel_ascii_exists_nonempty, ascii_import_rows_gt_zero, manifest_validation_passed, postconditions_passed
Fast path: license-dialog wait reduced to 3 seconds and duplicate UI-driver register/validate skipped
```

Boundary: this is now an MCP/CLI-controlled deterministic GUI fallback, not zero-GUI native decoding and not zero-GUI workflow-command insertion.

## Zero-GUI Native Export

Run without Petrel launch:

```powershell
cd "D:\Computer\Code\Petrel_project"
.\scripts\run_petrel_zero_gui_export_mvp.ps1
```

Latest verified package state:

```text
Export package: D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609
Native files: 681
Copied bytes: 943518543
Native object candidates: 1746
Semantic extraction: 92 faults, 9 horizons, 11 zones, 4 structural frameworks, 193 GMS property files, 70 SQLite schema rows, 116 XML/BXML metadata files, 2 ZGY native files
Manifest rows after final full validation: 735
Validation: passed
```

Evidence:

```text
07_workflows_reports\native_zero_gui_export\zero_gui_native_export_20260703_064819.json
07_workflows_reports\native_semantic_export\zero_gui_native_semantic_export_20260703_064917.json
07_workflows_reports\validation_reports\export_validation_20260703_001422.md
00_manifest\native_store_inventory.csv
00_manifest\native_object_candidates.csv
05_interpretation\faults\native_fault_models.csv
05_interpretation\horizons\native_horizon_models.csv
06_models_properties\structural_models\native_gms_property_files.csv
03_seismic\seismic_metadata\native_zgy_inventory.csv
```

## Zero-GUI Well Tables

Run without Petrel launch:

```powershell
cd "D:\Computer\Code\Petrel_project"
.\scripts\export_petrel_well_tables_zero_gui.ps1
```

MCP tool:

```text
petrel_export_well_tables_zero_gui
```

Latest verified package state after the MCP call:

```text
Report: 07_workflows_reports\zero_gui_well_exports\well_tables_zero_gui_20260703_140507.json
Well headers: 02_wells\well_headers\las_well_headers.csv
LAS curve inventory: 02_wells\well_headers\las_curve_inventory.csv
Well top references: 02_wells\well_tops\well_tops_from_zero_gui_sources.csv
LAS files: 18
Well header rows: 18
Curve inventory rows: 259
Well top reference rows: 23
Actual well top pick rows: 0
Top decode statuses: 2 LAS zone-log values, 21 native XML references without pick-depth decoding
Manifest rows after final full validation: 735
Validation: passed
```

Boundary: this pass is zero-GUI and useful for inspection, but it is not itself a Petrel-authored well-top export. The current rows are LAS top-link values and native XML marker references; binary marker pick-depth records still need decoding or a mapped Petrel export command.

Additional native binary/source-ASCII well-top probe refreshed on 2026-07-04:

```text
MCP tool: petrel_export_well_tops_native_probe
CSV: 02_wells\well_tops\well_tops_native_binary_probe.csv
Source ASCII table: 02_wells\well_tops\well_tops_from_source_ascii.csv
Decode attempt table: 02_wells\well_tops\well_tops_native_decode_attempt.csv
Report: 07_workflows_reports\zero_gui_well_exports\well_tops_native_probe_20260704_133652.json
Native top order candidate: T_Tarbert [Converted], T_Ness, T_Etive, Seabed, BCU
LAS zone-log candidate rows: 2
Source ASCII pick rows: 98
Actual confirmed native-binary marker pick rows: 0
Manual GUI validation rows: 84
GUI/source comparison: matched=73; matched_with_numeric_differences=7; missing_in_gui_paste=18; missing_in_source_ascii=4
Manifest rows after validation: 735
Validation: passed
```

The probe CSV is now cleaned to canonical evidence rows only; it no longer exposes raw binary-adjacent symbols. The 98-row table is parsed from a local Petrel Well Tops ASCII source file and remains labeled `native_binary_confirmed=no` until the native BXML/Points payload is mapped. The manual GUI paste is now captured as `02_wells\well_tops\well_tops_from_petrel_gui_paste.csv`, with `02_wells\well_tops\well_tops_gui_vs_source_ascii_compare.csv` highlighting the B1 gap and C6 deltas.

Boundary: the native probe proves the top-name strings and LAS zone-log links are present in the project binary/export package. It still does not decode Petrel's marker-pick depth payload into confirmed `well_name, top_name, depth` rows.

Petrel-authored Well Tops ASCII export parsed after manual save:

```text
Raw export: 02_wells\well_tops\well_tops_petrel_ascii_manual01.txt
CRS sidecar: 02_wells\well_tops\well_tops_petrel_ascii_manual01.txt.crsmeta.xml
Parsed CSV: 02_wells\well_tops\well_tops_from_petrel_ascii_export.csv
GUI compare: 02_wells\well_tops\well_tops_petrel_ascii_export_vs_gui_compare.csv
Source compare: 02_wells\well_tops\well_tops_petrel_ascii_export_vs_source_ascii_compare.csv
Report: 07_workflows_reports\zero_gui_well_exports\well_tops_petrel_ascii_export_20260705_081214.json
Rows: 84
GUI comparison: matched=84
Source comparison: matched=73; matched_with_numeric_differences=7; missing_in_petrel_ascii_export=18; missing_in_source_ascii=4
CRS: ED50-UTM31 / EPSG,23031
Manifest rows after validation: 740
Validation: passed
```

Boundary: this confirms actual Petrel-exported marker-pick rows in universal text form. It was saved once through the Petrel UI, then parsed, registered, and validated outside Petrel. It is not yet zero-GUI command creation or native binary marker-pick decoding.

## Saved Workflow SEG-Y Donor

Run through Petrel's command-line workflow wrapper:

```powershell
cd "D:\Computer\Code\Petrel_project"
.\scripts\run_petrel_full_export_mvp.ps1
```

Latest verified SEG-Y state:

```text
Workflow: ExportPiloX
Command donor: Export SEGY seismic
Object: Orig Amp
Latest Petrel-authored second donor output: 03_seismic\segy\orig_amp_exportpilot_sgy2.sgy
Latest MCP-controlled patch output: 03_seismic\segy\orig_amp_exportpilot_mcp01.sgy
Latest MCP-controlled second-command token output: 03_seismic\segy\orig_amp_exportpilot_sgy3.sgy
Bytes: 129584100
Status JSON: 07_workflows_reports\automation_runs\petrel_automation_20260704_100733.json
Validation report: 07_workflows_reports\validation_reports\export_validation_20260704_100838.md
Manifest rows after final full validation: 735
Validation: passed
```

Petrel-authored System command bridge proof:

```text
Command: powershell.exe -NoProfile -ExecutionPolicy Bypass -File "D:\Computer\Code\Petrel_project\scripts\petrel_export_mvp_bridge.ps1" -StepName "post_export_register_validate"
Bridge status: D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\automation_runs\petrel_export_mvp_bridge_20260704_092550.json
Probe file: 07_workflows_reports\exported_reports\external_workflow_bridge_probe.csv
Native diff: D:\Computer\Code\Petrel_project\build\native_edit_experiments\native_workflow_snapshot_compare_20260704_092053\snapshot_compare_report.json
SystemCmd offset: Data.ptd 173184881
powershell.exe offset: Data.ptd 173185435
Petrel log: Executing System command .... (100%); Status: Workflow run OK
```

SystemCmd record analyzer and patch proof:

```text
Tool: petrel_analyze_systemcmd_records
Analyzer report: D:\Computer\Code\Petrel_project\build\native_edit_experiments\systemcmd_record_map_20260704_100011\systemcmd_record_map.json
Record count: 1
SystemCmd offset: Data.ptd 173184881
StepName offset: Data.ptd 173185525
post offset: Data.ptd 173185535
register_validate offset: Data.ptd 173185543
```

MCP-controlled SystemCmd patch-run-restore proof:

```text
Tool: petrel_export_systemcmd_token_patch
Patch: Data.ptd post -> p0st at offset 173185535
Target bridge step: p0st_export_register_validate
Report: D:\Computer\Code\Petrel_project\build\native_edit_experiments\systemcmd_token_patch_export_20260704_100224\systemcmd_token_patch_export_report.json
Petrel status: D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\automation_runs\petrel_automation_20260704_100230.json
Bridge status: D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\automation_runs\petrel_export_mvp_bridge_20260704_100312.json
Bridge step_name: p0st_export_register_validate
Validation: 735 rows, 0 failed
Restore compare: D:\Computer\Code\Petrel_project\build\native_edit_experiments\native_workflow_snapshot_compare_20260704_100330\snapshot_compare_report.json
Restore compare clean: true
```

Restored-state rerun after the MCP proof:

```text
Outer status: D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\automation_runs\petrel_automation_20260704_100733.json
Bridge status: D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\automation_runs\petrel_export_mvp_bridge_20260704_100822.json
Bridge step_name: post_export_register_validate
Validation: D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\validation_reports\export_validation_20260704_100838.json
```

Native binary donor evidence:

```text
Snapshot compare: D:\Computer\Code\Petrel_project\build\native_edit_experiments\native_workflow_snapshot_compare_20260703_012602\snapshot_compare_report.json
Data.ptd BXML chunk: 1293
LZ4 before command: 173200294
BXML command start: 173200309
Next BXML: 173201087
Command type guess: SimpleCmd;SheetSaveCmd;ExportSeismicCmd
```

Second Petrel-authored donor diff:

```text
Before snapshot: D:\Computer\Code\Petrel_project\build\native_edit_experiments\native_workflow_snapshot_20260703_031623_before_zgy_or_format_donor_diff
After snapshot: D:\Computer\Code\Petrel_project\build\native_edit_experiments\native_workflow_snapshot_20260703_054150_after_second_segy_command_donor_diff
Compare report: D:\Computer\Code\Petrel_project\build\native_edit_experiments\native_workflow_snapshot_compare_20260703_054200\snapshot_compare_report.json
Data.ptd ExportSeismicCmd string offsets: 173184998, 173200515
Visible second-output token: sgy2 at Data.ptd offset 173185552
Output: 03_seismic\segy\orig_amp_exportpilot_sgy2.sgy
```

Zero-GUI parameter mutation evidence:

```text
Patch: Data.ptd _donor.sgy -> _zgui1.sgy at offset 173201036
Patch report: D:\Computer\Code\Petrel_project\build\native_edit_experiments\native_workflow_string_patch_20260703_023521\native_workflow_string_patch_report.json
Patched run: 07_workflows_reports\automation_runs\petrel_automation_20260703_023613.json
Patched output: 03_seismic\segy\orig_amp_exportpilot_zgui1.sgy
Patched validation: 07_workflows_reports\validation_reports\export_validation_20260703_023657.md
Restore report: D:\Computer\Code\Petrel_project\build\native_edit_experiments\native_workflow_string_patch_20260703_023757\native_workflow_string_patch_report.json
Restore compare: D:\Computer\Code\Petrel_project\build\native_edit_experiments\native_workflow_snapshot_compare_20260703_023823\snapshot_compare_summary.md
```

Repeatable MCP-controlled proof:

```text
Tool: petrel_export_segy_filename_patch
Script: scripts\invoke_petrel_segy_filename_patch_export.ps1
Patch: Data.ptd _donor.sgy -> _mcp01.sgy at offset 173201036
Report: D:\Computer\Code\Petrel_project\build\native_edit_experiments\segy_filename_patch_export_20260703_030410\segy_filename_patch_export_report.json
Patched output: 03_seismic\segy\orig_amp_exportpilot_mcp01.sgy
Validation report: 07_workflows_reports\validation_reports\export_validation_20260703_030503.md
Restore compare: D:\Computer\Code\Petrel_project\build\native_edit_experiments\native_workflow_snapshot_compare_20260703_030507\snapshot_compare_summary.md
Data.ptd restored hash: 802079019DD0F85B6C8EA5AC7E54960EC73EF06E9A27B50212573E5660C34BF2
```

Second-command MCP token patch proof:

```text
Tool: petrel_export_segy_token_patch
Patch: Data.ptd sgy2 -> sgy3 at offset 173185552
Report: D:\Computer\Code\Petrel_project\build\native_edit_experiments\segy_token_patch_export_20260703_055859\segy_token_patch_export_report.json
Patched output: 03_seismic\segy\orig_amp_exportpilot_sgy3.sgy
Validation report: 07_workflows_reports\validation_reports\export_validation_20260703_055955.md
Restore compare: D:\Computer\Code\Petrel_project\build\native_edit_experiments\native_workflow_snapshot_compare_20260703_055958\snapshot_compare_summary.md
```

Read-only command record analyzer proof:

```text
Tool: petrel_analyze_exportseismiccmd_records
Report: D:\Computer\Code\Petrel_project\build\native_edit_experiments\exportseismiccmd_record_map_20260703_060617\exportseismiccmd_record_map.json
Record count: 2
Record 0: command offset 173184998, BXML 173184792, previous LZ4 173184777
Record 1: command offset 173200515, BXML 173200309, previous LZ4 173200294
```

Read-only command-clone readiness gate:

```text
Tool: petrel_analyze_workflow_command_clone_readiness
Report: D:\Computer\Code\Petrel_project\build\native_edit_experiments\workflow_command_clone_readiness_20260706_060734\workflow_command_clone_readiness.json
Clone safe: false
Status: blocked
Blockers: 10
Passed: two records present, envelopes bounded, donor reports loaded, same-length parameter mutation proven
Blocked: non-uniform spans, broad donor diffs, unmapped command-list indexes, BXML/LZ4 length fields, GUID/tag behavior, object references, and negative-control recovery
```

Read-only command-clone recipe extractor:

```text
Tool: petrel_extract_workflow_command_clone_recipe
Report: D:\Computer\Code\Petrel_project\build\native_edit_experiments\workflow_command_clone_recipe_20260706_111557\workflow_command_clone_recipe.json
Recipe status: blocked
Safe to apply: false
Blockers: 8
Candidate payloads: 2
first_donor core length: 779
second_donor core length: 799
second_donor extended length: 4807
Mapped now: command body storage location, non-uniform payload lengths, LZ4 length candidates, BXML mutation candidates, command record order, Orig Amp payload signal, unique_tag payload signal, corrupt-LZ4 negative-control refusal
Still blocked: side-effect isolation, Model.ptd side effects, BXML semantics, command-list/index semantics, Model.ptd UI/object-reference semantics, object-reference binding semantics, GUID/tag generation rule, applied-clone recovery proof
```

Read-only side-effect isolation analyzer:

```text
Tool: petrel_analyze_workflow_clone_side_effects
Report: D:\Computer\Code\Petrel_project\build\native_edit_experiments\workflow_clone_side_effects_20260706_111542\workflow_clone_side_effects.json
Status: blocked
Side effects isolated: false
Clone patch precondition satisfied: false
Blockers: 4
Blocking groups: data_store_index_or_page_churn; mixed_command_payload_and_store_allocation_churn; model_store_header_churn; model_ui_object_reference_churn; required_neighbor_record_candidate
Required next actions: map Data.ptd command-list/index updates; split command payload from store growth; map Model.ptd header/root updates; map Model.ptd UI/object-reference updates; map neighbor-record semantics
```

Read-only storage block splitter:

```text
Tool: petrel_analyze_workflow_clone_storage_blocks
Report: D:\Computer\Code\Petrel_project\build\native_edit_experiments\workflow_clone_storage_blocks_20260706_111547\workflow_clone_storage_blocks.json
Status: blocked
Storage payload separated: true
Clone patch precondition satisfied: false
Blockers: 3
Segment classes: 16
Blocking segment classes: data_store_index_or_page_churn; model_store_header_churn; model_ui_object_reference_churn; neighbor_or_extended_record_overlap
Required next actions: map Data.ptd command-list/index updates; map Model.ptd header/root updates; map Model.ptd UI/object-reference updates; map neighbor-record semantics
```

Boundary: these are Petrel-authored donors that can be run from MCP/CLI after saving, and same-length filename/output/bridge-argument parameters can be patched without GUI. The patch-run-restore loop is now automated through MCP for the first command filename tail, the second command tokenized output suffix, and the saved `SystemCmd` bridge StepName argument. The `System command` donor proves a saved native workflow can call back into the external CLI automation layer during a workflow run. The storage-block splitter removes the mixed payload/store-growth blocker by separating command-core bytes from allocator-growth bytes, but command cloning is still blocked until neighbor records, Data.ptd index/list churn, and Model.ptd UI/object-reference semantics are mapped.

## Next Milestone Without Ocean

The next milestone is to turn the mapped recipe evidence into validated semantics before writing any command-clone patcher:

1. Reduce the two donor snapshot diffs to isolated command payload, command-list index, object-reference, UI metadata, and saved-path-token changes.
2. Validate the affected BXML/LZ4 mutation semantics for inserted payloads.
3. Prove the `unique_tag`/GUID behavior for cloned commands.
4. Run an applied clone/recovery proof on a disposable copy only after the dry-run refusal checks remain green.
5. Only then build a backed-up dry-run command-clone patcher against the disposable automation copy.
6. Validate any future clone with Petrel `-runWorkflow`, manifest registration, checksum validation, and clean restore before calling it successful.

That path keeps the project moving toward universal-format exports through MCP/tools without requiring Ocean. The zero-GUI native export already gives a complete raw project-store package plus decoded metadata for the native stores that are safely parseable. The next native binary milestone is for editable/insertable workflow commands and Petrel-generated universal-format exports, not for raw data preservation.
