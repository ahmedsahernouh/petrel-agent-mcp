#!/usr/bin/env python3
"""Classify Petrel Workflow Editor command-clone donor side effects.

This is a read-only analyzer. It consumes Petrel-authored before/after snapshot
compare reports and classifies changed byte ranges around the ExportSeismicCmd
donor insertions. It does not patch, clone, resize, or write Petrel native
stores.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import extract_petrel_workflow_command_clone_recipe as recipe_tools


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "build" / "native_edit_experiments"
DEFAULT_PROJECT_STEM = "Petrel2010 demo project ExportPilot"
DEFAULT_FIRST_DONOR_COMPARE = (
    DEFAULT_OUTPUT_ROOT / "native_workflow_snapshot_compare_20260703_012602" / "snapshot_compare_report.json"
)
DEFAULT_SECOND_DONOR_COMPARE = (
    DEFAULT_OUTPUT_ROOT / "native_workflow_snapshot_compare_20260703_054200" / "snapshot_compare_report.json"
)
DEFAULT_TERMS = recipe_tools.DEFAULT_TERMS


GROUP_RULES = {
    "inserted_command_core_record": {
        "isolation_group": "required_command_payload",
        "isolation_status": "mapped_required",
        "clone_relevance": "must_reproduce_or_template",
        "blocks_clone": False,
    },
    "coalesced_store_growth_block_containing_command_core": {
        "isolation_group": "mixed_command_payload_and_store_allocation_churn",
        "isolation_status": "partially_mapped_needs_split",
        "clone_relevance": "must_split_payload_from_store_growth",
        "blocks_clone": True,
    },
    "adjacent_extended_command_record": {
        "isolation_group": "required_neighbor_record_candidate",
        "isolation_status": "mapped_needs_semantics",
        "clone_relevance": "may_need_neighbor_record_or_dictionary_update",
        "blocks_clone": True,
    },
    "appended_store_growth_or_free_page_region": {
        "isolation_group": "store_allocation_churn",
        "isolation_status": "mapped_probably_ignorable",
        "clone_relevance": "likely_store_page_allocation",
        "blocks_clone": False,
    },
    "sqlite_header_or_page_allocation_metadata": {
        "isolation_group": "store_allocation_churn",
        "isolation_status": "mapped_probably_ignorable",
        "clone_relevance": "likely_store_page_allocation",
        "blocks_clone": False,
    },
    "pre_existing_data_store_page_or_index_churn": {
        "isolation_group": "data_store_index_or_page_churn",
        "isolation_status": "mapped_needs_semantics",
        "clone_relevance": "may_include_command_list_index_or_store_page_updates",
        "blocks_clone": True,
    },
    "model_store_header_or_root_record_churn": {
        "isolation_group": "model_store_header_churn",
        "isolation_status": "mapped_needs_semantics",
        "clone_relevance": "may_include root/index metadata",
        "blocks_clone": True,
    },
    "model_ui_tree_object_reference_or_layout_churn": {
        "isolation_group": "model_ui_object_reference_churn",
        "isolation_status": "mapped_needs_semantics",
        "clone_relevance": "likely workflow UI tree, object reference, or layout update",
        "blocks_clone": True,
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-stem", default=DEFAULT_PROJECT_STEM)
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--first-donor-compare-report", default=str(DEFAULT_FIRST_DONOR_COMPARE))
    parser.add_argument("--second-donor-compare-report", default=str(DEFAULT_SECOND_DONOR_COMPARE))
    parser.add_argument("--terms", default="|".join(DEFAULT_TERMS))
    parser.add_argument("--include-context", action="store_true")
    return parser.parse_args()


def enrich_side_effect_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for row in rows:
        rule = GROUP_RULES.get(str(row.get("classification")), {})
        item = dict(row)
        item["isolation_group"] = rule.get("isolation_group", "unknown")
        item["isolation_status"] = rule.get("isolation_status", "unknown_needs_manual_mapping")
        item["clone_relevance"] = rule.get("clone_relevance", "unknown")
        item["blocks_clone"] = bool(rule.get("blocks_clone", True))
        enriched.append(item)
    return enriched


def summarize_enriched(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (
            str(row["compare_label"]),
            str(row["store_file"]),
            str(row["isolation_group"]),
            str(row["isolation_status"]),
        )
        item = summary.setdefault(
            key,
            {
                "compare_label": row["compare_label"],
                "store_file": row["store_file"],
                "isolation_group": row["isolation_group"],
                "isolation_status": row["isolation_status"],
                "clone_relevance": row["clone_relevance"],
                "blocks_clone": row["blocks_clone"],
                "range_count": 0,
                "total_bytes": 0,
                "first_offset": row["start_offset"],
                "last_offset": row["end_offset"],
            },
        )
        item["range_count"] += 1
        item["total_bytes"] += int(row.get("length") or 0)
        item["blocks_clone"] = bool(item["blocks_clone"]) or bool(row.get("blocks_clone"))
        item["first_offset"] = min(int(item["first_offset"]), int(row["start_offset"]))
        item["last_offset"] = max(int(item["last_offset"]), int(row["end_offset"]))
    return sorted(summary.values(), key=lambda row: (row["compare_label"], row["store_file"], row["isolation_group"]))


def gate(gates: list[dict[str, Any]], gate_id: str, status: str, detail: Any, blocker: bool) -> None:
    gates.append({"id": gate_id, "status": status, "detail": detail, "blocker": bool(blocker)})


def build_required_actions(summary_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    by_group = {str(row["isolation_group"]) for row in summary_rows if bool(row.get("blocks_clone"))}
    action_map = {
        "mixed_command_payload_and_store_allocation_churn": (
            "split_command_payload_from_store_growth",
            "Separate the command core bytes from allocator/page-growth bytes before any dry-run clone can be trusted.",
        ),
        "required_neighbor_record_candidate": (
            "map_neighbor_record_semantics",
            "Decide whether the following BXML/LZ4 record is a required dictionary/path-token record or Petrel store churn.",
        ),
        "data_store_index_or_page_churn": (
            "map_data_store_index_and_command_list_updates",
            "Identify whether pre-existing Data.ptd churn contains command-list indexes or only store/page metadata.",
        ),
        "model_store_header_churn": (
            "map_model_store_header_updates",
            "Identify whether Model.ptd header/root bytes are required for workflow UI/object registration.",
        ),
        "model_ui_object_reference_churn": (
            "map_model_ui_object_reference_updates",
            "Map workflow UI tree, object reference, and layout updates before any clone writes Model.ptd.",
        ),
        "unknown": (
            "classify_unknown_side_effects",
            "Classify all unknown changed ranges before any clone patcher is allowed to write.",
        ),
    }
    for group in sorted(by_group):
        action_id, description = action_map.get(
            group,
            (f"map_{group}", f"Map side-effect group {group} before applying a clone."),
        )
        actions.append(
            {
                "action_id": action_id,
                "isolation_group": group,
                "description": description,
                "required_before_clone_write": True,
            }
        )
    return actions


def build_analysis(
    first: dict[str, Any],
    second: dict[str, Any],
    payloads: list[dict[str, Any]],
    side_effect_rows: list[dict[str, Any]],
    side_effect_summary: list[dict[str, Any]],
    required_actions: list[dict[str, Any]],
) -> dict[str, Any]:
    gates: list[dict[str, Any]] = []
    donor_loaded = first.get("loaded") and second.get("loaded")
    gate(
        gates,
        "donor_compare_reports_loaded",
        "passed" if donor_loaded else "failed",
        {"first": first.get("path"), "second": second.get("path")},
        blocker=not donor_loaded,
    )
    gate(
        gates,
        "added_command_payloads_mapped",
        "passed" if len(payloads) >= 2 else "failed",
        {"payload_count": len(payloads), "command_offsets": [row.get("command_offset") for row in payloads]},
        blocker=len(payloads) < 2,
    )
    unknown_rows = [row for row in side_effect_rows if row.get("isolation_group") == "unknown"]
    gate(
        gates,
        "all_side_effect_ranges_classified",
        "passed" if not unknown_rows and side_effect_rows else "failed",
        {"unknown_range_count": len(unknown_rows), "classified_range_count": len(side_effect_rows) - len(unknown_rows)},
        blocker=bool(unknown_rows) or not side_effect_rows,
    )
    blocking_groups = sorted({str(row["isolation_group"]) for row in side_effect_summary if bool(row.get("blocks_clone"))})
    gate(
        gates,
        "side_effects_fully_isolated_for_clone",
        "passed" if not blocking_groups else "failed",
        {"blocking_groups": blocking_groups},
        blocker=bool(blocking_groups),
    )
    data_blocking = [
        row
        for row in side_effect_summary
        if row.get("store_file") == "Data.ptd" and bool(row.get("blocks_clone"))
    ]
    gate(
        gates,
        "data_store_side_effect_semantics_validated",
        "passed" if not data_blocking else "failed",
        data_blocking,
        blocker=bool(data_blocking),
    )
    model_blocking = [
        row
        for row in side_effect_summary
        if row.get("store_file") == "Model.ptd" and bool(row.get("blocks_clone"))
    ]
    gate(
        gates,
        "model_store_side_effect_semantics_validated",
        "passed" if not model_blocking else "failed",
        model_blocking,
        blocker=bool(model_blocking),
    )
    model_edit_likely_required = any(row.get("store_file") == "Model.ptd" for row in side_effect_summary)
    gate(
        gates,
        "model_edit_requirement_decided",
        "failed" if model_edit_likely_required else "passed",
        {
            "model_edit_likely_required_for_donor_authoring": model_edit_likely_required,
            "decision": "not_safe_to_skip_model_ptd_until_semantics_mapped" if model_edit_likely_required else "model_ptd_not_touched",
        },
        blocker=model_edit_likely_required,
    )
    gate(
        gates,
        "required_actions_written",
        "passed" if required_actions else "failed",
        {"required_action_count": len(required_actions)},
        blocker=not bool(required_actions),
    )
    blocker_count = sum(1 for row in gates if row["status"] != "passed" and row.get("blocker"))
    failed_count = sum(1 for row in gates if row["status"] != "passed")
    return {
        "side_effects_isolated": blocker_count == 0,
        "clone_patch_precondition_satisfied": blocker_count == 0,
        "status": "ready" if blocker_count == 0 else "blocked",
        "blocker_count": blocker_count,
        "failed_gate_count": failed_count,
        "gates": gates,
        "blocking_groups": blocking_groups,
        "model_edit_likely_required": model_edit_likely_required,
        "not_supported_yet": [
            "ignoring Model.ptd changes",
            "applying a command clone",
            "rewriting command-list/index records",
            "rewriting workflow UI/object-reference records",
        ],
        "next_required_evidence": [row["description"] for row in required_actions],
    }


def main() -> int:
    args = parse_args()
    terms = [term for term in args.terms.split("|") if term]
    first = recipe_tools.load_compare(
        Path(args.first_donor_compare_report).resolve(),
        "first_donor",
        args.project_stem,
        terms,
        bool(args.include_context),
    )
    second = recipe_tools.load_compare(
        Path(args.second_donor_compare_report).resolve(),
        "second_donor",
        args.project_stem,
        terms,
        bool(args.include_context),
    )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = Path(args.output_root).resolve() / f"workflow_clone_side_effects_{stamp}"
    report_dir.mkdir(parents=True, exist_ok=True)

    first_payloads, first_payload_rows = recipe_tools.extract_payloads(first, report_dir)
    second_payloads, second_payload_rows = recipe_tools.extract_payloads(second, report_dir)
    payloads = first_payloads + second_payloads
    payload_rows = first_payload_rows + second_payload_rows

    raw_rows = recipe_tools.build_side_effect_rows(first, payloads) + recipe_tools.build_side_effect_rows(second, payloads)
    side_effect_rows = enrich_side_effect_rows(raw_rows)
    side_effect_summary = summarize_enriched(side_effect_rows)
    required_actions = build_required_actions(side_effect_summary)
    analysis = build_analysis(first, second, payloads, side_effect_rows, side_effect_summary, required_actions)

    first.pop("_after_data_bytes", None)
    first.pop("_before_data_bytes", None)
    second.pop("_after_data_bytes", None)
    second.pop("_before_data_bytes", None)

    payloads_csv = report_dir / "clone_side_effect_candidate_payloads.csv"
    ranges_csv = report_dir / "clone_side_effect_ranges.csv"
    summary_csv = report_dir / "clone_side_effect_summary.csv"
    actions_csv = report_dir / "clone_side_effect_required_actions.csv"
    gates_csv = report_dir / "clone_side_effect_gates.csv"
    report_json = report_dir / "workflow_clone_side_effects.json"
    summary_md = report_dir / "workflow_clone_side_effects_summary.md"

    recipe_tools.write_csv(
        payloads_csv,
        payload_rows,
        [
            "compare_label",
            "added_record_index",
            "command_offset",
            "core_start",
            "core_end",
            "core_length",
            "core_sha256",
            "core_payload_file",
            "extended_start",
            "extended_end",
            "extended_length",
            "extended_sha256",
            "extended_payload_file",
            "previous_lz4_offset",
            "previous_bxml_offset",
            "next_bxml_offset",
            "next_lz4_offset",
            "next_next_bxml_offset",
            "next_record_header_start",
            "next_record_bxml_start",
            "command_span_to_next_bxml",
            "lz4_length_field_offset",
            "lz4_length_field_value",
            "core_length_minus_lz4_length_value",
            "before_region_state",
            "before_region_available_bytes",
            "before_region_nonzero_bytes",
            "data_diff_ranges_overlapping_core",
            "data_diff_bytes_overlapping_core",
            "data_diff_ranges_outside_core",
            "data_diff_bytes_outside_core",
            "data_diff_ranges_overlapping_extended",
            "data_diff_bytes_overlapping_extended",
            "hex_preview_first_64",
        ],
    )
    recipe_tools.write_csv(
        ranges_csv,
        side_effect_rows,
        [
            "compare_label",
            "store_file",
            "start_offset",
            "end_offset",
            "length",
            "classification",
            "isolation_group",
            "isolation_status",
            "clone_relevance",
            "blocks_clone",
            "nearest_added_core_distance",
        ],
    )
    recipe_tools.write_csv(
        summary_csv,
        side_effect_summary,
        [
            "compare_label",
            "store_file",
            "isolation_group",
            "isolation_status",
            "clone_relevance",
            "blocks_clone",
            "range_count",
            "total_bytes",
            "first_offset",
            "last_offset",
        ],
    )
    recipe_tools.write_csv(
        actions_csv,
        required_actions,
        ["action_id", "isolation_group", "description", "required_before_clone_write"],
    )
    gate_rows = [
        {
            "id": row["id"],
            "status": row["status"],
            "blocker": row["blocker"],
            "detail_json": json.dumps(row.get("detail"), ensure_ascii=False),
        }
        for row in analysis["gates"]
    ]
    recipe_tools.write_csv(gates_csv, gate_rows, ["id", "status", "blocker", "detail_json"])

    report = {
        "created_at_utc": recipe_tools.utc_now(),
        "operation": "analyze_workflow_clone_side_effects",
        "command_type": "ExportSeismicCmd",
        "project_stem": args.project_stem,
        "first_donor_compare": first,
        "second_donor_compare": second,
        "candidate_payloads": payloads,
        "side_effect_summary": side_effect_summary,
        "required_actions": required_actions,
        "analysis": analysis,
        "payloads_csv": str(payloads_csv),
        "ranges_csv": str(ranges_csv),
        "summary_csv": str(summary_csv),
        "required_actions_csv": str(actions_csv),
        "gates_csv": str(gates_csv),
        "payload_directory": str(report_dir / "candidate_payloads"),
    }
    report_json.write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines = [
        "# Workflow Clone Side-Effect Analysis",
        "",
        f"- Created UTC: {report['created_at_utc']}",
        f"- Status: {analysis['status']}",
        f"- Side effects isolated: {analysis['side_effects_isolated']}",
        f"- Clone patch precondition satisfied: {analysis['clone_patch_precondition_satisfied']}",
        f"- Blockers: {analysis['blocker_count']}",
        f"- Candidate payloads: {len(payloads)}",
        "",
        "## Isolation Groups",
        "",
        "| Donor | Store | Group | Status | Ranges | Bytes | Blocks Clone |",
        "| --- | --- | --- | --- | ---: | ---: | --- |",
    ]
    for row in side_effect_summary:
        lines.append(
            f"| {row['compare_label']} | {row['store_file']} | {row['isolation_group']} | "
            f"{row['isolation_status']} | {row['range_count']} | {row['total_bytes']} | {row['blocks_clone']} |"
        )
    lines.extend(["", "## Gates", ""])
    for row in analysis["gates"]:
        marker = "BLOCKER" if row.get("blocker") and row["status"] != "passed" else "INFO"
        lines.append(f"- {row['status']}: {row['id']} [{marker}]")
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "This analyzer is read-only. It classifies existing donor snapshot diffs and writes evidence files only under the report directory.",
            "A blocked result means a command-clone patcher must not write Petrel native stores yet.",
            "",
            "## Outputs",
            "",
            f"- JSON: {report_json}",
            f"- Payloads CSV: {payloads_csv}",
            f"- Ranges CSV: {ranges_csv}",
            f"- Summary CSV: {summary_csv}",
            f"- Required actions CSV: {actions_csv}",
            f"- Gates CSV: {gates_csv}",
        ]
    )
    summary_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("Workflow clone side-effect analysis complete")
    print(f"Status: {analysis['status']}")
    print(f"Side effects isolated: {analysis['side_effects_isolated']}")
    print(f"Clone patch precondition satisfied: {analysis['clone_patch_precondition_satisfied']}")
    print(f"Blockers: {analysis['blocker_count']}")
    print(f"Report: {report_json}")
    print(f"Summary: {summary_md}")
    print(f"Ranges: {ranges_csv}")
    print(f"Side-effect summary: {summary_csv}")
    print(f"Required actions: {actions_csv}")
    print(f"Gates: {gates_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
