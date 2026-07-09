#!/usr/bin/env python3
"""Split Petrel Workflow Editor command-clone storage blocks.

This is a read-only analyzer. It consumes Petrel-authored before/after
snapshot compare reports and separates inserted ExportSeismicCmd command
payload bytes from surrounding Data.ptd store-growth or page-churn bytes.
It does not patch, clone, resize, or write Petrel native stores.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import analyze_petrel_workflow_clone_side_effects as side_effect_tools
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


DATA_SEGMENT_RULES: dict[str, dict[str, Any]] = {
    "required_command_core_payload": {
        "storage_role": "command_payload",
        "isolation_status": "mapped_required",
        "clone_relevance": "must_reproduce_or_template",
        "blocks_clone": False,
    },
    "store_growth_before_command_core": {
        "storage_role": "allocator_or_page_growth",
        "isolation_status": "split_from_payload_probably_ignorable",
        "clone_relevance": "likely store allocation before inserted payload",
        "blocks_clone": False,
    },
    "store_growth_after_command_core": {
        "storage_role": "allocator_or_page_growth",
        "isolation_status": "split_from_payload_probably_ignorable",
        "clone_relevance": "likely store allocation after inserted payload",
        "blocks_clone": False,
    },
    "store_growth_or_free_page_region": {
        "storage_role": "allocator_or_page_growth",
        "isolation_status": "mapped_probably_ignorable",
        "clone_relevance": "likely store page allocation",
        "blocks_clone": False,
    },
    "sqlite_header_or_page_allocation_metadata": {
        "storage_role": "allocator_or_page_metadata",
        "isolation_status": "mapped_probably_ignorable",
        "clone_relevance": "likely store page metadata",
        "blocks_clone": False,
    },
    "neighbor_or_extended_record_overlap": {
        "storage_role": "neighbor_or_extended_payload",
        "isolation_status": "mapped_needs_semantics",
        "clone_relevance": "may need following BXML/LZ4 record or dictionary/path-token update",
        "blocks_clone": True,
    },
    "data_store_index_or_page_churn": {
        "storage_role": "data_store_index_or_page_churn",
        "isolation_status": "mapped_needs_semantics",
        "clone_relevance": "may include command-list indexes or store/page metadata",
        "blocks_clone": True,
    },
    "near_inserted_command_neighbor_record": {
        "storage_role": "near_inserted_command_neighbor",
        "isolation_status": "mapped_needs_semantics",
        "clone_relevance": "may include command-list or neighbor-record updates",
        "blocks_clone": True,
    },
    "model_store_header_churn": {
        "storage_role": "model_store_header_or_root",
        "isolation_status": "mapped_needs_semantics",
        "clone_relevance": "may include Model.ptd root/index metadata",
        "blocks_clone": True,
    },
    "model_ui_object_reference_churn": {
        "storage_role": "model_ui_tree_or_object_reference",
        "isolation_status": "mapped_needs_semantics",
        "clone_relevance": "likely workflow UI tree, object reference, or layout update",
        "blocks_clone": True,
    },
    "unknown_storage_block": {
        "storage_role": "unknown",
        "isolation_status": "unknown_needs_manual_mapping",
        "clone_relevance": "unknown",
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


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def overlaps(start: int, end: int, other_start: int, other_end: int) -> bool:
    return start < other_end and end > other_start


def payload_for_range(
    compare_label: str,
    start: int,
    end: int,
    payloads: list[dict[str, Any]],
) -> dict[str, Any] | None:
    for payload in payloads:
        if payload.get("compare_label") != compare_label:
            continue
        core_start = as_int(payload.get("core_start"))
        core_end = as_int(payload.get("core_end"))
        extended_start = as_int(payload.get("extended_start"))
        extended_end = as_int(payload.get("extended_end"))
        if overlaps(start, end, extended_start, extended_end) or overlaps(start, end, core_start, core_end):
            return payload
    return None


def payload_for_segment_or_source(
    compare_label: str,
    segment_start: int,
    segment_end: int,
    source_start: int,
    source_end: int,
    payloads: list[dict[str, Any]],
) -> dict[str, Any] | None:
    return payload_for_range(compare_label, segment_start, segment_end, payloads) or payload_for_range(
        compare_label,
        source_start,
        source_end,
        payloads,
    )


def split_points_for_row(row: dict[str, Any], payloads: list[dict[str, Any]]) -> list[int]:
    start = as_int(row.get("start_offset"))
    end = as_int(row.get("end_offset")) + 1
    points = {start, end}
    compare_label = str(row.get("compare_label"))
    for payload in payloads:
        if payload.get("compare_label") != compare_label:
            continue
        for key in ("extended_start", "core_start", "core_end", "extended_end"):
            value = as_int(payload.get(key), -1)
            if start < value < end:
                points.add(value)
        for key in ("next_record_header_start", "next_record_bxml_start"):
            value = as_int(payload.get(key), -1)
            if start < value < end:
                points.add(value)
    return sorted(points)


def classify_data_segment(
    source_classification: str,
    segment_start: int,
    segment_end: int,
    source_start: int,
    source_end: int,
    payload: dict[str, Any] | None,
) -> str:
    if payload:
        core_start = as_int(payload.get("core_start"))
        core_end = as_int(payload.get("core_end"))
        extended_start = as_int(payload.get("extended_start"))
        extended_end = as_int(payload.get("extended_end"))
        if core_start <= segment_start and segment_end <= core_end:
            return "required_command_core_payload"
        if extended_start <= segment_start and segment_end <= extended_end:
            return "neighbor_or_extended_record_overlap"
        if segment_end <= core_start:
            return "store_growth_before_command_core"
        if segment_start >= core_end:
            return "store_growth_after_command_core"

    if source_classification == "appended_store_growth_or_free_page_region":
        return "store_growth_or_free_page_region"
    if source_classification == "inserted_command_core_record":
        return "required_command_core_payload"
    if source_classification == "adjacent_extended_command_record":
        return "neighbor_or_extended_record_overlap"
    if source_classification == "sqlite_header_or_page_allocation_metadata":
        return "sqlite_header_or_page_allocation_metadata"
    if source_classification == "pre_existing_data_store_page_or_index_churn":
        return "data_store_index_or_page_churn"
    if source_classification == "near_inserted_command_neighbor_record":
        return "near_inserted_command_neighbor_record"
    if source_classification == "coalesced_store_growth_block_containing_command_core":
        if segment_end <= source_start or segment_start >= source_end:
            return "store_growth_or_free_page_region"
        return "store_growth_after_command_core"
    return "unknown_storage_block"


def classify_model_segment(source_classification: str) -> str:
    if source_classification == "model_store_header_or_root_record_churn":
        return "model_store_header_churn"
    if source_classification == "model_ui_tree_object_reference_or_layout_churn":
        return "model_ui_object_reference_churn"
    return "unknown_storage_block"


def make_segment_row(
    source_row: dict[str, Any],
    segment_start: int,
    segment_end: int,
    payloads: list[dict[str, Any]],
) -> dict[str, Any]:
    source_start = as_int(source_row.get("start_offset"))
    source_end = as_int(source_row.get("end_offset")) + 1
    source_classification = str(source_row.get("classification") or "")
    store_file = str(source_row.get("store_file") or "")
    payload = payload_for_segment_or_source(
        str(source_row.get("compare_label")),
        segment_start,
        segment_end,
        source_start,
        source_end,
        payloads,
    )

    if store_file == "Data.ptd":
        segment_classification = classify_data_segment(
            source_classification,
            segment_start,
            segment_end,
            source_start,
            source_end,
            payload,
        )
    else:
        segment_classification = classify_model_segment(source_classification)

    rule = DATA_SEGMENT_RULES.get(segment_classification, DATA_SEGMENT_RULES["unknown_storage_block"])
    payload_core_start = as_int(payload.get("core_start"), -1) if payload else None
    payload_core_end = as_int(payload.get("core_end"), -1) if payload else None
    payload_extended_start = as_int(payload.get("extended_start"), -1) if payload else None
    payload_extended_end = as_int(payload.get("extended_end"), -1) if payload else None
    payload_relative_start = segment_start - payload_core_start if payload and payload_core_start is not None else None
    payload_relative_end = segment_end - payload_core_start if payload and payload_core_start is not None else None

    return {
        "compare_label": source_row.get("compare_label"),
        "store_file": store_file,
        "source_diff_start_offset": source_start,
        "source_diff_end_offset": source_end - 1,
        "source_diff_length": as_int(source_row.get("length"), source_end - source_start),
        "source_classification": source_classification,
        "segment_start_offset": segment_start,
        "segment_end_offset": segment_end - 1,
        "segment_length": max(0, segment_end - segment_start),
        "segment_classification": segment_classification,
        "storage_role": rule["storage_role"],
        "isolation_status": rule["isolation_status"],
        "clone_relevance": rule["clone_relevance"],
        "segment_blocks_clone": bool(rule["blocks_clone"]),
        "payload_command_offset": payload.get("command_offset") if payload else None,
        "payload_core_start": payload_core_start,
        "payload_core_end": payload_core_end,
        "payload_core_length": payload.get("core_length") if payload else None,
        "payload_extended_start": payload_extended_start,
        "payload_extended_end": payload_extended_end,
        "payload_extended_length": payload.get("extended_length") if payload else None,
        "payload_relative_start": payload_relative_start,
        "payload_relative_end_exclusive": payload_relative_end,
        "lz4_length_field_offset": payload.get("lz4_length_field_offset") if payload else None,
        "lz4_length_field_value": payload.get("lz4_length_field_value") if payload else None,
        "bxml_start_offset": payload.get("previous_bxml_offset") if payload else None,
        "nearest_added_core_distance": source_row.get("nearest_added_core_distance"),
    }


def build_segment_rows(raw_side_effect_rows: list[dict[str, Any]], payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    segment_rows: list[dict[str, Any]] = []
    for source_row in raw_side_effect_rows:
        points = split_points_for_row(source_row, payloads)
        for index in range(len(points) - 1):
            segment_start = points[index]
            segment_end = points[index + 1]
            if segment_start >= segment_end:
                continue
            segment_rows.append(make_segment_row(source_row, segment_start, segment_end, payloads))
    return segment_rows


def summarize_segments(segment_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for row in segment_rows:
        key = (
            str(row["compare_label"]),
            str(row["store_file"]),
            str(row["segment_classification"]),
            str(row["isolation_status"]),
        )
        item = summary.setdefault(
            key,
            {
                "compare_label": row["compare_label"],
                "store_file": row["store_file"],
                "segment_classification": row["segment_classification"],
                "storage_role": row["storage_role"],
                "isolation_status": row["isolation_status"],
                "clone_relevance": row["clone_relevance"],
                "blocks_clone": row["segment_blocks_clone"],
                "segment_count": 0,
                "total_bytes": 0,
                "first_offset": row["segment_start_offset"],
                "last_offset": row["segment_end_offset"],
            },
        )
        item["segment_count"] += 1
        item["total_bytes"] += as_int(row.get("segment_length"))
        item["blocks_clone"] = bool(item["blocks_clone"]) or bool(row.get("segment_blocks_clone"))
        item["first_offset"] = min(as_int(item["first_offset"]), as_int(row["segment_start_offset"]))
        item["last_offset"] = max(as_int(item["last_offset"]), as_int(row["segment_end_offset"]))
    return sorted(
        summary.values(),
        key=lambda row: (row["compare_label"], row["store_file"], row["segment_classification"]),
    )


def gate(gates: list[dict[str, Any]], gate_id: str, status: str, detail: Any, blocker: bool) -> None:
    gates.append({"id": gate_id, "status": status, "detail": detail, "blocker": bool(blocker)})


def build_required_actions(segment_summary: list[dict[str, Any]]) -> list[dict[str, Any]]:
    classes = {str(row["segment_classification"]) for row in segment_summary if bool(row.get("blocks_clone"))}
    actions: list[dict[str, Any]] = []
    action_map = {
        "neighbor_or_extended_record_overlap": (
            "map_neighbor_record_semantics",
            "Decide whether the following BXML/LZ4 record is a required dictionary/path-token record or Petrel store churn.",
        ),
        "data_store_index_or_page_churn": (
            "map_data_store_index_and_command_list_updates",
            "Identify whether pre-existing Data.ptd churn contains command-list indexes or only store/page metadata.",
        ),
        "near_inserted_command_neighbor_record": (
            "map_near_command_neighbor_record_updates",
            "Classify nearby Data.ptd changes around the inserted command envelope.",
        ),
        "model_store_header_churn": (
            "map_model_store_header_updates",
            "Identify whether Model.ptd header/root bytes are required for workflow UI/object registration.",
        ),
        "model_ui_object_reference_churn": (
            "map_model_ui_object_reference_updates",
            "Map workflow UI tree, object reference, and layout updates before any clone writes Model.ptd.",
        ),
        "unknown_storage_block": (
            "classify_unknown_storage_blocks",
            "Classify all unknown storage block segments before any clone patcher is allowed to write.",
        ),
    }
    for segment_class in sorted(classes):
        action_id, description = action_map.get(
            segment_class,
            (f"map_{segment_class}", f"Map storage block segment {segment_class} before applying a clone."),
        )
        actions.append(
            {
                "action_id": action_id,
                "segment_classification": segment_class,
                "description": description,
                "required_before_clone_write": True,
            }
        )
    return actions


def source_row_key(row: dict[str, Any]) -> tuple[str, str, int, int]:
    return (
        str(row.get("compare_label")),
        str(row.get("store_file")),
        as_int(row.get("source_diff_start_offset")),
        as_int(row.get("source_diff_end_offset")),
    )


def build_analysis(
    first: dict[str, Any],
    second: dict[str, Any],
    payloads: list[dict[str, Any]],
    raw_side_effect_rows: list[dict[str, Any]],
    segment_rows: list[dict[str, Any]],
    segment_summary: list[dict[str, Any]],
    required_actions: list[dict[str, Any]],
) -> dict[str, Any]:
    gates: list[dict[str, Any]] = []
    donor_loaded = bool(first.get("loaded")) and bool(second.get("loaded"))
    gate(
        gates,
        "donor_compare_reports_loaded",
        "passed" if donor_loaded else "failed",
        {"first": first.get("path"), "second": second.get("path")},
        blocker=not donor_loaded,
    )

    payload_bounds = [
        {
            "compare_label": row.get("compare_label"),
            "command_offset": row.get("command_offset"),
            "core_start": row.get("core_start"),
            "core_end": row.get("core_end"),
            "core_length": row.get("core_length"),
            "extended_start": row.get("extended_start"),
            "extended_end": row.get("extended_end"),
            "extended_length": row.get("extended_length"),
        }
        for row in payloads
    ]
    payloads_mapped = len(payloads) >= 2 and all(as_int(row.get("core_length")) > 0 for row in payloads)
    gate(
        gates,
        "command_payload_bounds_mapped",
        "passed" if payloads_mapped else "failed",
        payload_bounds,
        blocker=not payloads_mapped,
    )

    coalesced_source_rows = [
        row
        for row in raw_side_effect_rows
        if row.get("classification") == "coalesced_store_growth_block_containing_command_core"
    ]
    split_details: list[dict[str, Any]] = []
    for row in coalesced_source_rows:
        segments = [segment for segment in segment_rows if source_row_key(segment) == source_row_key({
            "compare_label": row.get("compare_label"),
            "store_file": row.get("store_file"),
            "source_diff_start_offset": row.get("start_offset"),
            "source_diff_end_offset": row.get("end_offset"),
        })]
        classes = sorted({str(segment.get("segment_classification")) for segment in segments})
        split_details.append(
            {
                "compare_label": row.get("compare_label"),
                "store_file": row.get("store_file"),
                "source_start": row.get("start_offset"),
                "source_end": row.get("end_offset"),
                "source_length": row.get("length"),
                "segment_classes": classes,
                "segment_count": len(segments),
                "has_required_command_core_payload": "required_command_core_payload" in classes,
                "has_non_core_segment": any(item != "required_command_core_payload" for item in classes),
            }
        )
    mixed_split = bool(coalesced_source_rows) and all(
        row["has_required_command_core_payload"] and row["has_non_core_segment"] for row in split_details
    )
    gate(
        gates,
        "mixed_store_growth_blocks_split",
        "passed" if mixed_split else "failed",
        split_details,
        blocker=not mixed_split,
    )

    labels_with_core = {str(row.get("compare_label")) for row in segment_rows if row.get("segment_classification") == "required_command_core_payload"}
    payload_labels = {str(row.get("compare_label")) for row in payloads}
    no_mixed_segments = not any(
        str(row.get("segment_classification")).startswith("coalesced")
        or str(row.get("segment_classification")).startswith("mixed")
        for row in segment_rows
    )
    separated = payload_labels <= labels_with_core and no_mixed_segments and mixed_split
    gate(
        gates,
        "command_payload_separated_from_store_growth",
        "passed" if separated else "failed",
        {
            "payload_labels": sorted(payload_labels),
            "labels_with_required_command_core_payload": sorted(labels_with_core),
            "no_mixed_segments": no_mixed_segments,
        },
        blocker=not separated,
    )

    neighbor_segments = [
        row for row in segment_summary if row.get("segment_classification") == "neighbor_or_extended_record_overlap"
    ]
    gate(
        gates,
        "neighbor_record_overlap_still_requires_semantics",
        "failed" if neighbor_segments else "passed",
        neighbor_segments,
        blocker=bool(neighbor_segments),
    )

    data_index_segments = [
        row for row in segment_summary if row.get("segment_classification") == "data_store_index_or_page_churn"
    ]
    gate(
        gates,
        "data_store_index_or_page_churn_still_requires_semantics",
        "failed" if data_index_segments else "passed",
        data_index_segments,
        blocker=bool(data_index_segments),
    )

    model_segments = [row for row in segment_summary if str(row.get("store_file")) == "Model.ptd"]
    gate(
        gates,
        "model_side_effects_not_addressed_by_storage_split",
        "failed" if model_segments else "passed",
        model_segments,
        blocker=bool(model_segments),
    )

    gate(
        gates,
        "storage_block_split_report_written",
        "passed" if segment_rows and segment_summary else "failed",
        {"segment_count": len(segment_rows), "segment_class_count": len(segment_summary)},
        blocker=not bool(segment_rows and segment_summary),
    )

    blocker_count = sum(1 for row in gates if row["status"] != "passed" and row.get("blocker"))
    failed_count = sum(1 for row in gates if row["status"] != "passed")
    blocking_classes = sorted({str(row["segment_classification"]) for row in segment_summary if bool(row.get("blocks_clone"))})
    return {
        "storage_payload_separated": separated,
        "clone_patch_precondition_satisfied": blocker_count == 0,
        "status": "ready" if blocker_count == 0 else "blocked",
        "blocker_count": blocker_count,
        "failed_gate_count": failed_count,
        "gates": gates,
        "blocking_segment_classes": blocking_classes,
        "completed_actions": [
            {
                "action_id": "split_command_payload_from_store_growth",
                "status": "done" if separated else "not_done",
                "description": "Separate inserted command-core bytes from surrounding Data.ptd allocator/store-growth segments.",
            }
        ],
        "not_supported_yet": [
            "applying a command clone",
            "ignoring neighbor or extended BXML/LZ4 records",
            "rewriting Data.ptd command-list or index records",
            "rewriting Model.ptd UI/object-reference records",
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
    report_dir = Path(args.output_root).resolve() / f"workflow_clone_storage_blocks_{stamp}"
    report_dir.mkdir(parents=True, exist_ok=True)

    first_payloads, first_payload_rows = recipe_tools.extract_payloads(first, report_dir)
    second_payloads, second_payload_rows = recipe_tools.extract_payloads(second, report_dir)
    payloads = first_payloads + second_payloads
    payload_rows = first_payload_rows + second_payload_rows
    raw_side_effect_rows = recipe_tools.build_side_effect_rows(first, payloads) + recipe_tools.build_side_effect_rows(second, payloads)
    enriched_source_rows = side_effect_tools.enrich_side_effect_rows(raw_side_effect_rows)
    segment_rows = build_segment_rows(raw_side_effect_rows, payloads)
    segment_summary = summarize_segments(segment_rows)
    required_actions = build_required_actions(segment_summary)
    analysis = build_analysis(
        first,
        second,
        payloads,
        raw_side_effect_rows,
        segment_rows,
        segment_summary,
        required_actions,
    )

    first.pop("_after_data_bytes", None)
    first.pop("_before_data_bytes", None)
    second.pop("_after_data_bytes", None)
    second.pop("_before_data_bytes", None)

    payloads_csv = report_dir / "clone_storage_block_candidate_payloads.csv"
    source_ranges_csv = report_dir / "clone_storage_block_source_ranges.csv"
    segments_csv = report_dir / "clone_storage_block_segments.csv"
    summary_csv = report_dir / "clone_storage_block_summary.csv"
    actions_csv = report_dir / "clone_storage_block_required_actions.csv"
    gates_csv = report_dir / "clone_storage_block_gates.csv"
    report_json = report_dir / "workflow_clone_storage_blocks.json"
    summary_md = report_dir / "workflow_clone_storage_blocks_summary.md"

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
        source_ranges_csv,
        enriched_source_rows,
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
        segments_csv,
        segment_rows,
        [
            "compare_label",
            "store_file",
            "source_diff_start_offset",
            "source_diff_end_offset",
            "source_diff_length",
            "source_classification",
            "segment_start_offset",
            "segment_end_offset",
            "segment_length",
            "segment_classification",
            "storage_role",
            "isolation_status",
            "clone_relevance",
            "segment_blocks_clone",
            "payload_command_offset",
            "payload_core_start",
            "payload_core_end",
            "payload_core_length",
            "payload_extended_start",
            "payload_extended_end",
            "payload_extended_length",
            "payload_relative_start",
            "payload_relative_end_exclusive",
            "lz4_length_field_offset",
            "lz4_length_field_value",
            "bxml_start_offset",
            "nearest_added_core_distance",
        ],
    )
    recipe_tools.write_csv(
        summary_csv,
        segment_summary,
        [
            "compare_label",
            "store_file",
            "segment_classification",
            "storage_role",
            "isolation_status",
            "clone_relevance",
            "blocks_clone",
            "segment_count",
            "total_bytes",
            "first_offset",
            "last_offset",
        ],
    )
    recipe_tools.write_csv(
        actions_csv,
        required_actions,
        ["action_id", "segment_classification", "description", "required_before_clone_write"],
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
        "operation": "analyze_workflow_clone_storage_blocks",
        "command_type": "ExportSeismicCmd",
        "project_stem": args.project_stem,
        "first_donor_compare": first,
        "second_donor_compare": second,
        "candidate_payloads": payloads,
        "source_side_effect_ranges": enriched_source_rows,
        "storage_block_segments": segment_rows,
        "storage_block_summary": segment_summary,
        "required_actions": required_actions,
        "analysis": analysis,
        "payloads_csv": str(payloads_csv),
        "source_ranges_csv": str(source_ranges_csv),
        "segments_csv": str(segments_csv),
        "summary_csv": str(summary_csv),
        "required_actions_csv": str(actions_csv),
        "gates_csv": str(gates_csv),
        "payload_directory": str(report_dir / "candidate_payloads"),
    }
    report_json.write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines = [
        "# Workflow Clone Storage Block Analysis",
        "",
        f"- Created UTC: {report['created_at_utc']}",
        f"- Status: {analysis['status']}",
        f"- Storage payload separated: {analysis['storage_payload_separated']}",
        f"- Clone patch precondition satisfied: {analysis['clone_patch_precondition_satisfied']}",
        f"- Blockers: {analysis['blocker_count']}",
        f"- Candidate payloads: {len(payloads)}",
        f"- Storage block segments: {len(segment_rows)}",
        "",
        "## Segment Classes",
        "",
        "| Donor | Store | Segment Class | Status | Segments | Bytes | Blocks Clone |",
        "| --- | --- | --- | --- | ---: | ---: | --- |",
    ]
    for row in segment_summary:
        lines.append(
            f"| {row['compare_label']} | {row['store_file']} | {row['segment_classification']} | "
            f"{row['isolation_status']} | {row['segment_count']} | {row['total_bytes']} | {row['blocks_clone']} |"
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
            "This analyzer is read-only. It splits existing donor snapshot diffs into command payload, neighbor/extended record, allocator growth, Data.ptd churn, and Model.ptd side-effect segments.",
            "A blocked result means a command-clone patcher must not write Petrel native stores yet.",
            "",
            "## Outputs",
            "",
            f"- JSON: {report_json}",
            f"- Payloads CSV: {payloads_csv}",
            f"- Source ranges CSV: {source_ranges_csv}",
            f"- Segments CSV: {segments_csv}",
            f"- Summary CSV: {summary_csv}",
            f"- Required actions CSV: {actions_csv}",
            f"- Gates CSV: {gates_csv}",
        ]
    )
    summary_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("Workflow clone storage block analysis complete")
    print(f"Status: {analysis['status']}")
    print(f"Storage payload separated: {analysis['storage_payload_separated']}")
    print(f"Clone patch precondition satisfied: {analysis['clone_patch_precondition_satisfied']}")
    print(f"Blockers: {analysis['blocker_count']}")
    print(f"Report: {report_json}")
    print(f"Summary: {summary_md}")
    print(f"Payloads: {payloads_csv}")
    print(f"Source ranges: {source_ranges_csv}")
    print(f"Segments: {segments_csv}")
    print(f"Storage summary: {summary_csv}")
    print(f"Required actions: {actions_csv}")
    print(f"Gates: {gates_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
