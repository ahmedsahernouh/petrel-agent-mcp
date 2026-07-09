#!/usr/bin/env python3
"""Extract read-only Petrel Workflow Editor command clone recipe evidence."""

from __future__ import annotations

import argparse
import csv
import difflib
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "build" / "native_edit_experiments"
DEFAULT_PROJECT_STEM = "Petrel2010 demo project ExportPilot"
DEFAULT_FIRST_DONOR_COMPARE = (
    DEFAULT_OUTPUT_ROOT / "native_workflow_snapshot_compare_20260703_012602" / "snapshot_compare_report.json"
)
DEFAULT_SECOND_DONOR_COMPARE = (
    DEFAULT_OUTPUT_ROOT / "native_workflow_snapshot_compare_20260703_054200" / "snapshot_compare_report.json"
)
DEFAULT_TERMS = [
    "ExportSeismicCmd",
    "SheetSaveCmd",
    "SimpleCmd",
    "Orig Amp",
    "_donor.sgy",
    "sgy2",
    "sgy3",
    "segy",
    ".sgy",
    "Seismic",
    "Coordinate scale factor",
    "Sample value format",
    "BXML",
    "LZ4",
    "GUID",
    "guid",
    "unique_tag",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def printable_context(data: bytes, start: int, length: int) -> str:
    start = max(0, start)
    end = min(len(data), start + max(0, length))
    return "".join(chr(byte) if 32 <= byte <= 126 else "." for byte in data[start:end])


def find_offsets(data: bytes, term: str) -> list[int]:
    pattern = term.encode("latin-1", errors="ignore")
    if not pattern:
        return []
    offsets: list[int] = []
    start = data.find(pattern)
    while start >= 0:
        offsets.append(start)
        start = data.find(pattern, start + 1)
    return offsets


def nearest_before(offsets: list[int], offset: int) -> int | None:
    value: int | None = None
    for item in offsets:
        if item <= offset:
            value = item
        else:
            break
    return value


def nearest_after(offsets: list[int], offset: int) -> int | None:
    for item in offsets:
        if item > offset:
            return item
    return None


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def read_csv_rows(path: str | None) -> list[dict[str, str]]:
    if not path:
        return []
    csv_path = Path(path)
    if not csv_path.is_file():
        return []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def command_type_guess(context: str) -> str:
    import re

    matches = re.findall(r"[A-Za-z][A-Za-z0-9_]{2,}Cmd", context)
    return ";".join(dict.fromkeys(matches))


def term_hits(data: bytes, terms: list[str], start: int, end: int, include_context: bool) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for term in terms:
        for offset in find_offsets(data, term):
            if start <= offset < end:
                row: dict[str, Any] = {
                    "term": term,
                    "offset": offset,
                    "relative_offset": offset - start,
                }
                if include_context:
                    row["context"] = printable_context(data, offset - 100, 360)
                rows.append(row)
    return sorted(rows, key=lambda row: (row["offset"], row["term"]))


def map_command_records(data: bytes, terms: list[str], include_context: bool) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    bxml_offsets = sorted(find_offsets(data, "BXML"))
    lz4_offsets = sorted(find_offsets(data, "LZ4"))
    command_offsets = find_offsets(data, "ExportSeismicCmd")
    records: list[dict[str, Any]] = []
    hit_rows: list[dict[str, Any]] = []

    for index, command_offset in enumerate(command_offsets):
        previous_bxml = nearest_before(bxml_offsets, command_offset)
        previous_lz4 = nearest_before(lz4_offsets, command_offset)
        next_bxml = nearest_after(bxml_offsets, command_offset)
        next_lz4 = nearest_after(lz4_offsets, command_offset)
        next_next_bxml = nearest_after(bxml_offsets, next_bxml or command_offset) if next_bxml is not None else None
        start = previous_lz4 if previous_lz4 is not None else previous_bxml if previous_bxml is not None else command_offset
        bxml_end = next_bxml if next_bxml is not None else min(len(data), command_offset + 4096)
        payload_end = (
            next_lz4
            if next_lz4 is not None and next_bxml is not None and start < next_lz4 < next_bxml
            else bxml_end
        )
        extended_end = next_next_bxml if next_next_bxml is not None else bxml_end
        context = printable_context(data, command_offset - 240, 1020)
        record = {
            "record_index": index,
            "command_offset": command_offset,
            "previous_lz4_offset": previous_lz4,
            "previous_bxml_offset": previous_bxml,
            "next_bxml_offset": next_bxml,
            "next_lz4_offset": next_lz4,
            "next_next_bxml_offset": next_next_bxml,
            "core_start": start,
            "core_end": payload_end,
            "core_length": payload_end - start,
            "next_record_header_start": next_lz4,
            "next_record_bxml_start": next_bxml,
            "extended_start": start,
            "extended_end": extended_end,
            "extended_length": extended_end - start,
            "command_span_to_next_bxml": (bxml_end - previous_bxml) if previous_bxml is not None else None,
            "command_type_guess": command_type_guess(context),
        }
        if include_context:
            record["context"] = context
        records.append(record)
        for hit in term_hits(data, terms, start, extended_end, include_context):
            hit_rows.append({"record_index": index, **hit})

    return records, hit_rows


def store_summary(compare: dict[str, Any], store_file: str) -> dict[str, Any]:
    for row in compare.get("store_summaries", []):
        if row.get("store_file") == store_file:
            return row
    return {}


def load_compare(path: Path, label: str, project_stem: str, terms: list[str], include_context: bool) -> dict[str, Any]:
    report = read_json(path)
    stem = str(report.get("project_stem") or project_stem)
    before_snapshot = Path(str(report["before_snapshot"]))
    after_snapshot = Path(str(report["after_snapshot"]))
    before_data_path = before_snapshot / f"{stem}.ptd" / "Data.ptd"
    after_data_path = after_snapshot / f"{stem}.ptd" / "Data.ptd"
    before_model_path = before_snapshot / f"{stem}.ptd" / "Model.ptd"
    after_model_path = after_snapshot / f"{stem}.ptd" / "Model.ptd"
    before_data = before_data_path.read_bytes()
    after_data = after_data_path.read_bytes()
    before_model = before_model_path.read_bytes()
    after_model = after_model_path.read_bytes()
    before_records, before_hits = map_command_records(before_data, terms, include_context)
    after_records, after_hits = map_command_records(after_data, terms, include_context)

    data_store = store_summary(report, "Data.ptd")
    model_store = store_summary(report, "Model.ptd")
    before_offsets = {row["command_offset"] for row in before_records}
    after_offsets = {row["command_offset"] for row in after_records}
    added_records = [row for row in after_records if row["command_offset"] not in before_offsets]
    carried_records = [row for row in after_records if row["command_offset"] in before_offsets]
    removed_offsets = sorted(before_offsets - after_offsets)

    return {
        "label": label,
        "path": str(path),
        "loaded": True,
        "project_stem": stem,
        "before_snapshot": str(before_snapshot),
        "after_snapshot": str(after_snapshot),
        "before_data_path": str(before_data_path),
        "after_data_path": str(after_data_path),
        "before_model_path": str(before_model_path),
        "after_model_path": str(after_model_path),
        "before_data_sha256": sha256_bytes(before_data),
        "after_data_sha256": sha256_bytes(after_data),
        "before_model_sha256": sha256_bytes(before_model),
        "after_model_sha256": sha256_bytes(after_model),
        "before_data_length": len(before_data),
        "after_data_length": len(after_data),
        "before_model_length": len(before_model),
        "after_model_length": len(after_model),
        "data_store_summary": data_store,
        "model_store_summary": model_store,
        "before_records": before_records,
        "after_records": after_records,
        "before_token_hits": before_hits,
        "after_token_hits": after_hits,
        "added_records": added_records,
        "carried_records": carried_records,
        "removed_command_offsets": removed_offsets,
        "_before_data_bytes": before_data,
        "_after_data_bytes": after_data,
    }


def overlap_count(diff_rows: list[dict[str, str]], start: int, end: int) -> tuple[int, int]:
    count = 0
    total = 0
    for row in diff_rows:
        diff_start = int_or_none(row.get("start_offset"))
        diff_end = int_or_none(row.get("end_offset"))
        length = int_or_none(row.get("length")) or 0
        if diff_start is None or diff_end is None:
            continue
        if diff_start < end and diff_end >= start:
            count += 1
            total += length
    return count, total


def summarize_model_terms(model_store: dict[str, Any], terms: list[str]) -> list[dict[str, Any]]:
    rows = read_csv_rows(model_store.get("term_map_csv"))
    summaries: list[dict[str, Any]] = []
    for term in terms:
        hits = [row for row in rows if row.get("term") == term]
        if hits:
            summaries.append(
                {
                    "term": term,
                    "hit_count": len(hits),
                    "offsets": [int_or_none(row.get("offset")) for row in hits[:10]],
                    "truncated": len(hits) > 10,
                }
            )
    return summaries


def extract_payloads(compare: dict[str, Any], report_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    payload_dir = report_dir / "candidate_payloads"
    payload_dir.mkdir(parents=True, exist_ok=True)
    data_store = compare.get("data_store_summary", {})
    data_diff_rows = read_csv_rows(data_store.get("diff_ranges_csv"))
    before_data: bytes = compare["_before_data_bytes"]
    after_data: bytes = compare["_after_data_bytes"]
    payloads: list[dict[str, Any]] = []
    csv_rows: list[dict[str, Any]] = []

    for index, record in enumerate(compare["added_records"]):
        core_start = int(record["core_start"])
        core_end = int(record["core_end"])
        extended_start = int(record["extended_start"])
        extended_end = int(record["extended_end"])
        core_bytes = after_data[core_start:core_end]
        extended_bytes = after_data[extended_start:extended_end]
        lz4_length_field_offset = core_start + 4 if len(core_bytes) >= 8 and core_bytes[:4] == b"LZ4\x01" else None
        lz4_length_field_value = int.from_bytes(core_bytes[4:8], "little") if lz4_length_field_offset is not None else None
        prefix = f"{compare['label']}_added_{index}_cmd_{record['command_offset']}"
        core_file = payload_dir / f"{prefix}_core_record.bin"
        extended_file = payload_dir / f"{prefix}_extended_record.bin"
        core_file.write_bytes(core_bytes)
        extended_file.write_bytes(extended_bytes)
        core_overlap_count, core_overlap_bytes = overlap_count(data_diff_rows, core_start, core_end)
        extended_overlap_count, extended_overlap_bytes = overlap_count(data_diff_rows, extended_start, extended_end)
        total_diff_count = len(data_diff_rows)
        total_diff_bytes = sum(int_or_none(row.get("length")) or 0 for row in data_diff_rows)
        before_slice = before_data[core_start:core_end] if core_end <= len(before_data) else before_data[core_start:]
        before_nonzero = sum(1 for byte in before_slice if byte != 0)
        if core_start >= len(before_data):
            before_region_state = "absent_before_eof_append"
        elif before_slice and before_nonzero == 0:
            before_region_state = "all_zero_free_space"
        elif before_slice:
            before_region_state = "nonzero_existing_region"
        else:
            before_region_state = "empty_or_unavailable"
        payload = {
            "compare_label": compare["label"],
            "added_record_index": index,
            "command_offset": record["command_offset"],
            "core_start": core_start,
            "core_end": core_end,
            "core_length": len(core_bytes),
            "core_sha256": sha256_bytes(core_bytes),
            "core_payload_file": str(core_file),
            "extended_start": extended_start,
            "extended_end": extended_end,
            "extended_length": len(extended_bytes),
            "extended_sha256": sha256_bytes(extended_bytes),
            "extended_payload_file": str(extended_file),
            "previous_lz4_offset": record.get("previous_lz4_offset"),
            "previous_bxml_offset": record.get("previous_bxml_offset"),
            "next_bxml_offset": record.get("next_bxml_offset"),
            "next_lz4_offset": record.get("next_lz4_offset"),
            "next_next_bxml_offset": record.get("next_next_bxml_offset"),
            "next_record_header_start": record.get("next_record_header_start"),
            "next_record_bxml_start": record.get("next_record_bxml_start"),
            "command_span_to_next_bxml": record.get("command_span_to_next_bxml"),
            "lz4_length_field_offset": lz4_length_field_offset,
            "lz4_length_field_value": lz4_length_field_value,
            "core_length_minus_lz4_length_value": len(core_bytes) - lz4_length_field_value if lz4_length_field_value is not None else None,
            "before_region_state": before_region_state,
            "before_region_available_bytes": len(before_slice),
            "before_region_nonzero_bytes": before_nonzero,
            "data_diff_ranges_overlapping_core": core_overlap_count,
            "data_diff_bytes_overlapping_core": core_overlap_bytes,
            "data_diff_ranges_outside_core": max(0, total_diff_count - core_overlap_count),
            "data_diff_bytes_outside_core": max(0, total_diff_bytes - core_overlap_bytes),
            "data_diff_ranges_overlapping_extended": extended_overlap_count,
            "data_diff_bytes_overlapping_extended": extended_overlap_bytes,
            "hex_preview_first_64": core_bytes[:64].hex(),
        }
        payloads.append(payload)
        csv_rows.append({key: value for key, value in payload.items() if not isinstance(value, (list, dict))})

    return payloads, csv_rows


def ascii_preview(data: bytes) -> str:
    return "".join(chr(byte) if 32 <= byte <= 126 else "." for byte in data)


def classify_payload_mutation(tag: str, first_start: int, first_bytes: bytes, second_bytes: bytes) -> str:
    if first_start in {4, 5}:
        return "lz4_length_field_candidate"
    if 8 <= first_start < 12:
        return "lz4_checksum_or_hash_candidate"
    if tag == "insert" and b"sgy2" in second_bytes:
        return "inserted_output_token_reference"
    if first_start >= 15 and len(first_bytes) <= 4 and len(second_bytes) <= 4:
        return "bxml_container_or_size_candidate"
    if first_start >= 15:
        return "bxml_payload_mutation_candidate"
    return "header_or_unknown"


def compare_core_payloads(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(payloads) < 2:
        return []
    first = payloads[0]
    second = payloads[1]
    first_bytes = Path(first["core_payload_file"]).read_bytes()
    second_bytes = Path(second["core_payload_file"]).read_bytes()
    matcher = difflib.SequenceMatcher(None, first_bytes, second_bytes, autojunk=False)
    rows: list[dict[str, Any]] = []
    for tag, first_start, first_end, second_start, second_end in matcher.get_opcodes():
        if tag == "equal":
            continue
        old = first_bytes[first_start:first_end]
        new = second_bytes[second_start:second_end]
        rows.append(
            {
                "comparison": f"{first['compare_label']}_to_{second['compare_label']}",
                "tag": tag,
                "first_start": first_start,
                "first_end": first_end,
                "first_length": len(old),
                "second_start": second_start,
                "second_end": second_end,
                "second_length": len(new),
                "classification": classify_payload_mutation(tag, first_start, old, new),
                "first_hex": old.hex(),
                "second_hex": new.hex(),
                "first_ascii": ascii_preview(old),
                "second_ascii": ascii_preview(new),
                "first_context": ascii_preview(first_bytes[max(0, first_start - 48) : min(len(first_bytes), first_end + 48)]),
                "second_context": ascii_preview(second_bytes[max(0, second_start - 48) : min(len(second_bytes), second_end + 48)]),
            }
        )
    return rows


def overlaps(start: int, end: int, other_start: int, other_end: int) -> bool:
    return start < other_end and end > other_start


def range_distance(start: int, end: int, other_start: int, other_end: int) -> int:
    if overlaps(start, end, other_start, other_end):
        return 0
    if end <= other_start:
        return other_start - end
    return start - other_end


def classify_side_effect_row(
    store_file: str,
    start: int,
    end: int,
    payloads_for_label: list[dict[str, Any]],
    before_length: int,
) -> tuple[str, int | None]:
    nearest_distance: int | None = None
    for payload in payloads_for_label:
        core_start = int(payload["core_start"])
        core_end = int(payload["core_end"])
        extended_start = int(payload["extended_start"])
        extended_end = int(payload["extended_end"])
        distance = range_distance(start, end, core_start, core_end)
        nearest_distance = distance if nearest_distance is None else min(nearest_distance, distance)
        if overlaps(start, end, core_start, core_end):
            if start < core_start or end > core_end:
                return "coalesced_store_growth_block_containing_command_core", 0
            return "inserted_command_core_record", 0
        if overlaps(start, end, extended_start, extended_end):
            return "adjacent_extended_command_record", 0

    if store_file == "Data.ptd":
        if start >= before_length:
            return "appended_store_growth_or_free_page_region", nearest_distance
        if start < 4096:
            return "sqlite_header_or_page_allocation_metadata", nearest_distance
        if nearest_distance is not None and nearest_distance <= 4096:
            return "near_inserted_command_neighbor_record", nearest_distance
        return "pre_existing_data_store_page_or_index_churn", nearest_distance

    if start < 4096:
        return "model_store_header_or_root_record_churn", nearest_distance
    return "model_ui_tree_object_reference_or_layout_churn", nearest_distance


def build_side_effect_rows(compare: dict[str, Any], payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    payloads_for_label = [row for row in payloads if row["compare_label"] == compare["label"]]
    for store_file, store_key, before_length_key in (
        ("Data.ptd", "data_store_summary", "before_data_length"),
        ("Model.ptd", "model_store_summary", "before_model_length"),
    ):
        store = compare.get(store_key, {})
        diff_rows = read_csv_rows(store.get("diff_ranges_csv"))
        before_length = int(compare.get(before_length_key) or 0)
        for diff in diff_rows:
            start = int_or_none(diff.get("start_offset"))
            end_inclusive = int_or_none(diff.get("end_offset"))
            length = int_or_none(diff.get("length")) or 0
            if start is None or end_inclusive is None:
                continue
            end = end_inclusive + 1
            classification, nearest_distance = classify_side_effect_row(
                store_file,
                start,
                end,
                payloads_for_label,
                before_length,
            )
            rows.append(
                {
                    "compare_label": compare["label"],
                    "store_file": store_file,
                    "start_offset": start,
                    "end_offset": end_inclusive,
                    "length": length,
                    "classification": classification,
                    "nearest_added_core_distance": nearest_distance,
                }
            )
    return rows


def summarize_side_effect_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (str(row["compare_label"]), str(row["store_file"]), str(row["classification"]))
        item = summary.setdefault(
            key,
            {
                "compare_label": row["compare_label"],
                "store_file": row["store_file"],
                "classification": row["classification"],
                "range_count": 0,
                "total_bytes": 0,
                "first_offset": row["start_offset"],
                "last_offset": row["end_offset"],
                "nearest_added_core_distance_min": row.get("nearest_added_core_distance"),
            },
        )
        item["range_count"] += 1
        item["total_bytes"] += int(row.get("length") or 0)
        item["first_offset"] = min(int(item["first_offset"]), int(row["start_offset"]))
        item["last_offset"] = max(int(item["last_offset"]), int(row["end_offset"]))
        distance = row.get("nearest_added_core_distance")
        if distance is not None:
            current = item.get("nearest_added_core_distance_min")
            item["nearest_added_core_distance_min"] = distance if current is None else min(int(current), int(distance))
    return sorted(summary.values(), key=lambda row: (row["compare_label"], row["store_file"], row["classification"]))


def extract_payload_signals(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    terms = ["unique_tag", "orig_amp", "_donor.sgy", "sgy2", "ExportSeismicCmd", "SheetSaveCmd", "SimpleCmd"]
    rows: list[dict[str, Any]] = []
    for payload in payloads:
        data = Path(payload["core_payload_file"]).read_bytes()
        for term in terms:
            for offset in find_offsets(data, term):
                rows.append(
                    {
                        "compare_label": payload["compare_label"],
                        "command_offset": payload["command_offset"],
                        "term": term,
                        "relative_offset": offset,
                        "absolute_offset": int(payload["core_start"]) + offset,
                        "context": printable_context(data, offset - 48, 160),
                    }
                )
    return rows


def build_negative_controls(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    controls: list[dict[str, Any]] = []
    for payload in payloads:
        data = Path(payload["core_payload_file"]).read_bytes()
        has_lz4 = data.startswith(b"LZ4\x01")
        has_bxml = data.find(b"BXML") >= 0
        stored_length = int.from_bytes(data[4:8], "little") if len(data) >= 8 else None
        baseline_ok = bool(has_lz4 and has_bxml and stored_length and stored_length < len(data))
        corrupt = bytearray(data)
        if len(corrupt) >= 8:
            corrupt[4:8] = b"\x00\x00\x00\x00"
        corrupt_length = int.from_bytes(corrupt[4:8], "little") if len(corrupt) >= 8 else None
        corrupt_refused = not (corrupt.startswith(b"LZ4\x01") and corrupt.find(b"BXML") >= 0 and corrupt_length and corrupt_length < len(corrupt))
        controls.append(
            {
                "compare_label": payload["compare_label"],
                "command_offset": payload["command_offset"],
                "control": "zeroed_lz4_length_field",
                "baseline_guard_accepts_payload_shape": baseline_ok,
                "corrupt_lz4_length_value": corrupt_length,
                "guard_refused_corrupt_payload": corrupt_refused,
                "scope": "dry_run_payload_guard_only_no_petrel_file_write",
            }
        )
    return controls


def command_order_details(first: dict[str, Any], second: dict[str, Any], payloads: list[dict[str, Any]]) -> dict[str, Any]:
    second_added_offsets = [row["command_offset"] for row in second.get("added_records", [])]
    second_carried_offsets = [row["command_offset"] for row in second.get("carried_records", [])]
    current_order = [row["command_offset"] for row in sorted(second.get("after_records", []), key=lambda item: item["command_offset"])]
    added_payload_starts = [
        {
            "compare_label": row["compare_label"],
            "command_offset": row["command_offset"],
            "core_start": row["core_start"],
            "core_end": row["core_end"],
            "before_region_state": row.get("before_region_state"),
        }
        for row in payloads
    ]
    return {
        "first_donor_added_offsets": [row["command_offset"] for row in first.get("added_records", [])],
        "second_donor_added_offsets": second_added_offsets,
        "second_donor_carried_offsets": second_carried_offsets,
        "second_donor_after_order_by_offset": current_order,
        "added_payload_storage": added_payload_starts,
        "carried_original_preserved": bool(second_carried_offsets),
    }


def recipe_gate(gates: list[dict[str, Any]], gate_id: str, status: str, detail: Any, blocker: bool) -> None:
    gates.append({"id": gate_id, "status": status, "detail": detail, "blocker": blocker})


def build_recipe(
    first: dict[str, Any],
    second: dict[str, Any],
    payloads: list[dict[str, Any]],
    payload_mutations: list[dict[str, Any]],
    side_effect_summary: list[dict[str, Any]],
    payload_signals: list[dict[str, Any]],
    negative_controls: list[dict[str, Any]],
) -> dict[str, Any]:
    gates: list[dict[str, Any]] = []
    added_counts = {first["label"]: len(first["added_records"]), second["label"]: len(second["added_records"])}
    recipe_gate(
        gates,
        "donor_added_records_detected",
        "passed" if all(value >= 1 for value in added_counts.values()) else "failed",
        added_counts,
        blocker=not all(value >= 1 for value in added_counts.values()),
    )
    recipe_gate(
        gates,
        "candidate_payload_files_written",
        "passed" if len(payloads) >= 2 and all(Path(row["core_payload_file"]).is_file() for row in payloads) else "failed",
        {"payload_count": len(payloads)},
        blocker=len(payloads) < 2,
    )
    recipe_gate(
        gates,
        "core_record_bounds_detected",
        "passed" if payloads and all(int(row["core_length"]) > 0 for row in payloads) else "failed",
        [{"label": row["compare_label"], "core_length": row["core_length"]} for row in payloads],
        blocker=not payloads,
    )
    recipe_gate(
        gates,
        "second_donor_preserved_existing_record_offset",
        "passed" if len(second.get("carried_records", [])) >= 1 else "failed",
        {"carried_offsets": [row["command_offset"] for row in second.get("carried_records", [])]},
        blocker=len(second.get("carried_records", [])) < 1,
    )

    body_storage_details = [
        {
            "compare_label": row["compare_label"],
            "command_offset": row["command_offset"],
            "before_region_state": row.get("before_region_state"),
            "before_region_available_bytes": row.get("before_region_available_bytes"),
            "before_region_nonzero_bytes": row.get("before_region_nonzero_bytes"),
        }
        for row in payloads
    ]
    body_storage_mapped = bool(body_storage_details) and all(
        row["before_region_state"] in {"absent_before_eof_append", "all_zero_free_space"} for row in body_storage_details
    )
    recipe_gate(
        gates,
        "command_body_storage_location_mapped",
        "passed" if body_storage_mapped else "failed",
        body_storage_details,
        blocker=not body_storage_mapped,
    )

    data_side_effects = [
        {
            "compare_label": row["compare_label"],
            "outside_diff_ranges": row.get("data_diff_ranges_outside_core"),
            "outside_diff_bytes": row.get("data_diff_bytes_outside_core"),
            "length_delta": (first if row["compare_label"] == first["label"] else second)["data_store_summary"].get("length_delta"),
        }
        for row in payloads
    ]
    data_side_effects_isolated = all(
        int(row.get("outside_diff_ranges") or 0) == 0 and int(row.get("outside_diff_bytes") or 0) == 0 for row in data_side_effects
    )
    recipe_gate(
        gates,
        "data_side_effects_outside_command_body_are_isolated",
        "passed" if data_side_effects_isolated else "failed",
        data_side_effects,
        blocker=not data_side_effects_isolated,
    )
    recipe_gate(
        gates,
        "side_effect_diff_classes_mapped",
        "passed" if side_effect_summary else "failed",
        side_effect_summary,
        blocker=not bool(side_effect_summary),
    )

    model_summaries = {
        first["label"]: {
            "length_delta": first["model_store_summary"].get("length_delta"),
            "diff_range_count": first["model_store_summary"].get("diff_range_count"),
            "changed": first["model_store_summary"].get("changed"),
        },
        second["label"]: {
            "length_delta": second["model_store_summary"].get("length_delta"),
            "diff_range_count": second["model_store_summary"].get("diff_range_count"),
            "changed": second["model_store_summary"].get("changed"),
        },
    }
    model_isolated = all(
        bool(summary.get("changed")) is False and int(summary.get("length_delta") or 0) == 0
        for summary in model_summaries.values()
    )
    recipe_gate(gates, "model_side_effects_isolated", "passed" if model_isolated else "failed", model_summaries, blocker=not model_isolated)

    order_detail = command_order_details(first, second, payloads)
    order_mapped = bool(order_detail["second_donor_added_offsets"]) and bool(order_detail["second_donor_carried_offsets"])
    recipe_gate(
        gates,
        "workflow_command_record_order_mapped",
        "passed" if order_mapped else "failed",
        order_detail,
        blocker=not order_mapped,
    )

    core_lengths = sorted({row["core_length"] for row in payloads})
    extended_lengths = sorted({row["extended_length"] for row in payloads})
    recipe_gate(
        gates,
        "payload_lengths_detected",
        "passed" if payloads and all(int(row["core_length"]) > 0 for row in payloads) else "failed",
        {"core_lengths": core_lengths, "extended_lengths": extended_lengths, "uniform": len(core_lengths) == 1},
        blocker=not payloads,
    )

    lz4_length_candidates = [
        {
            "compare_label": row["compare_label"],
            "command_offset": row["command_offset"],
            "field_offset": row.get("lz4_length_field_offset"),
            "field_value": row.get("lz4_length_field_value"),
            "core_length_minus_field_value": row.get("core_length_minus_lz4_length_value"),
        }
        for row in payloads
    ]
    lz4_candidate_mapped = bool(lz4_length_candidates) and all(item["field_offset"] is not None for item in lz4_length_candidates)
    recipe_gate(
        gates,
        "lz4_length_field_candidates_mapped",
        "passed" if lz4_candidate_mapped else "failed",
        lz4_length_candidates,
        blocker=not lz4_candidate_mapped,
    )

    bxml_mutations = [
        row
        for row in payload_mutations
        if str(row.get("classification", "")).startswith("bxml_")
        or row.get("classification") == "inserted_output_token_reference"
    ]
    recipe_gate(
        gates,
        "bxml_mutation_candidates_mapped",
        "passed" if bxml_mutations else "failed",
        [
            {
                "classification": row["classification"],
                "first_start": row["first_start"],
                "second_start": row["second_start"],
                "first_length": row["first_length"],
                "second_length": row["second_length"],
                "second_ascii": row["second_ascii"],
            }
            for row in bxml_mutations
        ],
        blocker=not bool(bxml_mutations),
    )

    labels_with_orig_amp = {row["compare_label"] for row in payload_signals if row.get("term") == "orig_amp"}
    orig_amp_signal_mapped = labels_with_orig_amp == {row["compare_label"] for row in payloads}
    recipe_gate(
        gates,
        "exportseismiccmd_orig_amp_payload_signals_mapped",
        "passed" if orig_amp_signal_mapped else "failed",
        [row for row in payload_signals if row.get("term") == "orig_amp"],
        blocker=not orig_amp_signal_mapped,
    )

    labels_with_unique_tag = {row["compare_label"] for row in payload_signals if row.get("term") == "unique_tag"}
    unique_tag_mapped = labels_with_unique_tag == {row["compare_label"] for row in payloads}
    recipe_gate(
        gates,
        "unique_tag_payload_field_candidates_mapped",
        "passed" if unique_tag_mapped else "failed",
        [row for row in payload_signals if row.get("term") == "unique_tag"],
        blocker=not unique_tag_mapped,
    )

    negative_refusal = bool(negative_controls) and all(row.get("guard_refused_corrupt_payload") for row in negative_controls)
    recipe_gate(
        gates,
        "negative_control_clone_refusal_guard_recorded",
        "passed" if negative_refusal else "failed",
        negative_controls,
        blocker=not negative_refusal,
    )

    known_unvalidated = [
        "BXML mutation semantics are not validated",
        "workflow command-list/index semantics are not validated",
        "Model.ptd UI tree and object-reference semantics are not validated",
        "ExportSeismicCmd object-reference binding semantics are not validated",
        "unique_tag/GUID generation or reuse rule is not validated",
        "applied clone recovery proof has not run",
    ]
    for item in known_unvalidated:
        recipe_gate(
            gates,
            item.lower().replace(" ", "_").replace("/", "_").replace("-", "_"),
            "failed",
            item,
            blocker=True,
        )

    blocker_count = sum(1 for row in gates if row["status"] != "passed" and row.get("blocker"))
    failed_count = sum(1 for row in gates if row["status"] != "passed")
    return {
        "recipe_safe_to_apply": blocker_count == 0,
        "recipe_status": "ready" if blocker_count == 0 else "blocked",
        "failed_gate_count": failed_count,
        "blocker_count": blocker_count,
        "gates": gates,
        "what_is_extracted": [
            "added ExportSeismicCmd records in first and second donor snapshots",
            "candidate core and extended record payload files",
            "BXML/LZ4 marker offsets around each added command",
            "payload-to-payload mutation candidates",
            "command body storage location state before Petrel authored the donors",
            "donor Data.ptd and Model.ptd side-effect summaries",
            "payload signal offsets for orig_amp, unique_tag, and output tokens",
            "dry-run negative-control refusal evidence for a corrupt LZ4 length field",
        ],
        "not_supported_yet": [
            "applying a clone patch",
            "variable-length insertion into Data.ptd",
            "updating Model.ptd UI/object-reference structures",
            "generating new GUID/tag values",
            "claiming a new Petrel-authored workflow command exists",
        ],
        "next_required_evidence": [
            "a cleaner donor diff or deeper parser that isolates command-list/index bytes",
            "validated BXML mutation semantics for core and extended payload insertion",
            "a deterministic rule for Model.ptd references and UI tree updates",
            "a GUID/unique_tag generation or reuse rule",
            "an applied-clone recovery proof on a disposable copy before any real native workflow write",
        ],
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


def main() -> int:
    args = parse_args()
    terms = [term for term in args.terms.split("|") if term]
    first_compare_path = Path(args.first_donor_compare_report).resolve()
    second_compare_path = Path(args.second_donor_compare_report).resolve()
    first = load_compare(first_compare_path, "first_donor", args.project_stem, terms, bool(args.include_context))
    second = load_compare(second_compare_path, "second_donor", args.project_stem, terms, bool(args.include_context))

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = Path(args.output_root).resolve() / f"workflow_command_clone_recipe_{stamp}"
    report_dir.mkdir(parents=True, exist_ok=True)

    first_payloads, first_payload_rows = extract_payloads(first, report_dir)
    second_payloads, second_payload_rows = extract_payloads(second, report_dir)
    payloads = first_payloads + second_payloads
    payload_rows = first_payload_rows + second_payload_rows
    payload_mutations = compare_core_payloads(payloads)
    side_effect_rows = build_side_effect_rows(first, payloads) + build_side_effect_rows(second, payloads)
    side_effect_summary = summarize_side_effect_rows(side_effect_rows)
    payload_signals = extract_payload_signals(payloads)
    negative_controls = build_negative_controls(payloads)
    recipe = build_recipe(
        first,
        second,
        payloads,
        payload_mutations,
        side_effect_summary,
        payload_signals,
        negative_controls,
    )

    first.pop("_after_data_bytes", None)
    first.pop("_before_data_bytes", None)
    second.pop("_after_data_bytes", None)
    second.pop("_before_data_bytes", None)
    for compare in (first, second):
        compare["model_term_signals"] = summarize_model_terms(compare["model_store_summary"], terms)

    payload_csv = report_dir / "clone_recipe_candidate_payloads.csv"
    payload_mutations_csv = report_dir / "clone_recipe_payload_mutations.csv"
    side_effects_csv = report_dir / "clone_recipe_side_effects.csv"
    side_effect_summary_csv = report_dir / "clone_recipe_side_effect_summary.csv"
    payload_signals_csv = report_dir / "clone_recipe_payload_signals.csv"
    negative_controls_csv = report_dir / "clone_recipe_negative_controls.csv"
    gates_csv = report_dir / "clone_recipe_gates.csv"
    report_json = report_dir / "workflow_command_clone_recipe.json"
    summary_md = report_dir / "workflow_command_clone_recipe_summary.md"
    if payload_rows:
        write_csv(
            payload_csv,
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
    else:
        write_csv(payload_csv, [], ["compare_label", "added_record_index", "command_offset"])

    write_csv(
        payload_mutations_csv,
        payload_mutations,
        [
            "comparison",
            "tag",
            "first_start",
            "first_end",
            "first_length",
            "second_start",
            "second_end",
            "second_length",
            "classification",
            "first_hex",
            "second_hex",
            "first_ascii",
            "second_ascii",
            "first_context",
            "second_context",
        ],
    )
    write_csv(
        side_effects_csv,
        side_effect_rows,
        [
            "compare_label",
            "store_file",
            "start_offset",
            "end_offset",
            "length",
            "classification",
            "nearest_added_core_distance",
        ],
    )
    write_csv(
        side_effect_summary_csv,
        side_effect_summary,
        [
            "compare_label",
            "store_file",
            "classification",
            "range_count",
            "total_bytes",
            "first_offset",
            "last_offset",
            "nearest_added_core_distance_min",
        ],
    )
    write_csv(
        payload_signals_csv,
        payload_signals,
        ["compare_label", "command_offset", "term", "relative_offset", "absolute_offset", "context"],
    )
    write_csv(
        negative_controls_csv,
        negative_controls,
        [
            "compare_label",
            "command_offset",
            "control",
            "baseline_guard_accepts_payload_shape",
            "corrupt_lz4_length_value",
            "guard_refused_corrupt_payload",
            "scope",
        ],
    )

    gate_rows = [
        {
            "id": row["id"],
            "status": row["status"],
            "blocker": row["blocker"],
            "detail_json": json.dumps(row.get("detail"), ensure_ascii=False),
        }
        for row in recipe["gates"]
    ]
    write_csv(gates_csv, gate_rows, ["id", "status", "blocker", "detail_json"])

    report = {
        "created_at_utc": utc_now(),
        "operation": "extract_workflow_command_clone_recipe",
        "command_type": "ExportSeismicCmd",
        "project_stem": args.project_stem,
        "first_donor_compare": first,
        "second_donor_compare": second,
        "candidate_payloads": payloads,
        "payload_mutations": payload_mutations,
        "side_effect_summary": side_effect_summary,
        "payload_signals": payload_signals,
        "negative_controls": negative_controls,
        "recipe": recipe,
        "payloads_csv": str(payload_csv),
        "payload_mutations_csv": str(payload_mutations_csv),
        "side_effects_csv": str(side_effects_csv),
        "side_effect_summary_csv": str(side_effect_summary_csv),
        "payload_signals_csv": str(payload_signals_csv),
        "negative_controls_csv": str(negative_controls_csv),
        "gates_csv": str(gates_csv),
        "payload_directory": str(report_dir / "candidate_payloads"),
    }
    report_json.write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines = [
        "# Workflow Command Clone Recipe",
        "",
        f"- Created UTC: {report['created_at_utc']}",
        f"- Command type: {report['command_type']}",
        f"- Recipe status: {recipe['recipe_status']}",
        f"- Safe to apply: {recipe['recipe_safe_to_apply']}",
        f"- Blockers: {recipe['blocker_count']}",
        f"- Candidate payloads: {len(payloads)}",
        "",
        "## Candidate Payloads",
        "",
        "| Donor | Command Offset | Core Length | Extended Length | Core SHA256 |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for row in payloads:
        lines.append(
            f"| {row['compare_label']} | {row['command_offset']} | {row['core_length']} | "
            f"{row['extended_length']} | `{row['core_sha256']}` |"
        )
    lines.extend(["", "## Gates", ""])
    for row in recipe["gates"]:
        marker = "BLOCKER" if row.get("blocker") and row["status"] != "passed" else "INFO"
        lines.append(f"- {row['status']}: {row['id']} [{marker}]")
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "This is a read-only recipe extractor. It writes evidence files only under the report directory and does not patch, clone, resize, or write Petrel native stores.",
            "The current recipe is intentionally blocked until length fields, command indexes, Model.ptd references, GUID/tag behavior, and negative-control recovery are mapped.",
            "",
            "## Outputs",
            "",
            f"- JSON: {report_json}",
            f"- Payload CSV: {payload_csv}",
            f"- Payload mutations CSV: {payload_mutations_csv}",
            f"- Side effects CSV: {side_effects_csv}",
            f"- Side effect summary CSV: {side_effect_summary_csv}",
            f"- Payload signals CSV: {payload_signals_csv}",
            f"- Negative controls CSV: {negative_controls_csv}",
            f"- Gates CSV: {gates_csv}",
            f"- Payload directory: {report_dir / 'candidate_payloads'}",
        ]
    )
    summary_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("Workflow command clone recipe extraction complete")
    print(f"Recipe status: {recipe['recipe_status']}")
    print(f"Safe to apply: {recipe['recipe_safe_to_apply']}")
    print(f"Blockers: {recipe['blocker_count']}")
    print(f"Candidate payloads: {len(payloads)}")
    print(f"Report: {report_json}")
    print(f"Summary: {summary_md}")
    print(f"Payloads: {payload_csv}")
    print(f"Payload mutations: {payload_mutations_csv}")
    print(f"Side effects: {side_effects_csv}")
    print(f"Side effect summary: {side_effect_summary_csv}")
    print(f"Payload signals: {payload_signals_csv}")
    print(f"Negative controls: {negative_controls_csv}")
    print(f"Gates: {gates_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
