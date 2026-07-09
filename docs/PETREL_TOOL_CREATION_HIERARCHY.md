# Petrel Tool Creation Hierarchy

This is the selection rule for creating new Petrel MCP/CLI tools.

Use the highest tier that can produce the required output with evidence. Do not move to a lower tier until the higher tier is proven insufficient for that specific task.

Machine-readable policy:

```text
D:\Computer\Code\Petrel_project\mcp\petrel_tool_creation_hierarchy.json
```

## Required Tool Contract

Every new tool must declare:

```text
task: what user-visible Petrel automation task it performs
inputs: required files, project paths, object selectors, workflow ids, version assumptions
outputs: generated files, formats, schema, and manifest rows
validation: row counts, checksums, parser checks, Petrel log evidence, and manifest validation
runtime_boundary: zero_gui_python, zero_gui_petrel_workflow_editor, deterministic_gui, or discovery_only
evidence: reports, screenshots if GUI is used, snapshots for native edits, restore reports for probes
```

## Tier 1 - Zero-GUI Python Or Direct File Processing

This is always first choice.

Use it when Python can read existing project/export/package files and produce the required output without launching Petrel and without desktop automation.

Examples already in this project:

```text
petrel_export_native_zero_gui
petrel_export_native_semantic_zero_gui
petrel_export_well_tables_zero_gui
petrel_export_well_tops_native_probe
```

Required evidence:

```text
runtime_gui_used=false
petrel_process_launched=false
parser/report JSON
manifest rows
validation report
```

Escalate only when the requested confirmed Petrel output cannot be decoded from files with enough confidence. For example, current zero-GUI well-top tooling can find top-name evidence and source-ASCII rows, but it cannot yet decode the confirmed native marker-pick payload.

## Tier 2 - Zero-GUI Petrel Workflow Editor Native Control

Use this when Petrel must author the final export, but the operation can still be controlled without desktop GUI.

Allowed mechanisms:

```text
saved Workflow Editor commands run by Petrel command line
workflow variables passed with -sparm/-nparm
same-length native .ptd parameter patches at mapped offsets
guarded patch-run-restore wrappers
read-only native command analyzers
```

Examples already in this project:

```text
run_petrel_full_export_mvp.ps1
petrel_export_segy_filename_patch
petrel_export_segy_token_patch
petrel_export_systemcmd_token_patch
petrel_analyze_exportseismiccmd_records
```

Required evidence:

```text
Petrel log: Status: Workflow run OK
workflow_execution_status=confirmed
native snapshots/compare reports for binary edits
patch and restore reports for probes
Petrel-written output files
manifest validation report
```

Escalate only when no saved or safely patchable Workflow Editor command can produce the requested output.

## Tier 3 - Reusable Deterministic GUI Workflow

Use this only when Tier 1 and Tier 2 cannot produce the requested result yet.

This is not a general desktop agent. It is a named workflow spec with bounded anchors, fixed actions, explicit inputs/outputs, trace logs, screenshots, and fail-closed validation.

Examples:

```text
petrel_run_deterministic_gui_workflow
petrel_gui_workflows\export_well_tops_ascii.json
```

Required evidence:

```text
workflow spec JSON
runner report
trace log
screenshots
exported files
parser/import report
manifest validation report
```

The current Well Tops ASCII workflow follows this tier:

```text
activate Petrel
right-click Input/Wells/Well Tops
Export object
save Petrel well tops ASCII
confirm Coordinate reference system selection
parse/register/validate
```

For an already-open Petrel project, this tier uses a fast deterministic path: short license-dialog absence check, one-cycle file stability polling, and no duplicate register/validate inside the UI helper. The outer runner remains responsible for the final import, manifest registration, checksum update, and validation report.

## Tier 4 - Discovery Or Donor Capture Only

Use this only when a deterministic GUI workflow cannot yet be made stable or when native workflow storage is not mapped enough.

This is not a production tool. The output is evidence for moving back up to Tier 2 or Tier 1.

Required evidence:

```text
before snapshot
after snapshot
snapshot compare report
operator notes
next candidate tier
```

## Composed Tool Workflows

A Petrel MCP tool may be a workflow of smaller tools. The workflow still has to state the tier for every step.

Standard structure:

```text
read_inputs
choose_highest_viable_tier
execute_or_dry_run
write_outputs
register_outputs
validate_outputs
write_run_report
```

Example for Well Tops:

```text
1. Try Tier 1: zero-GUI native/source/LAS well-top extraction.
2. If confirmed marker-pick rows are still missing, try Tier 2: saved or mapped Workflow Editor export command.
3. If no mapped command exists, use Tier 3: deterministic GUI Well Tops ASCII export.
4. Feed the raw ASCII output back into Tier 1 Python parsing, comparison, registration, and validation.
```

This keeps GUI automation as a bridge, not the default architecture.
