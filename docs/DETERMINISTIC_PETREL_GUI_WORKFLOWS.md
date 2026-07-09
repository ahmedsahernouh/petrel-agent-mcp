# Deterministic Petrel GUI Workflows

This layer is Tier 3 in the Petrel tool-creation hierarchy. It is the fallback when Tier 1 zero-GUI Python/direct file processing and Tier 2 zero-GUI Workflow Editor/native control cannot yet produce a confirmed universal-format Petrel export.

The rule is strict:

```text
zero-GUI Python/direct files -> zero-GUI Workflow Editor/native control -> deterministic GUI micro-tool only when needed -> parse/register/validate -> fail closed
```

Full hierarchy:

```text
D:\Computer\Code\Petrel_project\docs\PETREL_TOOL_CREATION_HIERARCHY.md
```

It is not a free-form desktop agent. The LLM calls a named MCP tool with a named workflow id, and the runner executes a fixed contract from:

```text
D:\Computer\Code\Petrel_project\petrel_gui_workflows
```

## First Workflow

Current prototype:

```text
petrel_gui_workflows\export_well_tops_ascii.json
```

Purpose:

```text
Input > Wells > Well Tops -> Export object -> Petrel well tops ASCII
```

Why this needs the fallback:

- The zero-GUI well-table tools can derive LAS/native well-top references.
- The zero-GUI native probe can recover useful top-name and source-ASCII evidence.
- They still do not decode the confirmed native binary marker-pick payload into the visible Petrel Well Tops table.
- A Petrel-authored ASCII export gives confirmed `well_name`, `surface/top`, depth/MD/TWT rows.

## Runner

Dry run, no Petrel launch:

```powershell
cd "D:\Computer\Code\Petrel_project"
.\scripts\invoke_petrel_deterministic_gui_workflow.ps1 -WorkflowId export_well_tops_ascii
```

Execute the workflow:

```powershell
.\scripts\invoke_petrel_deterministic_gui_workflow.ps1 `
  -WorkflowId export_well_tops_ascii `
  -Execute `
  -CoordinateFallback
```

The `-CoordinateFallback` flag is explicit because Petrel's WinForms tree is not always exposed through UI Automation. The workflow still fails closed unless the ASCII file exists, parses into rows, registers, and validates.

## MCP Tool

MCP entry point:

```text
petrel_run_deterministic_gui_workflow
```

Default behavior is dry-run. It does not launch Petrel unless `execute: true` is passed.

Minimal dry-run call:

```json
{
  "workflow_id": "export_well_tops_ascii"
}
```

Execution call:

```json
{
  "workflow_id": "export_well_tops_ascii",
  "execute": true,
  "coordinate_fallback": true,
  "timeout_seconds": 900,
  "license_dialog_timeout_seconds": 3,
  "stable_file_ticks": 1,
  "file_poll_seconds": 1
}
```

## Evidence Contract

Every run writes a runner report:

```text
07_workflows_reports\automation_runs\deterministic_gui_export_well_tops_ascii_*.json
```

An executed run must also provide:

```text
07_workflows_reports\automation_runs\petrel_ui_welltops_export_*.trace.log
07_workflows_reports\automation_runs\ui_well_log_export_*\*.png
02_wells\well_tops\well_tops_exportpilot_detgui_*.txt
02_wells\well_tops\well_tops_exportpilot_detgui_*.txt.crsmeta.xml
02_wells\well_tops\well_tops_from_petrel_ascii_export.csv
02_wells\well_tops\well_tops_petrel_ascii_export_vs_gui_compare.csv
02_wells\well_tops\well_tops_petrel_ascii_export_vs_source_ascii_compare.csv
07_workflows_reports\validation_reports\export_validation_*.md
```

## Verified Run

Latest deterministic GUI execution:

```text
MCP result audit: passed
Runner report: D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\07_workflows_reports\automation_runs\deterministic_gui_export_well_tops_ascii_20260706_053532.json
Raw ASCII: D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\02_wells\well_tops\well_tops_exportpilot_detgui_20260706_053532.txt
CRS sidecar: D:\Computer\Code\Petrel_project\build\export_pilots\petrel2010_demo_project_export_20260701_060609\02_wells\well_tops\well_tops_exportpilot_detgui_20260706_053532.txt.crsmeta.xml
Parsed rows: 84
GUI comparison: matched=84
Source comparison: matched=73; matched_with_numeric_differences=7; missing_in_petrel_ascii_export=18; missing_in_source_ascii=4
Validation: passed, rows=750, failed=0
Audit gates: process_exit_zero, execution_requested, runner_report_loaded, runner_report_status_passed, ui_driver_exit_zero, raw_petrel_ascii_exists_nonempty, ascii_import_rows_gt_zero, manifest_validation_passed, postconditions_passed
UI helper manifest pass: skipped; outer deterministic runner performed final import/register/validate
```

The calibrated sequence is:

```text
activate Petrel -> right-click Input/Wells/Well Tops -> Export object -> save Petrel well tops ASCII -> confirm Coordinate reference system selection with OK for all -> parse/register/validate
```

## Performance Pattern (shared driver)

GUI-tool speed is dominated by UIA scan cost, not by clicking. The single biggest cost is `AutomationElement.FindAll(TreeScope::Descendants)` over the Petrel main window: Petrel's UIA tree is enormous, so one such call blocks ~10-15 seconds, which silently defeats any short poll timeout. The `export_petrel_well_logs_ui.ps1` shared driver therefore follows these rules, and every new GUI tool built on it inherits them:

- Dialogs (Export as, Save As, overwrite, CRS) are top-level windows. Find them with `Find-TopLevelWindowByTitleRegex` (a `Children`-scope scan, milliseconds), not a deep descendant scan. The deep scan (`Find-WindowByRegexDeep`) is a last-resort fallback only.
- Context-menu items live in their own popup window (Win32 class `#32768` / ControlType `Menu`). Use `Find-ContextMenuItemByName`, which descends only into those small popup subtrees and never walks the Petrel main window. This preserves the OCR fallback if the popup is not exposed via UIA.
- Preflight "dismiss stray dialog" checks (stale export dialog, Studio login, OFM connector, project data table) must use the fast top-level scan; on the common empty case a deep scan wastes ~15s each.
- Do not tighten waits around genuine Petrel processing (e.g. the CRS dialog appears only after Petrel computes the export); those seconds are real work, not scan overhead.

The 2026-07-08 pass applied these to the Well Tops flow, targeting the three scan-bound stages (stale-dialog ~17s, Export-object menu ~22s, Export-as dialog ~14s) that dominated a ~108s run.

## Robustness To Screen / Window / Monitor / DPI

A 2026-07-08 read-only UIA probe established the hard boundary that dictates the whole design: Petrel's Explorer tree and the Input/Models/Results/Templates tab strip expose **zero TreeItems and zero TabItems via UI Automation** - they are custom-drawn controls with no accessibility layer. So that navigation *cannot* be done with geometry-independent UIA and must be visual (screenshot + OCR + click). This splits the flow in two:

- **Interaction layer** - Export as dialog, format ComboBox, File name edit, Save/OK/CRS buttons, and the Export object context menu - are standard Win32/WPF controls. They are driven by UIA (`ValuePattern.SetValue`, `Invoke`, popup-scoped item search), which uses element identity, not pixels. This layer is already robust to window size/position, monitor, DPI, and remote-desktop rendering.
- **Explorer tree + tab strip** - visual only. Robustness here comes from: (1) all OCR regions and clicks computed **relative to the Petrel window rect** (from UIA), so monitor and position are irrelevant; (2) NearestNeighbor OCR upscaling for scale/DPI tolerance; (3) anchoring the tree scan to the OCR-confirmed tab strip rather than fixed pixel offsets; and (4) `Normalize-PetrelWindow`, which restores a minimized window and maximizes it when it is smaller than ~1200x800, so a too-small or oddly-sized window (the failure that broke a run at 1950x1230 vs 1536x895) self-heals to a deterministic layout before any scan.

What is NOT achievable: a genuinely titled/structured handle on the Explorer tree items - Petrel does not provide one. A structure-based file-dialog finder (match by a "File name" edit) was tried and reverted: the field is a ComboBox whose inner Edit is unnamed, so the match timed out and added ~18s. The Export-as dialog find therefore stays a short title probe plus a content scan, and its wall time is dominated by Petrel's own (variable) dialog-render time, not by the finder.

## Boundary

This is deterministic only under the calibrated Windows desktop state: same Petrel version, same project layout, same interactive user session, and visible Petrel window. If anchors or dialogs are not found, the tool stops. It must not invent alternate clicks.

For runtime export automation, prefer saved Workflow Editor commands and zero-GUI native/MCP tools. Use deterministic GUI workflows for donor capture and for export commands that are not yet mapped in native `.ptd` storage.
