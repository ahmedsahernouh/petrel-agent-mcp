# Petrel Native Workflow Editing

This document records controlled native `.ptd` edit experiments for the Petrel automation copy.

## Results So Far

Same-length native edits have been proven and restored safely where needed:

- `Model.ptd` workflow identity edit: `ExportPilot` to `ExportPiloX`.
- `Data.ptd` workflow command token edit: `export_package` to `export_packagf`, then restored.
- `Data.ptd` workflow output path fragment edit by guarded offset: `csv` to `tsv`, then restored.
- `Data.ptd` `ExportSeismicCmd` filename-tail edit: `_donor.sgy` to `_zgui1.sgy`, then restored.
- Repeatable MCP-controlled `ExportSeismicCmd` filename-tail patch-run-restore: `_donor.sgy` to `_mcp01.sgy`, then restored.
- Repeatable MCP-controlled second-command token patch-run-restore: `sgy2` to `sgy3`, then restored.
- Repeatable `SystemCmd` bridge argument patch-run-restore: `register_validate` to `register_validatf`, then restored.
- Repeatable MCP-controlled `SystemCmd` bridge argument patch-run-restore: `post` to `p0st`, then restored.

These prove that external tooling can modify Petrel native workflow storage in-place for equal-length edits and that Petrel executes the modified workflow.

A stronger Petrel-authored donor milestone is also complete: a native Workflow Editor `Export SEGY seismic` command was added to `ExportPiloX`, configured for the `Orig Amp` seismic cube, saved into `.ptd`, run once from the GUI for validation, then run again from the external CLI wrapper. Petrel wrote a validated SEG-Y file. This proves the command exists in Workflow Editor storage and can be executed from outside Petrel after authoring. It does not yet prove zero-GUI insertion of a new variable-length command record.

A second Petrel-authored `Export SEGY seismic` command has now been added to the same workflow and saved in Petrel. The before/after diff proves the workflow stores now contain two `ExportSeismicCmd` records, and the external wrapper run wrote both the original donor SEG-Y and `orig_amp_exportpilot_sgy2.sgy`.

The second command's tokenized output suffix has also been patched through MCP without GUI: `sgy2` to `sgy3` at exact `Data.ptd` offset `173185552`. Petrel wrote `orig_amp_exportpilot_sgy3.sgy`, the manifest validated 724 rows, and the native store was restored with zero byte diffs.

A separate zero-GUI native project export milestone is also complete: the project `.pet/.ptd` native store can now be copied, indexed, semantically scanned for safe metadata, registered in the export manifest, and checksum-validated without launching Petrel.

A zero-GUI well-table milestone is also complete: the current export package can now derive well headers, LAS curve inventory, conservative well-top/top-reference CSVs, a cleaned native well-top evidence probe, and a parsed 98-row Petrel Well Tops ASCII source table through MCP without launching Petrel. A separate Petrel-authored Well Tops ASCII export is also now parsed and validated with 84 actual marker-pick rows. Native binary marker pick-depth payload decoding and zero-GUI insertion of the well-top export command are still not confirmed.

On 2026-07-04, a Windows desktop automation attempt tried to create a new `System command` donor in Petrel without manual interaction. Petrel exposed only a top-level custom WinForms pane through UI Automation, and conservative coordinate automation did not reveal a safe command insertion surface. The before/after snapshot compare showed no native-store changes. See `docs/DESKTOP_DONOR_AUTOMATION_ATTEMPT_20260704.md`.

A Petrel-authored `System command` bridge donor is now saved in `ExportPiloX`. It was added manually through the Workflow Editor search box, configured to call `scripts\petrel_export_mvp_bridge.ps1`, saved into native `.ptd` storage, mapped by before/after snapshots, and executed by the external CLI runner. Petrel logged `Executing System command .... (100%)`, the bridge wrote `external_workflow_bridge_probe.csv`, and validation passed. The saved `SystemCmd` argument payload is now also mapped and patchable through a guarded MCP tool for same-length argument edits.

The MCP server now attaches `mcp_result_audit` to native workflow tool responses. Read-only native tools pass only when their map/snapshot/compare/analyzer evidence exists. Low-level patch tools pass for dry-run evidence, but an applied raw patch remains incomplete until a Petrel run validates behavior. The patch-run-restore wrappers can pass a full mutation audit because they prove patch application, changed behavior, package validation, and binary restoration.

## Milestone 1 - Workflow Name In Model.ptd

The workflow name stored in:

```text
D:\Computer\Code\Petrel_project\Petrel_DemoData_project\Petrel2010 demo project ExportPilot.ptd\Model.ptd
```

was patched externally from:

```text
ExportPilot
```

to:

```text
ExportPiloX
```

The replacement is the same byte length, so the binary store layout was not shifted.

## Patch Evidence - Workflow Name

Patch command:

```powershell
.\scripts\patch_petrel_native_workflow_string.ps1
```

Patch report:

```text
D:\Computer\Code\Petrel_project\build\native_edit_experiments\native_workflow_string_patch_20260702_195212\native_workflow_string_patch_report.json
```

Important report values:

```text
target_path: D:\Computer\Code\Petrel_project\Petrel_DemoData_project\Petrel2010 demo project ExportPilot.ptd\Model.ptd
search: ExportPilot
replace: ExportPiloX
byte_length: 11
hit_count: 1
offset: 849331
before_sha256: 3bf4115ec1c2908e1a87b3727d0026ad64b3967a36b38f56a537930a4a1aeb26
after_sha256: 1c3f29181399b2e742f8184e14265d61aeeee5b31fd439255a43de1ae39cb34a
```

Backup:

```text
D:\Computer\Code\Petrel_project\build\native_edit_experiments\native_workflow_string_patch_20260702_195212\Model.ptd
```

## Petrel Validation

The patched workflow ran through Petrel command-line `-runWorkflow`:

```powershell
.\scripts\run_petrel_full_export_mvp.ps1
```

Latest verified status:

```text
Status file: D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\automation_runs\petrel_automation_20260702_195743.json
Petrel exit: 0
Workflow execution: confirmed
Artifact registration: registered
File export registration: registered
Validation: passed
```

The Petrel run log contains:

```text
Running workflow Automatic copy of ExportPiloX
Status: Workflow run OK
```

## Negative Control

After the patch, running the old workflow name returned Petrel process exit `0`, but no workflow execution was detected in the run log:

```text
Workflow execution: not_detected
Artifact registration: skipped_petrel_workflow_not_detected
```

This exposed an important automation rule: Petrel process exit code is not enough. The wrapper now requires `Status: Workflow run OK` in the Petrel log before treating a batch workflow run as successful.

## Milestone 2 - Command Token In Data.ptd

The serialized Workflow Editor command payload in:

```text
D:\Computer\Code\Petrel_project\Petrel_DemoData_project\Petrel2010 demo project ExportPilot.ptd\Data.ptd
```

was patched externally from:

```text
export_package
```

to:

```text
export_packagf
```

Patch command:

```powershell
.\scripts\patch_petrel_native_workflow_string.ps1 -RelativeStoreFile Data.ptd -Search export_package -Replace export_packagf
```

Patch report:

```text
D:\Computer\Code\Petrel_project\build\native_edit_experiments\native_workflow_string_patch_20260702_200648\native_workflow_string_patch_report.json
```

Important report values:

```text
target_path: D:\Computer\Code\Petrel_project\Petrel_DemoData_project\Petrel2010 demo project ExportPilot.ptd\Data.ptd
search: export_package
replace: export_packagf
byte_length: 14
hit_count: 1
offset: 173166025
before_sha256: b4382224d08c1516ff23a9f3ed99e22b5ca60f13258cb6ca2309ee5a8bb432dc
after_sha256: faf7247b1a9200dbcab12b717dcef5c2ca1ecbb99e6015d7673adb69b9d30d60
```

Petrel validation after the patch:

```text
Status file: D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\automation_runs\petrel_automation_20260702_200659.json
Petrel exit: 0
Workflow execution: confirmed
Validation: passed
```

The output sheet changed behavior after the native edit. Instead of the original populated package variable rows, Petrel wrote:

```text
export_packagf
inventory_packagf
export_manifest    D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\00_manifest\export_manifest.csv
```

That proves the externally patched `Data.ptd` token affected Workflow Editor command execution. It also showed an important serialization detail: changing the shared `export_package` token also affected the visible `inventory_package` row. Future edits must treat this payload as tokenized/shared data, not independent plain strings.

The patch was restored with:

```powershell
.\scripts\patch_petrel_native_workflow_string.ps1 -RelativeStoreFile Data.ptd -Search export_packagf -Replace export_package
```

Restore report:

```text
D:\Computer\Code\Petrel_project\build\native_edit_experiments\native_workflow_string_patch_20260702_200820\native_workflow_string_patch_report.json
```

## Milestone 3 - Output Path Fragment In Data.ptd

The output filename extension fragment for the same `SheetSaveCmd` payload was patched by exact offset. This required a new guarded offset patcher:

```text
D:\Computer\Code\Petrel_project\scripts\patch_petrel_native_workflow_offset.ps1
```

The script verifies the expected bytes at the target offset before writing.

Patch command:

```powershell
.\scripts\patch_petrel_native_workflow_offset.ps1 -RelativeStoreFile Data.ptd -Offset 173166325 -Expected csv -Replace tsv
```

Patch report:

```text
D:\Computer\Code\Petrel_project\build\native_edit_experiments\native_workflow_offset_patch_20260702_201606\native_workflow_offset_patch_report.json
```

Petrel validation after the patch:

```text
Status file: D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\automation_runs\petrel_automation_20260702_201623.json
Petrel exit: 0
Workflow execution: confirmed
Artifact registration: no_workflow_artifacts_found
File export registration: registered
Validation: skipped
```

The dedicated artifact registrar did not find the old `.csv` probe, as expected. Petrel instead wrote:

```text
D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\exported_reports\cli_variable_probe.tsv
```

The `.tsv` output contained the expected injected variable values, proving the native edit changed the Workflow Editor output path used by Petrel. Evidence was preserved at:

```text
D:\Computer\Code\Petrel_project\build\native_edit_experiments\tsv_output_probe_20260702_201617\cli_variable_probe.after_tsv_patch.tsv
```

The patch was restored with:

```powershell
.\scripts\patch_petrel_native_workflow_offset.ps1 -RelativeStoreFile Data.ptd -Offset 173166325 -Expected tsv -Replace csv
```

Restore report:

```text
D:\Computer\Code\Petrel_project\build\native_edit_experiments\native_workflow_offset_patch_20260702_201738\native_workflow_offset_patch_report.json
```

## Payload Inspection

The payload inspection script is:

```text
D:\Computer\Code\Petrel_project\scripts\inspect_petrel_native_workflow_payload.ps1
```

Latest relevant inspection output:

```text
D:\Computer\Code\Petrel_project\build\native_edit_experiments\native_workflow_payload_inspection_20260702_201151\native_workflow_payload_summary.md
```

It located:

```text
Data.ptd | SheetSaveCmd | offset 173165895
Data.ptd | export_package | offset 173166025
Data.ptd | cli_variable | offset 173166307
Data.ptd | csv | offset 173166325
Model.ptd | ExportPiloX | offset 849331
```

The richer region mapper is:

```text
D:\Computer\Code\Petrel_project\scripts\map_petrel_native_workflow_regions.ps1
```

Latest region map:

```text
D:\Computer\Code\Petrel_project\build\native_edit_experiments\native_workflow_region_map_20260702_203425\native_workflow_region_map_summary.md
```

It isolated the current output-sheet command record:

```text
Data.ptd | LZ4 before command | offset 173165688
Data.ptd | BXML command start | offset 173165703
Data.ptd | SheetSaveCmd | offset 173165895
Data.ptd | next BXML record | offset 173166363
```

This older scan was captured before the Petrel-authored bridge donor. The current workflow now contains a `SystemCmd` command record as documented in Milestone 6G.

After the SEG-Y donor milestones below, the workflow also contains two Petrel-authored `ExportSeismicCmd` command records.

## Milestone 4 - Petrel-Authored Export SEGY Seismic Donor

The Workflow Editor command palette contains a native seismic export command:

```text
Utilities > Import Export > Export SEGY seismic
```

It was added to `ExportPiloX` from Petrel's Workflow Editor UI, configured as:

```text
Command: Export SEGY seismic
Seismic: Orig Amp
Filename: D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\03_seismic\segy\orig_amp_exportpilot_donor.sgy
Coordinate scale factor: 0
Sample value format: 0
```

Petrel's Workflow Editor `Test` returned `Test OK`. Running from the editor wrote:

```text
D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\03_seismic\segy\orig_amp_exportpilot_donor.sgy
Bytes: 129584100
```

After saving and closing Petrel, the same saved workflow was run from outside Petrel:

```powershell
.\scripts\run_petrel_full_export_mvp.ps1
```

External-control validation:

```text
Status file: D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\automation_runs\petrel_automation_20260703_013217.json
Petrel exit: 0
Workflow execution: confirmed
Artifact registration: registered
File export registration: registered
Validation: passed
```

Latest package validation:

```text
D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\validation_reports\export_validation_20260703_013303.md
Manifest rows: 720
Validated rows: 720
Failed rows: 0
SEG-Y row: 03_seismic\segy\orig_amp_exportpilot_donor.sgy [SEG-Y]
```

The file registrar added the SEG-Y as:

```text
source_object_type: seismic_cube
export_format: SEG-Y
export_file: 03_seismic\segy\orig_amp_exportpilot_donor.sgy
validation_status: validated
```

Current limitation: the registrar did not map the file back to an inventory object UUID, so the row is validated but still has an inventory-matching gap.

### Donor Binary Diff

Before snapshot:

```text
D:\Computer\Code\Petrel_project\build\native_edit_experiments\native_workflow_snapshot_20260703_004858_before_export_format_donor
```

After snapshot:

```text
D:\Computer\Code\Petrel_project\build\native_edit_experiments\native_workflow_snapshot_20260703_012443_after_segy_export_workflow_donor
```

Diff report:

```text
D:\Computer\Code\Petrel_project\build\native_edit_experiments\native_workflow_snapshot_compare_20260703_012602\snapshot_compare_report.json
```

Store summary:

```text
Model.ptd changed: true, bytes 858782 -> 847829, length delta -10953, diff ranges 13429
Data.ptd changed: true, bytes 173178880 -> 173211648, length delta 32768, diff ranges 4778
```

The inserted command donor is visible in `Data.ptd`:

```text
BXML chunk index: 1293
LZ4 before command: 173200294
BXML command start: 173200309
Next BXML: 173201087
Approx command span: 778
Command type guess: SimpleCmd;SheetSaveCmd;ExportSeismicCmd
```

The following BXML chunk contains the filename tail:

```text
BXML chunk index: 1294
LZ4 before command: 173201073
BXML command start: 173201087
Context includes: \segy\orig_amp..._donor.sgy
```

Related string signals:

```text
Model.ptd Orig Amp: offset 682967
Model.ptd sgy: offset 683291
Data.ptd sgy: offsets 170478753, 173201043
Data.ptd Seismic near new donor: offset 173200521
```

Boundary: this donor proves a Petrel-authored `ExportSeismicCmd` record can be saved, diffed, and run from the CLI wrapper. It also exposes a patchable filename-tail field in `Data.ptd`, proven in the next milestone. It is not yet a zero-GUI binary insertion algorithm.

## Milestone 5 - Zero-GUI ExportSeismicCmd Filename Mutation

The saved Petrel-authored `ExportSeismicCmd` donor was mutated without launching Petrel or using the GUI. Only the `Data.ptd` command payload was patched; `Model.ptd` was intentionally left unchanged.

Patch:

```text
Store: Data.ptd
Search: _donor.sgy
Replace: _zgui1.sgy
Offset: 173201036
Byte length: 10
Hit count: 1
```

Patch report:

```text
D:\Computer\Code\Petrel_project\build\native_edit_experiments\native_workflow_string_patch_20260703_023521\native_workflow_string_patch_report.json
```

Before/after snapshots:

```text
D:\Computer\Code\Petrel_project\build\native_edit_experiments\native_workflow_snapshot_20260703_023413_before_zero_gui_segy_filename_patch
D:\Computer\Code\Petrel_project\build\native_edit_experiments\native_workflow_snapshot_20260703_023533_after_zero_gui_segy_filename_data_patch
```

Snapshot compare:

```text
D:\Computer\Code\Petrel_project\build\native_edit_experiments\native_workflow_snapshot_compare_20260703_023546\snapshot_compare_summary.md
Model.ptd changed: false, diff ranges: 0
Data.ptd changed: true, length delta: 0, diff ranges: 1
```

Petrel was then run only through the external wrapper:

```powershell
.\scripts\run_petrel_full_export_mvp.ps1
```

Patched-run validation:

```text
Status file: D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\automation_runs\petrel_automation_20260703_023613.json
Petrel exit: 0
Workflow execution: confirmed
Validation: passed
Petrel log: Exporting to file orig_amp_exportpilot_zgui1 'SEG-Y seismic data'
```

Petrel wrote the patched target:

```text
D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\03_seismic\segy\orig_amp_exportpilot_zgui1.sgy
Bytes: 129584100
```

The package validation after the patched run recorded:

```text
D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\validation_reports\export_validation_20260703_023657.md
Manifest rows: 721
Validated rows: 721
Failed rows: 0
SEG-Y rows: orig_amp_exportpilot_donor.sgy, orig_amp_exportpilot_zgui1.sgy
```

Because this was a probe patch, it was restored:

```text
Restore patch report: D:\Computer\Code\Petrel_project\build\native_edit_experiments\native_workflow_string_patch_20260703_023757\native_workflow_string_patch_report.json
Search: _zgui1.sgy
Replace: _donor.sgy
Offset: 173201036
Before SHA256: 4af6c7c0ac3783964bbff5e6bdf34828ec5b86632db2192e5dd65b1d55ad51b0
After SHA256: 802079019dd0f85b6c8ea5ac7e54960ec73ef06e9a27b50212573e5660c34bf2
```

Restore compare:

```text
D:\Computer\Code\Petrel_project\build\native_edit_experiments\native_workflow_snapshot_compare_20260703_023823\snapshot_compare_summary.md
Model.ptd changed: false, diff ranges: 0
Data.ptd changed: false, diff ranges: 0
```

The restored workflow was run again and exported the original donor target:

```text
Status file: D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\automation_runs\petrel_automation_20260703_023838.json
Petrel log: Exporting to file orig_amp_exportpilot_donor 'SEG-Y seismic data'
Validation report: D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\validation_reports\export_validation_20260703_023926.md
Manifest rows: 721
Validated rows: 721
Failed rows: 0
```

Evidence copy of the patched SEG-Y output:

```text
D:\Computer\Code\Petrel_project\build\native_edit_experiments\orig_amp_exportpilot_zgui1.zero_gui_patch_evidence.sgy
```

Boundary: this proves zero-GUI same-length mutation of a real `ExportSeismicCmd` output filename parameter in `Data.ptd`. It still does not prove command insertion, record resizing, object-reference mutation, export-format enum mutation, or new workflow creation.

## Milestone 6 - MCP-Controlled ExportSeismicCmd Patch-Run-Restore

The filename-tail mutation is now wrapped as a repeatable external tool:

```text
D:\Computer\Code\Petrel_project\scripts\invoke_petrel_segy_filename_patch_export.ps1
```

It is also exposed through the no-Ocean MCP server as:

```text
petrel_export_segy_filename_patch
```

The tool performs this guarded sequence:

1. Snapshot `.pet`, `Model.ptd`, and `Data.ptd`.
2. Verify the expected filename tail at exact `Data.ptd` offset `173201036`.
3. Apply a same-length ASCII replacement.
4. Snapshot and compare the patched state.
5. Run `ExportPiloX` through the external Petrel command-line workflow wrapper.
6. Register Petrel-written files and validate the package.
7. Restore the original filename tail unless `-KeepPatch` is explicitly passed.
8. Snapshot and compare the restored state.

MCP proof run:

```text
Tool: petrel_export_segy_filename_patch
Replacement: _mcp01.sgy
Report: D:\Computer\Code\Petrel_project\build\native_edit_experiments\segy_filename_patch_export_20260703_030410\segy_filename_patch_export_report.json
Petrel status: D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\automation_runs\petrel_automation_20260703_030416.json
Validation report: D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\validation_reports\export_validation_20260703_030503.md
Output: D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\03_seismic\segy\orig_amp_exportpilot_mcp01.sgy
Bytes: 129584100
SHA256: 1eaf8db3dd7b59bda328541a4549f8036f56a166c25be24414f3f617829629b7
Manifest rows: 722
Validated rows: 722
Failed rows: 0
```

Restore proof:

```text
Restore compare: D:\Computer\Code\Petrel_project\build\native_edit_experiments\native_workflow_snapshot_compare_20260703_030507\snapshot_compare_summary.md
Model.ptd changed: false, diff ranges: 0
Data.ptd changed: false, diff ranges: 0
Data.ptd restored SHA256: 802079019DD0F85B6C8EA5AC7E54960EC73EF06E9A27B50212573E5660C34BF2
```

Boundary: this is the first repeatable MCP tool that mutates a real Petrel `ExportSeismicCmd` payload, uses Petrel to execute the mutated command, validates the generated universal-format file, and restores the native store. It still only supports same-length field mutation at a known offset.

## Milestone 6B - Petrel-Authored Second ExportSeismicCmd Donor Diff

A second `Export SEGY seismic` command was added in Petrel to `ExportPiloX` as a structural donor for future zero-GUI command insertion work:

```text
Command: Export SEGY seismic
Object: Orig Amp
Output: D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\03_seismic\segy\orig_amp_exportpilot_sgy2.sgy
```

Before snapshot:

```text
D:\Computer\Code\Petrel_project\build\native_edit_experiments\native_workflow_snapshot_20260703_031623_before_zgy_or_format_donor_diff
```

After snapshot:

```text
D:\Computer\Code\Petrel_project\build\native_edit_experiments\native_workflow_snapshot_20260703_054150_after_second_segy_command_donor_diff
```

Diff report:

```text
D:\Computer\Code\Petrel_project\build\native_edit_experiments\native_workflow_snapshot_compare_20260703_054200\snapshot_compare_report.json
```

Store summary:

```text
Model.ptd changed: true, bytes 847829 -> 847739, length delta -90, diff ranges 21914
Data.ptd changed: true, bytes 173211648 -> 173211648, length delta 0, diff ranges 3234
```

The current `Data.ptd` now contains two command records with `ExportSeismicCmd` signals:

```text
BXML chunk index: 1293
BXML command start: 173184792
ExportSeismicCmd string offset: 173184998
Next BXML: 173185590
Approx command span: 798

BXML chunk index: 1296
BXML command start: 173200309
ExportSeismicCmd string offset: 173200515
Next BXML: 173201087
Approx command span: 778
```

The new output filename is tokenized in the store rather than present as one full plain ASCII path. The visible `sgy2` signal is at:

```text
Data.ptd offset: 173185552
```

External-control validation:

```text
Status file: D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\automation_runs\petrel_automation_20260703_054330.json
Petrel exit: 0
Workflow execution: confirmed
Artifact registration: registered
File export registration: registered
Validation: passed
Validation report: D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\validation_reports\export_validation_20260703_054445.md
Manifest rows: 723
Validated rows: 723
Failed rows: 0
```

Petrel wrote the second SEG-Y target from the externally launched workflow:

```text
D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\03_seismic\segy\orig_amp_exportpilot_sgy2.sgy
Bytes: 129584100
SHA256: ae2a7501fae1954a1f59f1c34daf9209b0720e632a8c0a1878ed6e547a9f994d
```

The Petrel run log contains:

```text
Exporting to file orig_amp_exportpilot_donor 'SEG-Y seismic data'
Status: Exported to ...\orig_amp_exportpilot_donor.sgy using format SEG-Y seismic data
Exporting to file orig_amp_exportpilot_sgy2 'SEG-Y seismic data'
Status: Exported to ...\orig_amp_exportpilot_sgy2.sgy using format SEG-Y seismic data
Status: Workflow run OK
```

Boundary: this is the first Petrel-authored structural diff that shows two saved `ExportSeismicCmd` records in the same workflow and proves both execute from the external wrapper. It is still not a zero-GUI command insertion algorithm; the next safe step is to map the record envelope and index changes well enough to build a guarded command-clone patcher.

## Milestone 6C - MCP-Controlled Second ExportSeismicCmd Token Patch

The second Petrel-authored `ExportSeismicCmd` command stores the `orig_amp_exportpilot_sgy2.sgy` filename in tokenized form. The visible `sgy2` token was patched by exact offset, run through Petrel, validated, and restored.

MCP tool:

```text
petrel_export_segy_token_patch
```

Patch:

```text
Store: Data.ptd
Offset: 173185552
Expected token: sgy2
Replacement token: sgy3
Target output: 03_seismic\segy\orig_amp_exportpilot_sgy3.sgy
```

Tool report:

```text
D:\Computer\Code\Petrel_project\build\native_edit_experiments\segy_token_patch_export_20260703_055859\segy_token_patch_export_report.json
```

External-control validation:

```text
Status file: D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\automation_runs\petrel_automation_20260703_055905.json
Workflow execution: confirmed
Validation report: D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\validation_reports\export_validation_20260703_055955.md
Manifest rows: 724
Validated rows: 724
Failed rows: 0
```

Petrel wrote:

```text
D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\03_seismic\segy\orig_amp_exportpilot_sgy3.sgy
Bytes: 129584100
SHA256: a61503cfa6667fd13590dc19bb4b7a748cab4f680360787f86be519e6a927584
```

Restore proof:

```text
D:\Computer\Code\Petrel_project\build\native_edit_experiments\native_workflow_snapshot_compare_20260703_055958\snapshot_compare_summary.md
Model.ptd changed: false, diff ranges: 0
Data.ptd changed: false, diff ranges: 0
```

Boundary: this proves that the LLM/MCP layer can select and mutate the second saved `ExportSeismicCmd` command's output token, run Petrel, validate the generated SEG-Y, and restore the native binary store. It is still same-length parameter mutation, not zero-GUI command insertion.

## Milestone 6D - ExportSeismicCmd Record Analyzer

A read-only analyzer now maps saved `ExportSeismicCmd` command records without modifying the Petrel project:

```text
D:\Computer\Code\Petrel_project\scripts\analyze_petrel_exportseismiccmd_records.py
```

It is exposed through MCP as:

```text
petrel_analyze_exportseismiccmd_records
```

Latest MCP analyzer proof:

```text
Report: D:\Computer\Code\Petrel_project\build\native_edit_experiments\exportseismiccmd_record_map_20260703_060617\exportseismiccmd_record_map.json
Record count: 2
Data SHA256: 96a5cc08294d009e6560df1861fd7d208bf86462796dd6fa9a86d40b51f94ae8
Model SHA256: e88cb6e2aae67a4ba335f724731ad235d8f9a3544f4515a63288600fcc77190f
```

Current record map:

```text
Record 0:
  ExportSeismicCmd offset: 173184998
  Previous LZ4: 173184777
  BXML start: 173184792
  Next BXML: 173185590
  Envelope length: 4807
  Output token candidates: segy at 173185500, _donor.sgy at 173185519, sgy2 at 173185552

Record 1:
  ExportSeismicCmd offset: 173200515
  Previous LZ4: 173200294
  BXML start: 173200309
  Next BXML: 173201087
  Envelope length: 793
  Output token candidates: segy at 173201017, _donor.sgy at 173201036
```

Boundary: this gives the tool layer a current machine-readable command map before applying exact-offset patches. It still does not identify all parent indexes or length fields needed for safe zero-GUI command insertion.

## Milestone 6E - Command Clone Readiness Analyzer

A read-only clone-readiness analyzer now combines the live `ExportSeismicCmd` record map, the first and second Petrel-authored SEG-Y donor diffs, and the proven patch-run-restore reports:

```text
D:\Computer\Code\Petrel_project\scripts\analyze_petrel_workflow_command_clone_readiness.py
```

It is exposed through MCP as:

```text
petrel_analyze_workflow_command_clone_readiness
```

Latest MCP analyzer proof:

```text
Report: D:\Computer\Code\Petrel_project\build\native_edit_experiments\workflow_command_clone_readiness_20260706_060734\workflow_command_clone_readiness.json
Clone safe: false
Status: blocked
Blockers: 10
Record count: 2
```

Current live `Data.ptd` command map from that report:

```text
Record 0:
  ExportSeismicCmd offset: 173184851
  Previous LZ4: 173184630
  BXML start: 173184645
  Next BXML: 173185590
  Envelope length: 4954
  Span to next BXML: 945

Record 1:
  ExportSeismicCmd offset: 173200515
  Previous LZ4: 173200294
  BXML start: 173200309
  Next BXML: 173200912
  Envelope length: 618
  Span to next BXML: 603
```

Passed gates:

```text
two_exportseismiccmd_records_present
record_envelopes_bounded
donor_compare_reports_loaded
same_length_parameter_mutation_proven
```

Blocking gates:

```text
record_spans_are_uniform
first_donor_model_changes_isolated
first_donor_data_payload_changes_isolated
second_donor_model_changes_isolated
second_donor_data_payload_changes_isolated
workflow_command-list_index_mutation_is_not_isolated
Model.ptd_UI_tree_or_object-reference_updates_are_not_mapped
BXML_LZ4_record_length_fields_are_not_mapped_for_insertion
unique_tag_GUID_behavior_is_not_mapped_for_cloned_commands
negative-control_clone_failure_and_recovery_have_not_been_run
```

Boundary: this is the machine-readable promotion gate before any zero-GUI command clone/insertion patcher. It confirms that same-length parameter mutation is proven, but it blocks variable-length command insertion until command-list indexes, length fields, GUID/tag behavior, object references, and recovery behavior are mapped.

## Milestone 6F - Command Clone Recipe Extractor

A read-only recipe extractor now converts the two Petrel-authored SEG-Y donor snapshot diffs into machine-readable clone evidence and candidate payload files:

```text
D:\Computer\Code\Petrel_project\scripts\extract_petrel_workflow_command_clone_recipe.py
```

It is exposed through MCP as:

```text
petrel_extract_workflow_command_clone_recipe
```

Latest MCP extractor proof:

```text
Report: D:\Computer\Code\Petrel_project\build\native_edit_experiments\workflow_command_clone_recipe_20260706_111557\workflow_command_clone_recipe.json
Recipe status: blocked
Safe to apply: false
Blockers: 8
Candidate payloads: 2
```

Extracted payload evidence:

```text
first_donor  command offset 173200515  core length 779  extended length 793
second_donor command offset 173184998  core length 799  extended length 4807
LZ4 length candidates: first value 755 at 173200298; second value 776 at 173184781
Command storage before authoring: first donor EOF append; second donor all-zero free-space region
Payload directory: D:\Computer\Code\Petrel_project\build\native_edit_experiments\workflow_command_clone_recipe_20260706_111557\candidate_payloads
Payload mutations: D:\Computer\Code\Petrel_project\build\native_edit_experiments\workflow_command_clone_recipe_20260706_111557\clone_recipe_payload_mutations.csv
Side-effect summary: D:\Computer\Code\Petrel_project\build\native_edit_experiments\workflow_command_clone_recipe_20260706_111557\clone_recipe_side_effect_summary.csv
Payload signals: D:\Computer\Code\Petrel_project\build\native_edit_experiments\workflow_command_clone_recipe_20260706_111557\clone_recipe_payload_signals.csv
Negative controls: D:\Computer\Code\Petrel_project\build\native_edit_experiments\workflow_command_clone_recipe_20260706_111557\clone_recipe_negative_controls.csv
```

Passed gates:

```text
donor_added_records_detected
candidate_payload_files_written
core_record_bounds_detected
second_donor_preserved_existing_record_offset
command_body_storage_location_mapped
side_effect_diff_classes_mapped
workflow_command_record_order_mapped
payload_lengths_detected
lz4_length_field_candidates_mapped
bxml_mutation_candidates_mapped
exportseismiccmd_orig_amp_payload_signals_mapped
unique_tag_payload_field_candidates_mapped
negative_control_clone_refusal_guard_recorded
```

Blocking gates:

```text
data_side_effects_outside_command_body_are_isolated
model_side_effects_isolated
bxml_mutation_semantics_are_not_validated
workflow_command_list_index_semantics_are_not_validated
model.ptd_ui_tree_and_object_reference_semantics_are_not_validated
exportseismiccmd_object_reference_binding_semantics_are_not_validated
unique_tag_guid_generation_or_reuse_rule_is_not_validated
applied_clone_recovery_proof_has_not_run
```

Boundary: this extracts real donor payload bytes and a candidate clone recipe, but it is still read-only evidence. It must not be used to write a clone until broad data/model side effects, BXML mutation semantics, command-list/index semantics, Model.ptd object/UI updates, GUID/tag behavior, and applied-clone recovery are validated.

## Milestone 6F2 - Command Clone Side-Effect Isolation Analyzer

A read-only side-effect analyzer now classifies donor snapshot diff ranges before any command-clone patcher is allowed:

```text
D:\Computer\Code\Petrel_project\scripts\analyze_petrel_workflow_clone_side_effects.py
```

It is exposed through MCP as:

```text
petrel_analyze_workflow_clone_side_effects
```

Latest MCP analyzer proof:

```text
Report: D:\Computer\Code\Petrel_project\build\native_edit_experiments\workflow_clone_side_effects_20260706_111542\workflow_clone_side_effects.json
Status: blocked
Side effects isolated: false
Clone patch precondition satisfied: false
Blockers: 4
Model edit likely required: true
```

Mapped isolation groups:

```text
required_command_payload
store_allocation_churn
data_store_index_or_page_churn
mixed_command_payload_and_store_allocation_churn
required_neighbor_record_candidate
model_store_header_churn
model_ui_object_reference_churn
```

Blocking groups:

```text
data_store_index_or_page_churn
mixed_command_payload_and_store_allocation_churn
required_neighbor_record_candidate
model_store_header_churn
model_ui_object_reference_churn
```

Required actions before any clone write:

```text
map_data_store_index_and_command_list_updates
split_command_payload_from_store_growth
map_model_store_header_updates
map_model_ui_object_reference_updates
map_neighbor_record_semantics
```

Boundary: this is progress on the first remaining recipe blocker, but the result is still blocked. The analyzer shows that a Data.ptd-only insertion is not safe to assume: donor authoring also churned Model.ptd header/root and UI/object-reference regions. No clone patcher should write native stores until these semantics are mapped or proven ignorable on a disposable copy.

## Milestone 6F3 - Command Clone Storage Block Splitter

A read-only storage block splitter now separates actual `ExportSeismicCmd` command-core bytes from surrounding `Data.ptd` allocator/page-growth bytes:

```text
D:\Computer\Code\Petrel_project\scripts\analyze_petrel_workflow_clone_storage_blocks.py
```

It is exposed through MCP as:

```text
petrel_analyze_workflow_clone_storage_blocks
```

Latest MCP analyzer proof:

```text
Report: D:\Computer\Code\Petrel_project\build\native_edit_experiments\workflow_clone_storage_blocks_20260706_111547\workflow_clone_storage_blocks.json
Status: blocked
Storage payload separated: true
Clone patch precondition satisfied: false
Blockers: 3
Segment classes: 16
Required actions: 4
```

The first donor's single 32 KB appended `Data.ptd` diff block is now split into:

```text
store_growth_before_command_core: 21414 bytes
required_command_core_payload: 779 bytes
neighbor_or_extended_record_overlap: 14 bytes
store_growth_after_command_core: 10561 bytes
```

The second donor's small mixed edge ranges are now split into:

```text
store_growth_before_command_core
required_command_core_payload
neighbor_or_extended_record_overlap
store_growth_after_command_core
```

Remaining blocking segment classes:

```text
data_store_index_or_page_churn
neighbor_or_extended_record_overlap
model_store_header_churn
model_ui_object_reference_churn
```

Required actions before any clone write:

```text
map_data_store_index_and_command_list_updates
map_neighbor_record_semantics
map_model_store_header_updates
map_model_ui_object_reference_updates
```

Boundary: this removes the `mixed_command_payload_and_store_allocation_churn` blocker from the previous side-effect analyzer by proving where the command payload starts and ends inside mixed storage ranges. It still does not authorize a native write. A command-clone patcher remains blocked until Data.ptd list/index churn, neighbor/extended record semantics, and Model.ptd header/UI/object-reference updates are mapped or proven ignorable on a disposable copy.

## Milestone 6G - Petrel-Authored System Command Bridge Donor

A `System command` was added manually in Petrel's Workflow Editor search box and saved in `ExportPiloX`:

```text
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "D:\Computer\Code\Petrel_project\scripts\petrel_export_mvp_bridge.ps1" -StepName "post_export_register_validate"
```

Before snapshot:

```text
D:\Computer\Code\Petrel_project\build\native_edit_experiments\native_workflow_snapshot_20260704_085738_before_manual_system_command_donor
```

After snapshot:

```text
D:\Computer\Code\Petrel_project\build\native_edit_experiments\native_workflow_snapshot_20260704_092035_after_manual_system_command_donor
```

Diff report:

```text
D:\Computer\Code\Petrel_project\build\native_edit_experiments\native_workflow_snapshot_compare_20260704_092053\snapshot_compare_report.json
```

Store summary:

```text
Model.ptd changed: true, bytes 847739 -> 847106, length delta -633, diff ranges 17421
Data.ptd changed: true, bytes 173211648 -> 173211648, length delta 0, diff ranges 490
```

Current command-region map:

```text
D:\Computer\Code\Petrel_project\build\native_edit_experiments\native_workflow_region_map_20260704_092313\native_workflow_region_map_summary.md
Data.ptd BXML command start: 173184645
Data.ptd SystemCmd offset: 173184881
Data.ptd powershell.exe offset: 173185435
Data.ptd StepName offset: 173185525
Next BXML: 173185590
```

External-control validation:

```text
Status file: D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\automation_runs\petrel_automation_20260704_092507.json
Workflow execution: confirmed
Artifact registration: registered
File export registration: registered
Validation: passed
Petrel log: Executing System command .... (100%); Status: Workflow run OK
```

Bridge evidence:

```text
Bridge status: D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\automation_runs\petrel_export_mvp_bridge_20260704_092550.json
Probe file: D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\exported_reports\external_workflow_bridge_probe.csv
Step name: post_export_register_validate
Validation report: D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\validation_reports\export_validation_20260704_092609.md
```

Boundary: this proves a Petrel-authored `System command` can link a saved native workflow to the external CLI automation layer and execute from the outside-Petrel runner. It is not yet a zero-GUI insertion algorithm for creating new `SystemCmd` records; it is a donor record and bridge execution proof.

## Milestone 6H - MCP-Controlled SystemCmd Argument Patch

The saved `System command` donor now has a read-only analyzer and guarded patch-run-restore wrapper:

```text
scripts\analyze_petrel_systemcmd_records.py
scripts\invoke_petrel_systemcmd_token_patch_export.ps1
mcp tool: petrel_analyze_systemcmd_records
mcp tool: petrel_export_systemcmd_token_patch
```

Read-only map:

```text
Report: D:\Computer\Code\Petrel_project\build\native_edit_experiments\systemcmd_record_map_20260704_100011\systemcmd_record_map.json
Record count: 1
SystemCmd offset: Data.ptd 173184881
BXML command start: Data.ptd 173184645
Next BXML: Data.ptd 173185590
powershell.exe offset: Data.ptd 173185435
StepName offset: Data.ptd 173185525
post offset: Data.ptd 173185535
register_validate offset: Data.ptd 173185543
```

Direct guarded proof:

```text
Patch: Data.ptd register_validate -> register_validatf at offset 173185543
Target bridge step: post_export_register_validatf
Report: D:\Computer\Code\Petrel_project\build\native_edit_experiments\systemcmd_token_patch_export_20260704_100034\systemcmd_token_patch_export_report.json
Patch report: D:\Computer\Code\Petrel_project\build\native_edit_experiments\native_workflow_offset_patch_20260704_100035\native_workflow_offset_patch_report.json
Petrel status: D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\automation_runs\petrel_automation_20260704_100041.json
Bridge status: D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\automation_runs\petrel_export_mvp_bridge_20260704_100126.json
Bridge step_name: post_export_register_validatf
Validation: D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\validation_reports\export_validation_20260704_100144.json
Validation rows: 735, failed: 0
Restore report: D:\Computer\Code\Petrel_project\build\native_edit_experiments\native_workflow_offset_patch_20260704_100144\native_workflow_offset_patch_report.json
Restore compare: D:\Computer\Code\Petrel_project\build\native_edit_experiments\native_workflow_snapshot_compare_20260704_100147\snapshot_compare_report.json
Restore compare clean: true
```

MCP-controlled proof:

```text
Tool: petrel_export_systemcmd_token_patch
Patch: Data.ptd post -> p0st at offset 173185535
Target bridge step: p0st_export_register_validate
Report: D:\Computer\Code\Petrel_project\build\native_edit_experiments\systemcmd_token_patch_export_20260704_100224\systemcmd_token_patch_export_report.json
Patch report: D:\Computer\Code\Petrel_project\build\native_edit_experiments\native_workflow_offset_patch_20260704_100225\native_workflow_offset_patch_report.json
Petrel status: D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\automation_runs\petrel_automation_20260704_100230.json
Bridge status: D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\automation_runs\petrel_export_mvp_bridge_20260704_100312.json
Bridge step_name: p0st_export_register_validate
Validation: D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\validation_reports\export_validation_20260704_100327.json
Validation rows: 735, failed: 0
Restore report: D:\Computer\Code\Petrel_project\build\native_edit_experiments\native_workflow_offset_patch_20260704_100328\native_workflow_offset_patch_report.json
Restore compare: D:\Computer\Code\Petrel_project\build\native_edit_experiments\native_workflow_snapshot_compare_20260704_100330\snapshot_compare_report.json
Restore compare clean: true
```

Boundary: this proves the LLM/MCP layer can mutate a saved Petrel `SystemCmd` argument value in native `Data.ptd`, run Petrel, observe the changed external bridge behavior, validate the package, and restore the binary store with a clean compare. It still only supports same-length argument edits at known offsets; it does not create a new `SystemCmd` record or insert workflow steps.

## Milestone 7 - Zero-GUI Native Project Store Export

The zero-GUI exporter is:

```text
D:\Computer\Code\Petrel_project\scripts\export_petrel_native_project_zero_gui.ps1
```

One-command wrapper:

```text
D:\Computer\Code\Petrel_project\scripts\run_petrel_zero_gui_export_mvp.ps1
```

MCP tool:

```text
petrel_export_native_zero_gui
```

Latest run:

```text
D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\native_zero_gui_export\zero_gui_native_export_20260702_235354.json
```

Important values:

```text
runtime_gui_used: false
petrel_process_launched: false
copied_file_count: 681
copied_total_bytes: 943518543
text_probe_file_count: 666
candidate_count: 1746
validation_status: passed
```

Validation evidence:

```text
D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\validation_reports\export_validation_20260702_235440.md
Rows: 702
Validated: 702
Failed: 0
```

Generated indexes:

```text
D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\00_manifest\native_store_inventory.csv
D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\00_manifest\native_object_candidates.csv
```

This milestone exports the whole native project store in a reproducible package and proves a strict no-GUI, no-Ocean, no-Petrel-launch path. It does not decode proprietary Petrel stores into universal geological formats by itself.

## Milestone 8 - Zero-GUI Native Semantic Metadata Extraction

The semantic zero-GUI extractor is:

```text
D:\Computer\Code\Petrel_project\scripts\export_petrel_native_semantic_zero_gui.ps1
D:\Computer\Code\Petrel_project\scripts\export_petrel_native_semantic_zero_gui.py
```

The one-command zero-GUI runner now executes the raw native copy first and then the semantic extraction:

```text
D:\Computer\Code\Petrel_project\scripts\run_petrel_zero_gui_export_mvp.ps1
```

MCP tools:

```text
petrel_run_zero_gui_export_mvp
petrel_export_native_semantic_zero_gui
```

Latest verified run:

```text
D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\native_semantic_export\zero_gui_native_semantic_export_20260703_064917.json
D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\validation_reports\export_validation_20260703_064921.md
runtime_gui_used: false
petrel_process_launched: false
fault_models: 92
horizon_models: 9
zone_models: 11
structural_frameworks: 4
gms_property_files: 193
sqlite_schema_rows: 70
xml_metadata_files: 116
zgy_files: 2
manifest_rows: 719
validation_failed_rows: 0
```

Generated semantic outputs include:

```text
01_project_metadata\native_project_metadata_zero_gui.json
01_project_metadata\native_project_object_counts.csv
01_project_metadata\native_ocean_xml_metadata.csv
01_project_metadata\native_sqlite_schema.csv
01_project_metadata\native_sqlite_reference_values.csv
05_interpretation\faults\native_fault_models.csv
05_interpretation\horizons\native_horizon_models.csv
05_interpretation\horizons\native_zone_models.csv
06_models_properties\structural_models\native_structural_frameworks.csv
06_models_properties\structural_models\native_gms_property_files.csv
03_seismic\seismic_metadata\native_zgy_inventory.csv
```

Boundary: this milestone decodes safe XML, SQLite, text-like property metadata, and file inventory only. It does not decode proprietary bulk geometry stores, grid/property arrays, seismic cube samples, or full native object payloads.

## Milestone 8B - Zero-GUI Well Headers, LAS Inventory, And Well-Top References

The zero-GUI well table exporter is:

```text
D:\Computer\Code\Petrel_project\scripts\export_petrel_well_tables_zero_gui.ps1
D:\Computer\Code\Petrel_project\scripts\export_petrel_well_tables_zero_gui.py
```

MCP tool:

```text
petrel_export_well_tables_zero_gui
```

Latest MCP-controlled run:

```text
D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\zero_gui_well_exports\well_tables_zero_gui_20260703_140507.json
D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\validation_reports\export_validation_20260704_070049.md
runtime_gui_used: false
petrel_process_launched: false
las_files: 18
well_header_rows: 18
curve_inventory_rows: 259
well_top_reference_rows: 23
actual_well_top_pick_rows: 0
las_top_link_rows: 2
manifest_rows: 727
validation_failed_rows: 0
```

Generated outputs:

```text
02_wells\well_headers\las_well_headers.csv
02_wells\well_headers\las_curve_inventory.csv
02_wells\well_tops\well_tops_from_zero_gui_sources.csv
```

Boundary: this is a zero-GUI package-derived metadata extraction. The well-top CSV is a reference inventory containing two LAS zone-log values linked to `Well Tops` and 21 native XML marker/well-top references. It is not an actual Petrel marker-pick table; binary marker pick-depth records still need decoding or a mapped Petrel `Export well data` workflow command.

## Milestone 8C - Clean Native Well-Top Probe And Source ASCII Recovery

The native well-top probe is:

```text
D:\Computer\Code\Petrel_project\scripts\export_petrel_well_tops_native_probe.ps1
D:\Computer\Code\Petrel_project\scripts\export_petrel_well_tops_native_probe.py
```

MCP tool:

```text
petrel_export_well_tops_native_probe
```

Latest run:

```text
D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\zero_gui_well_exports\well_tops_native_probe_20260704_133652.json
runtime_gui_used: false
petrel_process_launched: false
native_top_name_occurrences: 5
native_top_order_candidate: T_Tarbert [Converted], T_Ness, T_Etive, Seabed, BCU
native_history_rows: 1
las_zone_log_candidate_rows: 2
source_ascii_pick_rows: 98
native_binary_marker_pick_rows: 0
manual_gui_table_capture_rows: 84
gui_vs_source_status_counts: matched=73; matched_with_numeric_differences=7; missing_in_gui_paste=18; missing_in_source_ascii=4
manifest_rows: 735
validation_failed_rows: 0
```

Generated outputs:

```text
02_wells\well_tops\well_tops_native_binary_probe.csv
02_wells\well_tops\well_tops_from_source_ascii.csv
02_wells\well_tops\well_tops_native_decode_attempt.csv
02_wells\well_tops\well_tops_from_petrel_gui_paste.csv
02_wells\well_tops\well_tops_gui_vs_source_ascii_compare.csv
```

The native probe CSV is now cleaned to canonical evidence rows only; raw binary-adjacent symbols are no longer exposed in the user-facing CSV. `well_tops_from_source_ascii.csv` contains real well/top/depth rows parsed from the local Petrel Well Tops ASCII source file, but every row remains labeled `native_binary_confirmed=no`. `well_tops_from_petrel_gui_paste.csv` captures the manual Petrel GUI table as an 84-row validation target, and the comparison report shows four B1 GUI rows missing from the source-ASCII fallback plus seven C6 rows with small X/depth deltas. The native BXML/Points marker-pick payload still needs mapping before this can be called a native binary decode.

## Milestone 8D - Petrel-Authored Well Tops ASCII Export

The Well Tops table was exported once from Petrel's UI to a Petrel ASCII text file, then imported, compared, registered, and validated by the outside-Petrel tooling:

```text
D:\Computer\Code\Petrel_project\scripts\import_petrel_well_tops_ascii_export.py
D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\02_wells\well_tops\well_tops_petrel_ascii_manual01.txt
D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\02_wells\well_tops\well_tops_petrel_ascii_manual01.txt.crsmeta.xml
D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\02_wells\well_tops\well_tops_from_petrel_ascii_export.csv
D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\02_wells\well_tops\well_tops_petrel_ascii_export_vs_gui_compare.csv
D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\02_wells\well_tops\well_tops_petrel_ascii_export_vs_source_ascii_compare.csv
```

Latest import report:

```text
D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\zero_gui_well_exports\well_tops_petrel_ascii_export_20260705_081214.json
manual_petrel_export_used: true
runtime_gui_used_by_importer: false
petrel_process_launched_by_importer: false
petrel_ascii_rows: 84
petrel_ascii_vs_gui_status_counts: matched=84
petrel_ascii_vs_source_status_counts: matched=73; matched_with_numeric_differences=7; missing_in_petrel_ascii_export=18; missing_in_source_ascii=4
crs: ED50-UTM31 / EPSG,23031
validation_report: export_validation_20260705_011307.md
manifest_rows: 740
validation_failed_rows: 0
```

Boundary: this proves the 84 visible GUI Well Tops rows can be exported from Petrel into a universal text file and processed automatically after save. It is not a native binary marker-pick decoder and not yet a zero-GUI workflow-command insertion method.

## Current Project State

The automation copy now uses:

```text
ExportPiloX
```

The original name was:

```text
ExportPilot
```

The runner defaults were updated to `ExportPiloX`.

`Data.ptd` has the normal `.csv` output path, the normal `export_package` token, the restored original Petrel-authored `Export SEGY seismic` donor step, the second Petrel-authored `Export SEGY seismic` donor step, and the restored Petrel-authored `System command` bridge donor step. Latest full MVP validation after the MCP-controlled `SystemCmd` patch-run-restore proof and a restored-state normal rerun:

```text
Status file: D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\automation_runs\petrel_automation_20260704_100733.json
Petrel exit: 0
Workflow execution: confirmed
Artifact registration: registered
File export registration: registered
Validation: passed
Bridge status: D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\automation_runs\petrel_export_mvp_bridge_20260704_100822.json
Bridge step_name after restore: post_export_register_validate
Validation: D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\validation_reports\export_validation_20260704_100838.json
Restore compare: D:\Computer\Code\Petrel_project\build\native_edit_experiments\native_workflow_snapshot_compare_20260704_100330\snapshot_compare_report.json
```

## Restore Command

To restore the original workflow name:

```powershell
.\scripts\patch_petrel_native_workflow_string.ps1 -Search ExportPiloX -Replace ExportPilot
```

Then run:

```powershell
.\scripts\run_petrel_full_export_mvp.ps1 -WorkflowName ExportPilot
```

## Boundary

This proves controlled same-length native `.ptd` edits can change:

- a workflow identity in `Model.ptd`,
- a Workflow Editor command token in `Data.ptd`,
- a Workflow Editor output path fragment in `Data.ptd`.
- a real `ExportSeismicCmd` filename tail in `Data.ptd`, while leaving `Model.ptd` unchanged.
- a real `SystemCmd` bridge argument token in `Data.ptd`, while restoring the native store afterward.

It also proves that Petrel-authored `Export SEGY seismic` commands can be captured as donor records, saved into native storage, and executed from the CLI wrapper to produce validated Petrel-generated SEG-Y files. The Petrel-authored `System command` bridge donor now proves a saved native workflow can call back into the outside-Petrel CLI automation layer during the workflow run, and that MCP can mutate that bridge argument value in a guarded patch-run-restore loop.

It does not yet prove that we can safely insert new variable-length workflow steps, resize serialized records, or create a new workflow from scratch in native storage. The next native milestone is to turn the two-command donor diff into a guarded command-clone patcher only after record envelopes, indexes, object references, and length fields are mapped.

The zero-GUI native export does not require that step-insertion milestone; it preserves native project data directly and now decodes a useful metadata layer. Universal-format exports still require either deeper decoded native store layouts or additional mapped Petrel export command donors. The Petrel-authored Well Tops ASCII file closes the actual well-top table evidence gap for inspection, but native binary decoding and zero-GUI well-top export command creation remain open milestones.
