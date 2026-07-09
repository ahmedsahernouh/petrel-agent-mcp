#!/usr/bin/env python3
"""Smoke-test the no-Ocean Petrel MCP stdio server without launching Petrel."""

from __future__ import annotations

import json
import importlib.util
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SERVER = REPO_ROOT / "mcp" / "petrel_mcp_server.py"


def send(proc: subprocess.Popen[str], message: dict) -> dict:
    assert proc.stdin is not None
    assert proc.stdout is not None
    proc.stdin.write(json.dumps(message) + "\n")
    proc.stdin.flush()
    line = proc.stdout.readline()
    if not line:
        stderr = proc.stderr.read() if proc.stderr else ""
        raise RuntimeError(f"Server produced no response. stderr={stderr}")
    return json.loads(line)


def main() -> int:
    proc = subprocess.Popen(
        [sys.executable, str(SERVER)],
        cwd=str(REPO_ROOT),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        init = send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "smoke", "version": "0"}},
            },
        )
        assert init["result"]["serverInfo"]["name"] == "petrel-no-ocean-control"

        tools = send(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        tool_names = {tool["name"] for tool in tools["result"]["tools"]}
        required = {
            "petrel_agent_readiness",
            "petrel_tool_creation_hierarchy",
            "petrel_tool_failure_policy",
            "petrel_status",
            "petrel_prepare_mvp",
            "petrel_run_mvp",
            "petrel_open_project",
            "petrel_export_native_zero_gui",
            "petrel_run_zero_gui_export_mvp",
            "petrel_export_native_semantic_zero_gui",
            "petrel_export_well_tables_zero_gui",
            "petrel_export_well_tops_native_probe",
            "petrel_import_gui_well_tops_table",
            "petrel_export_well_logs_ui",
            "petrel_export_well_tops_ui",
            "petrel_run_deterministic_gui_workflow",
            "petrel_register_and_validate",
            "petrel_native_map_workflow",
            "petrel_native_snapshot",
            "petrel_native_compare_snapshots",
            "petrel_native_patch_string",
            "petrel_native_patch_offset",
            "petrel_export_segy_filename_patch",
            "petrel_export_segy_token_patch",
            "petrel_analyze_exportseismiccmd_records",
            "petrel_export_systemcmd_token_patch",
            "petrel_analyze_systemcmd_records",
            "petrel_analyze_workflow_command_clone_readiness",
            "petrel_analyze_workflow_clone_side_effects",
            "petrel_analyze_workflow_clone_storage_blocks",
            "petrel_extract_workflow_command_clone_recipe",
            "petrel_generate_workflow_from_okf",
            "petrel_validate_workflow_coverage",
            "petrel_query_kb",
            "petrel_export_surfaces_zero_gui",
            "petrel_survey_geometry",
            "petrel_grid_convert",
            "petrel_export_seismic_zgy_zero_gui",
            "petrel_write_well_tops_ascii",
            "petrel_las_convert",
            "petrel_project_audit_report",
        }
        missing = required - tool_names
        assert not missing, f"Missing tools: {sorted(missing)}"
        for tool in tools["result"]["tools"]:
            properties = tool["inputSchema"].get("properties", {})
            for field in ("petrel_version", "version_scope", "target_versions"):
                assert field in properties, f"{tool['name']} is missing version-aware input {field}"

        # Every registered tool must carry an explicit failure-policy entry, and the policy file
        # must not reference tools that no longer exist. A silent default-policy fallback hides
        # the tool's real tier and evidence contract from agents.
        policy_config = json.loads(
            (REPO_ROOT / "mcp" / "petrel_mcp_failure_policies.json").read_text(encoding="utf-8-sig")
        )
        tool_policies = policy_config["tool_policies"]
        policy_templates = policy_config["policy_templates"]
        missing_policy = tool_names - set(tool_policies)
        assert not missing_policy, f"Tools without an explicit failure policy entry: {sorted(missing_policy)}"
        stale_policy = set(tool_policies) - tool_names
        assert not stale_policy, f"Failure policy entries for unregistered tools: {sorted(stale_policy)}"

        # Generalized safe-defaults audit: risky boolean flags must default to false on every
        # tool, and any tool whose policy expects a Petrel process must be impossible to fire
        # blind - it needs a launch/execute gate defaulting false, required inputs that force
        # deliberate use, or an explicit WARNING in its description.
        risky_flags = {"launch", "execute", "writable", "wait", "apply", "keep_patch", "open_project_writable"}
        by_name = {tool["name"]: tool for tool in tools["result"]["tools"]}
        for tool in tools["result"]["tools"]:
            name = tool["name"]
            properties = tool["inputSchema"].get("properties", {})
            for field in sorted(risky_flags & set(properties)):
                spec = properties[field]
                if spec.get("type") == "boolean":
                    assert spec.get("default") is False, (
                        f"{name}.{field} must default to false so Petrel launch/GUI/mutation "
                        f"never happens without an explicit opt-in"
                    )
            resolved_policy = dict(policy_templates.get(tool_policies[name].get("template", ""), {}))
            resolved_policy.update({k: v for k, v in tool_policies[name].items() if k != "template"})
            if resolved_policy.get("petrel_process_expected"):
                has_gate = any(
                    properties.get(field, {}).get("type") == "boolean"
                    and properties[field].get("default") is False
                    for field in ("launch", "execute")
                )
                has_required = bool(tool["inputSchema"].get("required"))
                has_warning = "WARNING" in tool["description"]
                assert has_gate or has_required or has_warning, (
                    f"{name} expects a Petrel process but a bare call could fire it blind: "
                    f"add a launch/execute gate defaulting false, required inputs, or a WARNING "
                    f"in the tool description"
                )

        run_mvp_props = by_name["petrel_run_mvp"]["inputSchema"]["properties"]
        assert run_mvp_props["dry_run"].get("default") is True, (
            "petrel_run_mvp must stay safe-by-default (dry_run defaults true since 0.7.0); "
            "a live Petrel run requires an explicit dry_run=false"
        )
        assert "dry_run" in by_name["petrel_run_mvp"]["description"], (
            "petrel_run_mvp's description must keep explaining the dry_run default and the "
            "explicit dry_run=false requirement for live runs"
        )

        # On a fresh clone the default export package under build/ does not exist
        # (build/ is gitignored). Fall back to the synthetic mini fixture so the
        # petrel_status code path is still exercised end-to-end.
        status_args: dict = {}
        status = send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "petrel_status", "arguments": status_args},
            },
        )
        if "error" in status:
            fixture_package = REPO_ROOT / "tests" / "fixtures" / "export_package_mini"
            status_args = {"export_package": str(fixture_package)}
            print("NOTE: default export package absent (fresh clone); using mini fixture package")
            status = send(
                proc,
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {"name": "petrel_status", "arguments": status_args},
                },
            )
        text = status["result"]["content"][0]["text"]
        payload = json.loads(text)
        assert payload["readiness"]["no_ocean_path"] is True
        assert "manifest" in payload
        assert payload["version_context"]["petrel_version"] == "2018.2.0.5333"
        assert payload["mcp_failure_policy"]["tier"] == "status_read_only"
        assert payload["mcp_failure_policy"]["fail_closed"] is True
        assert payload["mcp_result_audit"]["status"] == "passed"
        assert payload["mcp_result_audit"]["tier"] == "status_read_only"

        # petrel_status is a recommended first call for agents, so its default response must
        # stay compact: manifest counts plus a bounded row preview, never the full row list.
        manifest_summary = payload["manifest"]
        assert "rows" not in manifest_summary, "default petrel_status must not inline all manifest rows"
        assert len(manifest_summary["rows_preview"]) <= 10
        assert manifest_summary["rows_omitted"] == manifest_summary["row_count"] - len(manifest_summary["rows_preview"])
        assert len(text.encode("utf-8")) < 65536, (
            f"default petrel_status response is {len(text.encode('utf-8'))} bytes; "
            f"it must stay well under agent context limits"
        )

        full_status = send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 20,
                "method": "tools/call",
                "params": {"name": "petrel_status", "arguments": {**status_args, "include_manifest_rows": True}},
            },
        )
        full_payload = json.loads(full_status["result"]["content"][0]["text"])
        assert len(full_payload["manifest"]["rows"]) == full_payload["manifest"]["row_count"]

        readiness = send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 14,
                "method": "tools/call",
                "params": {"name": "petrel_agent_readiness", "arguments": {}},
            },
        )
        readiness_payload = json.loads(readiness["result"]["content"][0]["text"])
        assert readiness_payload["status"] == "ready_local_agent_surface"
        assert readiness_payload["tool_counts"]["missing_from_server"] == 0
        assert "petrel_export_well_tops_native_probe" in readiness_payload["tool_maturity"]["stable"]["tools"]

        hierarchy = send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "petrel_tool_creation_hierarchy", "arguments": {}},
            },
        )
        hierarchy_payload = json.loads(hierarchy["result"]["content"][0]["text"])
        assert hierarchy_payload["hierarchy"]["tiers"][0]["id"] == "zero_gui_python"
        assert hierarchy_payload["hierarchy"]["tiers"][1]["id"] == "zero_gui_petrel_workflow_editor"
        assert hierarchy_payload["mcp_failure_policy"]["tier"] == "planning_policy"
        assert hierarchy_payload["mcp_result_audit"]["status"] == "passed"

        policy = send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 7,
                "method": "tools/call",
                "params": {
                    "name": "petrel_tool_failure_policy",
                    "arguments": {"tool_name": "petrel_run_deterministic_gui_workflow"},
                },
            },
        )
        policy_payload = json.loads(policy["result"]["content"][0]["text"])
        assert policy_payload["policy"]["tier"] == "deterministic_gui"
        assert "raw Petrel ASCII export exists" in policy_payload["policy"]["success_evidence"]
        assert policy_payload["mcp_failure_policy"]["tier"] == "planning_policy"
        assert policy_payload["mcp_result_audit"]["status"] == "passed"

        # The deterministic GUI dry-run and the native-store analyzers need the Petrel
        # demo project automation copy (machine-local, not in git). The dry-run
        # fail-closes without it, which is correct tool behavior but not a test failure.
        native_evidence = (REPO_ROOT / "Petrel_DemoData_project").exists()
        if not native_evidence:
            print("SKIP: deterministic GUI dry-run assertions (Petrel demo project not present on this machine)")
        else:
            deterministic_dry_run = send(
                proc,
                {
                    "jsonrpc": "2.0",
                    "id": 8,
                    "method": "tools/call",
                    "params": {
                        "name": "petrel_run_deterministic_gui_workflow",
                        "arguments": {"workflow_id": "export_well_tops_ascii", "timeout_seconds": 60},
                    },
                },
            )
            deterministic_payload = json.loads(deterministic_dry_run["result"]["content"][0]["text"])
            assert deterministic_payload["execute"] is False
            assert deterministic_payload["mcp_failure_policy"]["tier"] == "deterministic_gui"
            assert deterministic_payload["mcp_result_audit"]["status"] == "passed"
            assert any(
                item["id"] == "execution_requested" and item["status"] == "skipped"
                for item in deterministic_payload["mcp_result_audit"]["evidence"]
            )

        if not native_evidence:
            print("SKIP: native-store analyzer assertions (Petrel demo project not present on this machine)")
        else:
            systemcmd_map = send(
                proc,
                {
                    "jsonrpc": "2.0",
                    "id": 9,
                    "method": "tools/call",
                    "params": {
                        "name": "petrel_analyze_systemcmd_records",
                        "arguments": {},
                    },
                },
            )
            systemcmd_payload = json.loads(systemcmd_map["result"]["content"][0]["text"])
            assert systemcmd_payload["mcp_failure_policy"]["tier"] == "native_read_only"
            assert systemcmd_payload["mcp_result_audit"]["status"] == "passed"
            assert any(
                item["id"] == "native_records_found" and item["status"] == "passed"
                for item in systemcmd_payload["mcp_result_audit"]["evidence"]
            )

            clone_readiness = send(
                proc,
                {
                    "jsonrpc": "2.0",
                    "id": 10,
                    "method": "tools/call",
                    "params": {
                        "name": "petrel_analyze_workflow_command_clone_readiness",
                        "arguments": {},
                    },
                },
            )
            clone_payload = json.loads(clone_readiness["result"]["content"][0]["text"])
            assert clone_payload["clone_safe"] is False
            assert clone_payload["clone_status"] == "blocked"
            assert clone_payload["clone_blocker_count"] >= 1
            assert clone_payload["mcp_failure_policy"]["tier"] == "native_read_only"
            assert clone_payload["mcp_result_audit"]["status"] == "passed"
            assert any(
                item["id"] == "clone_readiness_evaluated" and item["status"] == "passed"
                for item in clone_payload["mcp_result_audit"]["evidence"]
            )

            side_effects = send(
                proc,
                {
                    "jsonrpc": "2.0",
                    "id": 12,
                    "method": "tools/call",
                    "params": {
                        "name": "petrel_analyze_workflow_clone_side_effects",
                        "arguments": {},
                    },
                },
            )
            side_effect_payload = json.loads(side_effects["result"]["content"][0]["text"])
            assert side_effect_payload["side_effects_isolated"] is False
            assert side_effect_payload["clone_patch_precondition_satisfied"] is False
            assert side_effect_payload["side_effect_status"] == "blocked"
            assert side_effect_payload["side_effect_blocker_count"] >= 1
            assert side_effect_payload["side_effect_class_count"] >= 1
            assert side_effect_payload["required_action_count"] >= 1
            assert side_effect_payload["mcp_failure_policy"]["tier"] == "native_read_only"
            assert side_effect_payload["mcp_result_audit"]["status"] == "passed"
            assert any(
                item["id"] == "clone_side_effects_evaluated" and item["status"] == "passed"
                for item in side_effect_payload["mcp_result_audit"]["evidence"]
            )
            for evidence_id in (
                "clone_side_effect_ranges_csv_exists",
                "clone_side_effect_summary_csv_exists",
                "clone_side_effect_required_actions_csv_exists",
                "clone_side_effect_gates_csv_exists",
            ):
                assert any(
                    item["id"] == evidence_id and item["status"] == "passed"
                    for item in side_effect_payload["mcp_result_audit"]["evidence"]
                )

            storage_blocks = send(
                proc,
                {
                    "jsonrpc": "2.0",
                    "id": 13,
                    "method": "tools/call",
                    "params": {
                        "name": "petrel_analyze_workflow_clone_storage_blocks",
                        "arguments": {},
                    },
                },
            )
            storage_payload = json.loads(storage_blocks["result"]["content"][0]["text"])
            assert storage_payload["storage_payload_separated"] is True
            assert storage_payload["clone_patch_precondition_satisfied"] is False
            assert storage_payload["storage_block_status"] == "blocked"
            assert storage_payload["storage_blocker_count"] >= 1
            assert storage_payload["segment_class_count"] >= 1
            assert storage_payload["required_action_count"] >= 1
            assert storage_payload["mcp_failure_policy"]["tier"] == "native_read_only"
            assert storage_payload["mcp_result_audit"]["status"] == "passed"
            assert any(
                item["id"] == "clone_storage_blocks_evaluated" and item["status"] == "passed"
                for item in storage_payload["mcp_result_audit"]["evidence"]
            )
            for evidence_id in (
                "clone_storage_block_segments_csv_exists",
                "clone_storage_block_summary_csv_exists",
                "clone_storage_block_required_actions_csv_exists",
                "clone_storage_block_gates_csv_exists",
            ):
                assert any(
                    item["id"] == evidence_id and item["status"] == "passed"
                    for item in storage_payload["mcp_result_audit"]["evidence"]
                )

            clone_recipe = send(
                proc,
                {
                    "jsonrpc": "2.0",
                    "id": 11,
                    "method": "tools/call",
                    "params": {
                        "name": "petrel_extract_workflow_command_clone_recipe",
                        "arguments": {},
                    },
                },
            )
            recipe_payload = json.loads(clone_recipe["result"]["content"][0]["text"])
            assert recipe_payload["recipe_safe_to_apply"] is False
            assert recipe_payload["recipe_status"] == "blocked"
            assert recipe_payload["recipe_blocker_count"] >= 1
            assert recipe_payload["candidate_payload_count"] >= 2
            assert recipe_payload["payload_mutation_count"] >= 1
            assert recipe_payload["side_effect_class_count"] >= 1
            assert recipe_payload["payload_signal_count"] >= 1
            assert recipe_payload["negative_control_count"] >= 1
            assert recipe_payload["mcp_failure_policy"]["tier"] == "native_read_only"
            assert recipe_payload["mcp_result_audit"]["status"] == "passed"
            assert any(
                item["id"] == "clone_recipe_extracted" and item["status"] == "passed"
                for item in recipe_payload["mcp_result_audit"]["evidence"]
            )
            for evidence_id in (
                "clone_recipe_payload_mutations_csv_exists",
                "clone_recipe_side_effect_summary_csv_exists",
                "clone_recipe_payload_signals_csv_exists",
                "clone_recipe_negative_controls_csv_exists",
            ):
                assert any(
                    item["id"] == evidence_id and item["status"] == "passed"
                    for item in recipe_payload["mcp_result_audit"]["evidence"]
                )

        # Survey geometry is read-only and fast, but needs the machine-local donor
        # SEG-Y under the gitignored build/ package.
        segy_donor = (
            REPO_ROOT
            / "build" / "export_pilots" / "petrel2010_demo_project_export_20260701_060609"
            / "03_seismic" / "segy" / "orig_amp_exportpilot_donor.sgy"
        )
        if not segy_donor.exists():
            print("SKIP: survey-geometry assertions (donor SEG-Y not present on this machine)")
        else:
            survey = send(
                proc,
                {
                    "jsonrpc": "2.0",
                    "id": 21,
                    "method": "tools/call",
                    "params": {"name": "petrel_survey_geometry", "arguments": {}},
                },
            )
            survey_payload = json.loads(survey["result"]["content"][0]["text"])
            assert survey_payload["status"] == "passed"
            assert survey_payload["xlines_per_inline"] > 0
            assert "rotation_deg" in survey_payload
            assert survey_payload["corners"]["origin"]["x"] > 0
            assert survey_payload["mcp_result_audit"]["status"] == "passed"

        # Workflow generation retrieves from the agent index, which is generated
        # machine-local state (agent-index/ is gitignored).
        if not (REPO_ROOT / "agent-index").exists():
            print("SKIP: workflow-generation assertions (agent-index not built on this machine)")
        else:
            generated = send(
                proc,
                {
                    "jsonrpc": "2.0",
                    "id": 5,
                    "method": "tools/call",
                    "params": {
                        "name": "petrel_generate_workflow_from_okf",
                        "arguments": {
                            "workflow_goal": "Export Petrel project to universal formats",
                            "object_classes": ["well_log", "seismic_cube"],
                            "top_k": 2,
                        },
                    },
                },
            )
            generated_payload = json.loads(generated["result"]["content"][0]["text"])
            assert generated_payload["version_context"]["petrel_version"] == "2018.2.0.5333"
            assert generated_payload["workflow_scaffold"]["review_status"] == "design_draft"

        # Coverage validation asserts against the real export package manifest;
        # skip when the run fell back to the mini fixture (fresh clone).
        if status_args:
            print("SKIP: workflow-coverage assertions (real export package not present on this machine)")
        else:
            coverage = send(
                proc,
                {
                    "jsonrpc": "2.0",
                    "id": 6,
                    "method": "tools/call",
                    "params": {
                        "name": "petrel_validate_workflow_coverage",
                        "arguments": {"expected_object_types": ["well_log", "seismic_cube"]},
                    },
                },
            )
            coverage_payload = json.loads(coverage["result"]["content"][0]["text"])
            assert coverage_payload["status"] == "pass"
            assert coverage_payload["version_mismatch_count"] == 0

        spec = importlib.util.spec_from_file_location("petrel_mcp_server_for_test", SERVER)
        assert spec and spec.loader
        server_module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = server_module
        spec.loader.exec_module(server_module)

        fixtures_dir = REPO_ROOT / "tests" / "fixtures" / "native_edit_experiments"
        full_patch_report = fixtures_dir / "systemcmd_token_patch_export_report.json"
        full_patch_report_data = json.loads(full_patch_report.read_text(encoding="utf-8-sig"))
        full_patch_payload = {
            "operation": "export_systemcmd_token_patch",
            "exit_code": 0,
            "report_path": str(full_patch_report),
            "report": full_patch_report_data,
        }
        # The pass-audit checks paths referenced inside the report (snapshots, restore report),
        # which only exist on a machine that has run the original patch-run-restore experiment.
        # On a fresh clone the fixture report still loads, but the disk evidence is absent, so
        # skip the pass assertions rather than fail on missing generated outputs.
        patch_evidence_paths = [
            full_patch_report_data.get("before_snapshot"),
            full_patch_report_data.get("restore_report"),
        ]
        patch_evidence_present = all(item and Path(item).exists() for item in patch_evidence_paths)
        if patch_evidence_present:
            full_patch_audit = server_module.audit_tool_payload(
                "petrel_export_systemcmd_token_patch",
                full_patch_payload,
                server_module.failure_policy_summary("petrel_export_systemcmd_token_patch"),
            )
            assert full_patch_audit["status"] == "passed"
            assert any(
                item["id"] == "restore_clean" and item["status"] == "passed"
                for item in full_patch_audit["evidence"]
            )
        else:
            print("SKIP: patch-run-restore pass-audit (snapshot evidence not present on this machine)")

        raw_patch_report = fixtures_dir / "native_workflow_offset_patch_report.json"
        raw_patch_payload = {
            "operation": "native_patch_offset",
            "applied": True,
            "exit_code": 0,
            "report_path": str(raw_patch_report),
            "report": json.loads(raw_patch_report.read_text(encoding="utf-8-sig")),
        }
        raw_patch_audit = server_module.audit_tool_payload(
            "petrel_native_patch_offset",
            raw_patch_payload,
            server_module.failure_policy_summary("petrel_native_patch_offset"),
        )
        assert raw_patch_audit["status"] == "failed"
        assert any(
            item["id"] == "petrel_runtime_validation_present" and item["status"] == "failed"
            for item in raw_patch_audit["evidence"]
        )

        # Every tools/call above must have appended a parseable line to today's usage log.
        from datetime import datetime, timezone

        usage_log = (
            REPO_ROOT / "build" / "mcp_usage" / f"petrel_mcp_usage_{datetime.now(timezone.utc).strftime('%Y%m%d')}.jsonl"
        )
        assert usage_log.exists(), f"usage log missing: {usage_log}"
        usage_lines = usage_log.read_text(encoding="utf-8").strip().splitlines()
        assert usage_lines, "usage log is empty"
        last_record = json.loads(usage_lines[-1])
        assert last_record["tool"] in tool_names
        assert last_record["outcome"] in ("ok", "error")

        print("Petrel MCP smoke test passed")
        print(f"Tools: {', '.join(sorted(tool_names))}")
        print(f"Export package: {payload['export_package']}")
        print(f"Manifest rows: {payload['manifest']['row_count']}")
        print(f"Usage log: {usage_log} ({len(usage_lines)} calls logged)")
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
