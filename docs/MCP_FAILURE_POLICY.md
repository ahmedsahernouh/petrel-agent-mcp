# MCP Failure Policy

Every Petrel MCP tool is assigned a fail-closed policy. The policy does not make a tool safer by itself; it states what evidence is required before the result can be trusted, what can fail, and which fallback tier is allowed.

Policy source:

```text
D:\Computer\Code\Petrel_project\mcp\petrel_mcp_failure_policies.json
```

MCP query tool:

```text
petrel_tool_failure_policy
```

Example:

```json
{
  "tool_name": "petrel_run_deterministic_gui_workflow"
}
```

Every normal MCP tool response also includes:

```json
{
  "mcp_failure_policy": {
    "tier": "...",
    "fail_closed": true,
    "success_evidence": [],
    "critical_failures": [],
    "fallback_chain": [],
    "retry_policy": "..."
  }
}
```

The server also audits the returned result against generic gates and, for selected tools, tool-specific evidence gates:

```json
{
  "mcp_result_audit": {
    "status": "passed | failed",
    "failure_class": "",
    "evidence": [],
    "failures": [],
    "fallback_available": true,
    "next_safe_action": "..."
  }
}
```

The policy is the contract. The audit is the per-run enforcement summary. A tool result should not be treated as complete when `mcp_result_audit.status` is `failed`, even if the underlying process returned exit code `0`.

## Tiers

```text
planning_policy
status_read_only
zero_gui_file_processing
saved_workflow_cli
deterministic_gui
native_read_only
native_same_length_patch
validation_manifest
petrel_launch_project
```

Use the tiers in this order for new tool design:

```text
zero-GUI Python/direct file processing
zero-GUI Petrel Workflow Editor/native control
reusable deterministic GUI workflow
discovery or donor capture only
```

## Well Tops Example

`petrel_run_deterministic_gui_workflow` with `workflow_id=export_well_tops_ascii` is tier `deterministic_gui`.

Success requires:

```text
runner report status=passed
ui_driver_status captured
raw Petrel ASCII export exists
ASCII import report row_count > 0
manifest validation passed
```

The MCP audit currently enforces these concrete gates for `petrel_run_deterministic_gui_workflow`:

```text
execution_requested when execute=true
runner_report_loaded
runner_report_status_passed
ui_driver_exit_zero
raw_petrel_ascii_exists_nonempty
ascii_import_rows_gt_zero
manifest_validation_passed
postconditions_passed
```

Latest audited Well Tops run:

```text
MCP result audit: passed
Runner report: 07_workflows_reports\automation_runs\deterministic_gui_export_well_tops_ascii_20260706_053532.json
Raw ASCII: 02_wells\well_tops\well_tops_exportpilot_detgui_20260706_053532.txt
Rows parsed: 84
Validation: passed, rows=750, failed=0
```

Allowed fallback:

```text
1. Run petrel_export_well_tops_native_probe for zero-GUI evidence.
2. Import an already-saved Petrel ASCII file.
3. Author a Petrel Workflow Editor donor command and move the task to native control.
```

It must not retry blind clicks. A retry is allowed only after a specific failed anchor is corrected or a calibrated GUI profile is updated from screenshot and trace evidence.

## Native Workflow Audit Gates

Native Workflow Editor tools are split into two audit modes:

```text
native_read_only:
  map/snapshot/compare/analyzer report path exists
  report is loadable when JSON is expected
  command analyzers find at least one mapped native record
  command clone-readiness analysis may pass audit with clone_safe=false
  command clone-recipe extraction may pass audit with recipe_safe_to_apply=false
  no native store mutation is required

native_same_length_patch low-level tools:
  patch report exists and is loadable
  target store and backup store exist
  expected/replacement values have the same ASCII byte length
  hashes are recorded
  dry-run reports must not change the hash
  applied low-level patches remain incomplete until Petrel runtime validation is supplied

native_same_length_patch patch-run-restore wrappers:
  runner report status=passed
  patch report exists
  before/after-patch snapshots exist
  patch compare shows a changed store
  Petrel workflow execution is confirmed unless skip_run=true
  target SEG-Y output or changed SystemCmd bridge proof is observed
  validation summary passes when validation is requested
  restore report and clean restore compare exist unless keep_patch=true
```

The low-level `petrel_native_patch_string` and `petrel_native_patch_offset` tools are safe primitives, not full export proofs. A dry-run can pass the audit. An applied low-level patch without a Petrel run should keep `mcp_result_audit.status=failed` with `runtime_validation_missing`; use `petrel_export_segy_filename_patch`, `petrel_export_segy_token_patch`, or `petrel_export_systemcmd_token_patch` for a complete patch-run-restore proof.

For `petrel_analyze_workflow_command_clone_readiness`, an audit pass means the readiness report exists, is loadable, found native records, and wrote its CSV evidence. It is not authorization to patch. The current expected result is `clone_safe=false` and `status=blocked` until the analyzer's blocking gates are cleared.

For `petrel_analyze_workflow_clone_side_effects`, an audit pass means the side-effect report exists, is loadable, classified donor diff ranges, wrote range/summary/action/gate CSV evidence, and explicitly reported whether side effects are isolated. It is not authorization to patch. The current expected result is `side_effects_isolated=false` and `status=blocked` until Data.ptd index/page churn, neighbor-record semantics, and Model.ptd UI/object-reference updates are mapped.

For `petrel_analyze_workflow_clone_storage_blocks`, an audit pass means the storage block report exists, is loadable, wrote segment/summary/action/gate CSV evidence, and explicitly reported whether command payload bytes were separated from store-growth bytes. It is not authorization to patch. The current expected result is `storage_payload_separated=true`, `clone_patch_precondition_satisfied=false`, and `status=blocked` until neighbor records, Data.ptd index/page churn, and Model.ptd UI/object-reference updates are mapped.

For `petrel_extract_workflow_command_clone_recipe`, an audit pass means the recipe report exists, is loadable, found added donor command records, and wrote candidate payload, payload-mutation, side-effect summary, payload-signal, negative-control, and gate evidence. It is not authorization to patch. The current expected result is `recipe_safe_to_apply=false` and `recipe_status=blocked` until side-effect isolation, BXML semantics, index/reference semantics, GUID/tag behavior, and applied-clone recovery gates are cleared.

## Promotion Rule

A tool cannot move to a lower-risk tier by documentation alone. Promotion requires evidence:

```text
deterministic_gui -> saved_workflow_cli:
  Petrel-authored donor command exists, can run from CLI, and writes validated files.

saved_workflow_cli -> native_same_length_patch:
  exact bytes/offsets are mapped, same-length mutation is proven, and restore compare is clean.

native_same_length_patch -> zero_gui_file_processing:
  the output can be produced without launching Petrel and without mutating native stores.
```

If the evidence is missing, the policy must report `partial`, `design_draft`, or `needs_attention`; it must not call the export complete.

## `petrel_run_mvp` Is Safe By Default Since Server 0.7.0

Before server `0.7.0`, `petrel_run_mvp`'s `dry_run` and `validate_only` flags both defaulted to `false`, so a bare call launched Petrel and executed the saved `ExportPiloX` workflow for real — the sharpest accidental-launch risk in the tool surface. As of `0.7.0`, `dry_run` defaults to `true` (applied server-side, so clients that omit the argument get the safe behavior); a live Petrel run requires an explicit `dry_run=false`.

The tool description and `mcp/petrel_mcp_failure_policies.json` state this, and `scripts\test_petrel_mcp_server.py` asserts both the safe schema default and the description text. Pass `dry_run=false` only when a live run is deliberately required against the prepared automation copy.
