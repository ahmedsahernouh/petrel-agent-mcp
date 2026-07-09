# Full Project Export MVP

This is the current prototype for the full Petrel project data export goal.

## What Is Working

The local knowledge base now drives a generated export MVP:

- `00_manifest/full_project_export_capability_matrix.csv`
- `00_manifest/full_project_export_plan.csv`
- `00_manifest/petrel_full_project_export.workflow.json`
- `07_workflows_reports/mvp_full_project_export/petrel_workflow_editor_build_sheet.md`
- `07_workflows_reports/mvp_full_project_export/mcp_tool_spec.petrel.workflow.export_project_universal_package.json`
- `07_workflows_reports/mvp_full_project_export/kb_evidence_used.csv`
- `mcp/petrel_mcp_server.py`
- `scripts/export_petrel_native_project_zero_gui.ps1`
- `scripts/export_petrel_native_semantic_zero_gui.ps1`
- `scripts/export_petrel_native_semantic_zero_gui.py`
- `scripts/run_petrel_zero_gui_export_mvp.ps1`
- `scripts/export_petrel_well_tables_zero_gui.ps1`
- `scripts/export_petrel_well_tables_zero_gui.py`
- `scripts/import_petrel_well_tops_ascii_export.py`
- `scripts/export_petrel_well_logs_ui.ps1`
- `scripts/invoke_petrel_segy_filename_patch_export.ps1`
- `scripts/invoke_petrel_segy_token_patch_export.ps1`
- `scripts/analyze_petrel_exportseismiccmd_records.py`
- `scripts/analyze_petrel_workflow_command_clone_readiness.py`
- `scripts/analyze_petrel_workflow_clone_side_effects.py`
- `scripts/analyze_petrel_workflow_clone_storage_blocks.py`
- `scripts/extract_petrel_workflow_command_clone_recipe.py`
- `scripts/invoke_petrel_systemcmd_token_patch_export.ps1`
- `scripts/analyze_petrel_systemcmd_records.py`

The generator is:

```powershell
.\scripts\build_petrel_full_export_mvp.ps1
```

The one-command MVP runner is:

```powershell
.\scripts\run_petrel_full_export_mvp.ps1
```

The strict zero-GUI runner is:

```powershell
.\scripts\run_petrel_zero_gui_export_mvp.ps1
```

The current workflow name is `ExportPiloX`. It was renamed from `ExportPilot` by the native `.ptd` edit milestone documented in `docs/PETREL_NATIVE_WORKFLOW_EDITING.md`. Follow-up native edits also proved that equal-length changes inside the `Data.ptd` Workflow Editor command payload can affect Petrel execution.

It runs this sequence:

1. Read the local Petrel KB export index.
2. Generate the full-project capability matrix.
3. Generate the export plan.
4. Generate the external workflow JSON spec.
5. Generate the Petrel Workflow Editor build sheet.
6. Run the current Petrel `ExportPiloX` workflow through `-runWorkflow`.
7. Register workflow artifacts and exported files.
8. Validate the package and update checksums.

The first strict no-GUI full-project export is now implemented as a raw native project-store package plus safe semantic metadata extraction:

```text
Petrel .pet/.ptd files -> 08_native_project -> native XML/SQLite/property metadata CSV/JSON -> manifest/checksum validation
```

This is controlled from outside Petrel by:

```powershell
.\scripts\export_petrel_native_project_zero_gui.ps1
.\scripts\export_petrel_native_semantic_zero_gui.ps1
.\scripts\run_petrel_zero_gui_export_mvp.ps1
```

And through MCP by:

```text
petrel_export_native_zero_gui
petrel_export_native_semantic_zero_gui
petrel_run_zero_gui_export_mvp
petrel_export_segy_filename_patch
petrel_export_segy_token_patch
petrel_analyze_exportseismiccmd_records
petrel_analyze_workflow_command_clone_readiness
petrel_analyze_workflow_clone_side_effects
petrel_analyze_workflow_clone_storage_blocks
petrel_extract_workflow_command_clone_recipe
petrel_export_systemcmd_token_patch
petrel_analyze_systemcmd_records
petrel_export_well_tables_zero_gui
```

The first real Petrel data export class is also proven through UI automation, but this remains a fallback/discovery path:

```text
Petrel Input/Wells -> Export all logs in folder -> LAS files
```

This is controlled from outside Petrel by:

```powershell
.\scripts\export_petrel_well_logs_ui.ps1
```

And through MCP by:

```text
petrel_export_well_logs_ui
```

The zero-GUI well table layer is now also implemented from the validated LAS/native-store package:

```text
LAS files -> 02_wells\well_headers\las_well_headers.csv
LAS files -> 02_wells\well_headers\las_curve_inventory.csv
LAS top-link curves + native XML marker references -> 02_wells\well_tops\well_tops_from_zero_gui_sources.csv
```

The well-top CSV is a reference inventory only. It is not an actual Petrel marker-pick table with confirmed `well_name`, `top_name`, and depth values.

This is controlled from outside Petrel by:

```powershell
.\scripts\export_petrel_well_tables_zero_gui.ps1
```

And through MCP by:

```text
petrel_export_well_tables_zero_gui
```

## Latest Verified Run

```text
Status file: D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\automation_runs\petrel_automation_20260704_092507.json
Petrel exit code: 0
Workflow execution: confirmed
Artifact registration: registered
File export registration: registered
Validation: passed
```

Current manifest rows:

- `workflow_report_cli_variable_probe`: proves CLI-to-Workflow-Editor variable passing.
- `external_workflow_bridge_probe`: proves the Petrel-authored `System command` in `ExportPiloX` can call the external MVP bridge script, write a probe file, register outputs, and validate the package from inside the workflow run.
- 18 `well_log` rows: real Petrel-generated LAS files exported through the mapped `Input/Wells` UI command and validated with checksums.
- 2 `well` rows: zero-GUI LAS-derived well headers and LAS curve inventory CSVs.
- 1 `well_top_reference` row: zero-GUI LAS top-link/native XML well-top reference CSV. It includes LAS top-link values and native references only, not actual Petrel marker pick-depth records.
- 1 `well_top_native_probe` row: clean zero-GUI native binary evidence CSV with canonical top/history strings and LAS zone-log candidates only.
- 1 `well_top_source_ascii` row: parsed local Petrel Well Tops ASCII source table with 98 real pick rows, labeled as source-derived rather than native-binary-decoded.
- 1 `well_top_native_decode_attempt` row: current decode-attempt table populated from the source ASCII fallback while native marker-pick payload decoding remains unconfirmed.
- 1 `well_top_gui_ground_truth` row: parsed manual Petrel GUI Well Tops table paste with 84 visible pick rows, used as validation target rather than native-binary-confirmed export.
- 1 `well_top_comparison_report` row: GUI-paste versus source-ASCII comparison report for well-top decoder targeting.
- 1 `well_top_petrel_ascii_export` row and 1 `well_top_crs_metadata` row: Petrel-authored Well Tops ASCII export plus CRS sidecar saved from the Petrel UI.
- 1 `well_top_petrel_ascii_export_parsed` row: parsed Petrel-authored Well Tops ASCII table with 84 actual marker-pick rows.
- 2 `well_top_petrel_ascii_export_comparison` rows: Petrel ASCII versus GUI-paste and Petrel ASCII versus source-ASCII comparison reports.
- 5 `seismic_cube` rows: one active donor SEG-Y file exported by the saved `Export SEGY seismic` Workflow Editor command, one second Petrel-authored SEG-Y command output, one manual zero-GUI filename-mutation proof file, one repeatable MCP-controlled first-command patch-run-restore proof file, and one MCP-controlled second-command token patch-run-restore proof file; all are validated with checksums.
- 681 `petrel_native_store` rows: zero-GUI copied `.pet/.ptd` native project-store files under `08_native_project`, validated with checksums.
- 2 `native_export_report` rows: zero-GUI native-store inventory and native object candidate CSVs.
- Semantic zero-GUI rows: `fault_metadata`, `horizon_metadata`, `zone_metadata`, `structural_framework_metadata`, `native_gms_property_metadata`, `seismic_metadata`, `sqlite_metadata`, `native_xml_metadata`, `project_metadata`, and run reports under `native_semantic_report`.

Latest real export validation:

```text
D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\validation_reports\export_validation_20260705_011307.md
Rows: 740
Validated: 740
Failed: 0
```

Latest Petrel-generated seismic files:

```text
D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\03_seismic\segy\orig_amp_exportpilot_donor.sgy
Bytes: 129584100
Validation row: 03_seismic\segy\orig_amp_exportpilot_donor.sgy [SEG-Y]

D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\03_seismic\segy\orig_amp_exportpilot_zgui1.sgy
Bytes: 129584100
Validation row: 03_seismic\segy\orig_amp_exportpilot_zgui1.sgy [SEG-Y]
Note: this second file was created by a restored zero-GUI Data.ptd filename-tail mutation.

D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\03_seismic\segy\orig_amp_exportpilot_mcp01.sgy
Bytes: 129584100
Validation row: 03_seismic\segy\orig_amp_exportpilot_mcp01.sgy [SEG-Y]
Note: this third file was created through the `petrel_export_segy_filename_patch` MCP tool, which patched, ran, registered, validated, and restored the native workflow store.

D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\03_seismic\segy\orig_amp_exportpilot_sgy2.sgy
Bytes: 129584100
SHA256: ae2a7501fae1954a1f59f1c34daf9209b0720e632a8c0a1878ed6e547a9f994d
Validation row: 03_seismic\segy\orig_amp_exportpilot_sgy2.sgy [SEG-Y]
Note: this fourth file was created by a second Petrel-authored `Export SEGY seismic` command and executed through the external wrapper.

D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\03_seismic\segy\orig_amp_exportpilot_sgy3.sgy
Bytes: 129584100
SHA256: a61503cfa6667fd13590dc19bb4b7a748cab4f680360787f86be519e6a927584
Validation row: 03_seismic\segy\orig_amp_exportpilot_sgy3.sgy [SEG-Y]
Note: this fifth file was created through `petrel_export_segy_token_patch`, which patched `sgy2` to `sgy3`, ran, registered, validated, and restored the native workflow store.
```

Zero-GUI native and semantic export evidence:

```text
D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\native_zero_gui_export\zero_gui_native_export_20260703_064819.json
D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\native_semantic_export\zero_gui_native_semantic_export_20260703_064917.json
runtime_gui_used: false
petrel_process_launched: false
copied_file_count: 681
copied_total_bytes: 943518543
candidate_count: 1746
fault_models: 92
horizon_models: 9
zone_models: 11
structural_frameworks: 4
gms_property_files: 193
sqlite_schema_rows: 70
xml_metadata_files: 116
zgy_files: 2
validation_status: passed
```

Zero-GUI well table export evidence:

```text
D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\zero_gui_well_exports\well_tables_zero_gui_20260703_140507.json
D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\02_wells\well_headers\las_well_headers.csv
D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\02_wells\well_headers\las_curve_inventory.csv
D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\02_wells\well_tops\well_tops_from_zero_gui_sources.csv
runtime_gui_used: false
petrel_process_launched: false
las_files: 18
well_header_rows: 18
curve_inventory_rows: 259
well_top_reference_rows: 23
actual_well_top_pick_rows: 0
well_top_export_status: actual_petrel_marker_pick_table_not_exported
las_top_link_rows: 2
well_top_decode_status_counts: las_zone_log_value_without_marker_name_mapping=2; native_xml_reference_only_no_pick_depth_decoded=21
```

Zero-GUI native well-top binary probe evidence:

```text
D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\02_wells\well_tops\well_tops_native_binary_probe.csv
D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\02_wells\well_tops\well_tops_from_source_ascii.csv
D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\02_wells\well_tops\well_tops_native_decode_attempt.csv
D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\02_wells\well_tops\well_tops_from_petrel_gui_paste.csv
D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\02_wells\well_tops\well_tops_gui_vs_source_ascii_compare.csv
D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\zero_gui_well_exports\well_tops_native_probe_20260704_133652.json
D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\zero_gui_well_exports\well_tops_gui_paste_compare_20260704_140044.json
runtime_gui_used: false
petrel_process_launched: false
native_top_order_candidate: T_Tarbert [Converted], T_Ness, T_Etive, Seabed, BCU
native_history_rows: 1
las_zone_log_candidate_rows: 2
source_ascii_pick_rows: 98
manual_gui_table_capture_used: true
gui_paste_rows: 84
gui_vs_source_status_counts: matched=73; matched_with_numeric_differences=7; missing_in_gui_paste=18; missing_in_source_ascii=4
actual_well_top_pick_rows_from_native_binary: 0
native_binary_marker_pick_rows: 0
manifest_source_types: well_top_native_probe, well_top_source_ascii, well_top_native_decode_attempt, well_top_gui_ground_truth, well_top_comparison_report
validation_report: export_validation_20260704_070049.md
manifest_rows_after_validation: 735
```

The native binary probe is now clean and no longer exposes raw binary-adjacent symbols in the CSV. The usable 98-row pick table is parsed from the local Petrel Well Tops ASCII source file and is explicitly labeled `native_binary_confirmed=no`. The manual Petrel GUI paste adds an 84-row ground-truth validation target: B1 has four GUI rows missing from the source-ASCII fallback, and C6 has seven matched rows with small X/depth deltas. The next native decoding task is still the BXML/Points marker-pick payload.

Petrel-authored Well Tops ASCII export evidence:

```text
D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\02_wells\well_tops\well_tops_petrel_ascii_manual01.txt
D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\02_wells\well_tops\well_tops_petrel_ascii_manual01.txt.crsmeta.xml
D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\02_wells\well_tops\well_tops_from_petrel_ascii_export.csv
D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\02_wells\well_tops\well_tops_petrel_ascii_export_vs_gui_compare.csv
D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\02_wells\well_tops\well_tops_petrel_ascii_export_vs_source_ascii_compare.csv
D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\zero_gui_well_exports\well_tops_petrel_ascii_export_20260705_081214.json
manual_petrel_export_used: true
runtime_gui_used_by_importer: false
petrel_process_launched_by_importer: false
petrel_ascii_rows: 84
petrel_ascii_vs_gui_status_counts: matched=84
petrel_ascii_vs_source_status_counts: matched=73; matched_with_numeric_differences=7; missing_in_petrel_ascii_export=18; missing_in_source_ascii=4
crs: ED50-UTM31 / EPSG,23031
validation_report: export_validation_20260705_011307.md
manifest_rows_after_validation: 740
```

This confirms the 84 visible GUI Well Tops rows are real Petrel-exported marker-pick rows in a universal text file. It still does not prove native binary marker-pick payload decoding or zero-GUI insertion of the Petrel well-top export command.

## Native Workflow Edit Milestones

The first external native `.ptd` edit succeeded:

- Store file: `Petrel2010 demo project ExportPilot.ptd\Model.ptd`
- Patch: `ExportPilot` -> `ExportPiloX`
- Offset: `849331`
- Petrel validation: `Workflow execution: confirmed`

Two stronger `Data.ptd` edits also succeeded:

- Command token patch: `export_package` -> `export_packagf` at offset `173166025`; Petrel executed the modified command payload and wrote altered output rows. The patch was restored.
- Output path fragment patch: `csv` -> `tsv` at offset `173166325`; Petrel wrote `cli_variable_probe.tsv` through the modified Workflow Editor output command. The patch was restored.

A Petrel-authored Workflow Editor command donor also succeeded:

- Command: `Export SEGY seismic`
- Object: `Orig Amp`
- Output: `03_seismic\segy\orig_amp_exportpilot_donor.sgy`
- Petrel run mode: saved once through the GUI, then executed through `.\scripts\run_petrel_full_export_mvp.ps1`
- Binary signal: `Data.ptd` BXML chunk `1293`, command type guess `SimpleCmd;SheetSaveCmd;ExportSeismicCmd`, BXML offset `173200309`
- Status: validated SEG-Y file in the manifest

A second Petrel-authored donor command also succeeded:

- Command: `Export SEGY seismic`
- Object: `Orig Amp`
- Output: `03_seismic\segy\orig_amp_exportpilot_sgy2.sgy`
- Petrel run mode: saved through the GUI, then executed through `.\scripts\run_petrel_full_export_mvp.ps1`
- Binary signals: two `ExportSeismicCmd` records in `Data.ptd` at string offsets `173184998` and `173200515`
- Diff report: `native_workflow_snapshot_compare_20260703_054200`
- Status: validated SEG-Y file in the manifest; latest validation has 723 rows, 0 failed

A zero-GUI `ExportSeismicCmd` parameter mutation also succeeded:

- Store: `Data.ptd`
- Patch: `_donor.sgy` -> `_zgui1.sgy`
- Offset: `173201036`
- Scope: `Data.ptd` only; `Model.ptd` unchanged
- Diff: same file length, one `Data.ptd` diff range
- Petrel result: external workflow run wrote `orig_amp_exportpilot_zgui1.sgy`
- Current state: patch restored; active workflow writes `orig_amp_exportpilot_donor.sgy`

The same operation is now repeatable through a guarded MCP tool:

- Tool: `petrel_export_segy_filename_patch`
- Script: `scripts\invoke_petrel_segy_filename_patch_export.ps1`
- Proved patch: `_donor.sgy` -> `_mcp01.sgy`
- Petrel result: external workflow run wrote `orig_amp_exportpilot_mcp01.sgy`
- Validation: 722 rows validated, 0 failed
- Restore compare: `native_workflow_snapshot_compare_20260703_030507`, zero diff ranges in `Model.ptd` and `Data.ptd`

The second saved command can now be controlled through a guarded MCP token patch tool:

- Tool: `petrel_export_segy_token_patch`
- Script: `scripts\invoke_petrel_segy_token_patch_export.ps1`
- Proved patch: `sgy2` -> `sgy3`
- Offset: `173185552`
- Petrel result: external workflow run wrote `orig_amp_exportpilot_sgy3.sgy`
- Validation: 724 rows validated, 0 failed
- Restore compare: `native_workflow_snapshot_compare_20260703_055958`, zero diff ranges in `Model.ptd` and `Data.ptd`

The current saved `ExportSeismicCmd` records can also be mapped through MCP without modifying Petrel files:

- Tool: `petrel_analyze_exportseismiccmd_records`
- Script: `scripts\analyze_petrel_exportseismiccmd_records.py`
- Latest report: `exportseismiccmd_record_map_20260703_060617`
- Record count: 2
- Record offsets: `173184998`, `173200515`

See:

```text
D:\Computer\Code\Petrel_project\docs\PETREL_NATIVE_WORKFLOW_EDITING.md
```

## Workflow Bridge

The CLI runner sets these environment variables before launching Petrel:

```text
PETREL_EXPORT_PACKAGE
PETREL_INVENTORY_PACKAGE
PETREL_EXPORT_MANIFEST
```

The generated Workflow Editor build sheet includes this target final `System command` step:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "D:\Computer\Code\Petrel_project\scripts\petrel_export_mvp_bridge.ps1" -StepName "post_export_register_validate"
```

That step is now saved in the native `ExportPiloX` workflow as a Petrel-authored `System command` donor. The before/after native diff is:

```text
D:\Computer\Code\Petrel_project\build\native_edit_experiments\native_workflow_snapshot_compare_20260704_092053\snapshot_compare_report.json
```

The current native map shows:

```text
Data.ptd SystemCmd offset: 173184881
Data.ptd powershell.exe offset: 173185435
Data.ptd StepName offset: 173185525
Data.ptd post offset: 173185535
Data.ptd register_validate offset: 173185543
```

External run proof:

```text
Outer status: D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\automation_runs\petrel_automation_20260704_092507.json
Bridge status: D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\automation_runs\petrel_export_mvp_bridge_20260704_092550.json
Probe file: D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\exported_reports\external_workflow_bridge_probe.csv
Validation report: D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\validation_reports\export_validation_20260704_092609.md
Petrel log: Executing System command .... (100%); Status: Workflow run OK
```

MCP-controlled bridge patch proof:

```text
Tool: petrel_export_systemcmd_token_patch
Patch: Data.ptd post -> p0st at offset 173185535
Target bridge step: p0st_export_register_validate
Report: D:\Computer\Code\Petrel_project\build\native_edit_experiments\systemcmd_token_patch_export_20260704_100224\systemcmd_token_patch_export_report.json
Outer status: D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\automation_runs\petrel_automation_20260704_100230.json
Bridge status: D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\automation_runs\petrel_export_mvp_bridge_20260704_100312.json
Validation: 735 rows, 0 failed
Restore compare clean: true
```

Restored-state rerun after the MCP proof:

```text
Outer status: D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\automation_runs\petrel_automation_20260704_100733.json
Bridge status: D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\automation_runs\petrel_export_mvp_bridge_20260704_100822.json
Bridge step_name: post_export_register_validate
Validation: D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\validation_reports\export_validation_20260704_100838.json
```

## What Is Still Missing

This is an MVP with a complete zero-GUI raw native-store export and a safe decoded metadata layer for parseable native stores. It is not a full universal-format geological conversion yet.

Still missing:

- Decoding proprietary native stores into universal LAS/SEG-Y/ZMAP/RESQML/ASCII object files.
- Petrel-side export operations for the remaining object classes when universal Petrel-generated files are required.
- Deeper decoding of bulk geometry, grid/property arrays, seismic cube samples, and well object internals beyond safe XML/SQLite/text metadata and LAS-derived well tables.
- Native Petrel workflow step insertion or creation through a confirmed supported API, import format, or mapped `.ptd` record.
- Mapped no-Ocean control for data tables, surfaces/maps, additional seismic objects/formats, interpretation, and model/grid/property exports.
- Zero-GUI native binary decoding of full well-top marker pick depths, or zero-GUI insertion of a mapped Petrel well-top export command. A Petrel-authored manual Well Tops ASCII export now exists and validates 84 actual marker-pick rows.

Native `.ptd` workflow storage has now been patched for same-length workflow identity, command-token, output-path-fragment edits, a real `ExportSeismicCmd` filename parameter, and a real `SystemCmd` bridge argument parameter. Two Petrel-authored `ExportSeismicCmd` donors have also been captured and run, giving a before/after structural diff for future command-clone work. Zero-GUI step insertion, record resizing, object-reference mutation, export-format enum mutation, and new workflow creation are still not proven. The safe external workflow-as-code artifact is currently:

```text
00_manifest/petrel_full_project_export.workflow.json
```

The no-Ocean MCP control surface is:

```text
D:\Computer\Code\Petrel_project\mcp\petrel_mcp_server.py
```

It exposes status, MVP preparation, workflow running, zero-GUI native export, zero-GUI semantic metadata extraction, zero-GUI well table extraction, GUI well-top table import/comparison, registration/validation, knowledge-base query, native workflow mapping, before/after snapshot comparison, guarded same-length patch dry-run/apply tools, guarded SEG-Y patch-run-restore tools, and guarded `SystemCmd` bridge patch-run-restore tools. See `docs/NO_OCEAN_MCP_CONTROL.md`.

## Current Export Targets

The first strict zero-GUI target is achieved:

- Done: raw full native project store to `08_native_project`, with 681 native files.
- Done: semantic zero-GUI metadata extraction for SMD faults/horizons/zones/frameworks, GMS property files, Ocean QR SQLite stores, XML/BXML metadata, and ZGY native inventory.
- Done: zero-GUI LAS-derived well headers, LAS curve inventory, and conservative well-top/top-reference CSVs.
- Done: 733 strict zero-GUI/package rows after the well-top regeneration pass, plus 2 validated manual GUI well-top validation artifacts and 5 Petrel-authored Well Tops ASCII export artifacts. Current manifest total is 740 validated rows, including zero-GUI native/semantic export, zero-GUI well tables, LAS logs, SEG-Y proof files, clean native well-top evidence, the parsed source ASCII well-top table, the GUI/source comparison, and the Petrel-authored 84-row Well Tops ASCII export package.

The first Petrel-generated universal-ish target is partly achieved:

- Done: `well_logs` to `02_wells\well_logs_las`, exported as 18 validated LAS files through UI automation.
- Done: one seismic cube (`Orig Amp`) to `03_seismic\segy`, exported as validated SEG-Y files through two saved Workflow Editor `Export SEGY seismic` commands and external CLI runs.
- Done: zero-GUI filename mutation of that saved `ExportSeismicCmd` output target, producing validated SEG-Y proof files, then restoring the binary patch.
- Done: MCP-controlled repeatable patch-run-restore export using `petrel_export_segy_filename_patch`.
- Done: MCP-controlled second-command token patch-run-restore export using `petrel_export_segy_token_patch`.
- Done: MCP-controlled `SystemCmd` bridge argument patch-run-restore using `petrel_export_systemcmd_token_patch`.

Next extend `ExportPiloX`, decode native stores, or add mapped command donors for:

1. zero-GUI creation/control of the Well Tops export command, or native binary marker-pick payload decoding, beyond the manual Petrel-authored ASCII export now validated
2. `data_tables` to `07_workflows_reports\exported_reports`
3. `surfaces_maps` to `04_surfaces_maps\zmap_dat`
4. additional `seismic` objects or ZGY/SEG-Y variants to `03_seismic`
5. `interpretation` to `05_interpretation`
6. `models/properties` to `06_models_properties`

After those write files, the existing external registrar and validator should pick them up automatically.
