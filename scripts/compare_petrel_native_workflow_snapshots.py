#!/usr/bin/env python3
"""Fast before/after diff for Petrel native workflow snapshots."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "build" / "native_edit_experiments"
DEFAULT_TERMS = "SheetSaveCmd|SystemCmd|powershell.exe|petrel_export_mvp_bridge.ps1|export_package|cli_variable|BXML|LZ4"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def split_pipe(value: str) -> list[str]:
    return [item for item in value.split("|") if item.strip()]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def printable_context(data: bytes, start: int, length: int) -> str:
    if start >= len(data):
        return ""
    start = max(0, start)
    end = min(len(data), start + max(0, length))
    return "".join(chr(byte) if 32 <= byte <= 126 else "." for byte in data[start:end])


def diff_ranges(before: bytes, after: bytes, chunk_size: int = 1024 * 1024) -> list[dict[str, int]]:
    if before == after:
        return []

    ranges: list[dict[str, int]] = []
    max_len = max(len(before), len(after))
    current_start: int | None = None
    current_end: int | None = None

    def close_range() -> None:
        nonlocal current_start, current_end
        if current_start is not None and current_end is not None:
            ranges.append(
                {
                    "start_offset": current_start,
                    "end_offset": current_end,
                    "length": current_end - current_start + 1,
                }
            )
        current_start = None
        current_end = None

    for chunk_start in range(0, max_len, chunk_size):
        before_chunk = before[chunk_start : min(len(before), chunk_start + chunk_size)]
        after_chunk = after[chunk_start : min(len(after), chunk_start + chunk_size)]
        if before_chunk == after_chunk and len(before_chunk) == len(after_chunk):
            close_range()
            continue

        local_max = max(len(before_chunk), len(after_chunk))
        for index in range(local_max):
            absolute = chunk_start + index
            before_byte = before_chunk[index] if index < len(before_chunk) else None
            after_byte = after_chunk[index] if index < len(after_chunk) else None
            if before_byte != after_byte:
                if current_start is None:
                    current_start = absolute
                current_end = absolute
            else:
                close_range()

    close_range()
    return ranges


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
    candidate: int | None = None
    for item in offsets:
        if item <= offset:
            candidate = item
        else:
            break
    return candidate


def nearest_after(offsets: list[int], offset: int) -> int | None:
    for item in offsets:
        if item > offset:
            return item
    return None


def command_type_guess(context: str) -> str:
    import re

    matches = re.findall(r"[A-Za-z][A-Za-z0-9_]{2,}Cmd", context)
    return ";".join(dict.fromkeys(matches))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def map_terms(data: bytes, terms: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    bxml_offsets = sorted(find_offsets(data, "BXML"))
    lz4_offsets = sorted(find_offsets(data, "LZ4"))

    term_rows: list[dict[str, Any]] = []
    for term in terms:
        for offset in find_offsets(data, term):
            context = printable_context(data, max(0, offset - 260), 1020)
            term_rows.append(
                {
                    "term": term,
                    "offset": offset,
                    "previous_lz4_offset": nearest_before(lz4_offsets, offset),
                    "previous_bxml_offset": nearest_before(bxml_offsets, offset),
                    "next_bxml_offset": nearest_after(bxml_offsets, offset),
                    "next_lz4_offset": nearest_after(lz4_offsets, offset),
                    "command_type_guess": command_type_guess(context),
                    "context": context,
                }
            )

    chunk_rows: list[dict[str, Any]] = []
    for index, offset in enumerate(bxml_offsets):
        next_bxml = bxml_offsets[index + 1] if index + 1 < len(bxml_offsets) else len(data)
        context = printable_context(data, max(0, offset - 80), 600)
        chunk_rows.append(
            {
                "bxml_index": index,
                "bxml_offset": offset,
                "previous_lz4_offset": nearest_before(lz4_offsets, offset),
                "next_bxml_offset": next_bxml,
                "approx_span_to_next_bxml": next_bxml - offset,
                "command_type_guess": command_type_guess(context),
                "context": context,
            }
        )

    return term_rows, chunk_rows


def compare_store(
    before_snapshot: Path,
    after_snapshot: Path,
    project_stem: str,
    store_file: str,
    terms: list[str],
    report_dir: Path,
) -> dict[str, Any]:
    before_store = before_snapshot / f"{project_stem}.ptd" / store_file
    after_store = after_snapshot / f"{project_stem}.ptd" / store_file
    if not before_store.is_file():
        raise FileNotFoundError(f"Before store not found: {before_store}")
    if not after_store.is_file():
        raise FileNotFoundError(f"After store not found: {after_store}")

    before_bytes = before_store.read_bytes()
    after_bytes = after_store.read_bytes()
    ranges = diff_ranges(before_bytes, after_bytes)

    safe_store = "".join(char if char.isalnum() or char in "._-" else "_" for char in store_file)
    diff_csv = report_dir / f"diff_ranges_{safe_store}.csv"
    preview_csv = report_dir / f"diff_previews_{safe_store}.csv"
    term_csv = report_dir / f"term_map_{safe_store}.csv"
    chunk_csv = report_dir / f"bxml_chunks_{safe_store}.csv"

    write_csv(diff_csv, ranges, ["start_offset", "end_offset", "length"])

    previews: list[dict[str, Any]] = []
    for item in ranges[:50]:
        context_start = max(0, item["start_offset"] - 80)
        context_length = item["length"] + 160
        previews.append(
            {
                "start_offset": item["start_offset"],
                "end_offset": item["end_offset"],
                "length": item["length"],
                "before_context": printable_context(before_bytes, context_start, context_length),
                "after_context": printable_context(after_bytes, context_start, context_length),
            }
        )
    write_csv(preview_csv, previews, ["start_offset", "end_offset", "length", "before_context", "after_context"])

    term_rows, chunk_rows = map_terms(after_bytes, terms)
    write_csv(
        term_csv,
        term_rows,
        [
            "term",
            "offset",
            "previous_lz4_offset",
            "previous_bxml_offset",
            "next_bxml_offset",
            "next_lz4_offset",
            "command_type_guess",
            "context",
        ],
    )
    write_csv(
        chunk_csv,
        chunk_rows,
        [
            "bxml_index",
            "bxml_offset",
            "previous_lz4_offset",
            "next_bxml_offset",
            "approx_span_to_next_bxml",
            "command_type_guess",
            "context",
        ],
    )

    return {
        "store_file": store_file,
        "before_path": str(before_store),
        "after_path": str(after_store),
        "before_length": len(before_bytes),
        "after_length": len(after_bytes),
        "before_sha256": sha256_bytes(before_bytes),
        "after_sha256": sha256_bytes(after_bytes),
        "changed": before_bytes != after_bytes,
        "length_delta": len(after_bytes) - len(before_bytes),
        "diff_range_count": len(ranges),
        "diff_ranges_csv": str(diff_csv),
        "diff_previews_csv": str(preview_csv),
        "term_map_csv": str(term_csv),
        "bxml_chunks_csv": str(chunk_csv),
        "term_hit_count": len(term_rows),
        "bxml_marker_count": len(chunk_rows),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before-snapshot", required=True)
    parser.add_argument("--after-snapshot", required=True)
    parser.add_argument("--project-stem", default="Petrel2010 demo project ExportPilot")
    parser.add_argument("--store-files", default="Model.ptd|Data.ptd")
    parser.add_argument("--terms", default=DEFAULT_TERMS)
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    before_snapshot = Path(args.before_snapshot).resolve()
    after_snapshot = Path(args.after_snapshot).resolve()
    output_root = Path(args.output_root).resolve()
    if not before_snapshot.is_dir():
        raise FileNotFoundError(f"Before snapshot not found: {before_snapshot}")
    if not after_snapshot.is_dir():
        raise FileNotFoundError(f"After snapshot not found: {after_snapshot}")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = output_root / f"native_workflow_snapshot_compare_{stamp}"
    report_dir.mkdir(parents=True, exist_ok=True)

    store_files = split_pipe(args.store_files)
    terms = split_pipe(args.terms)
    store_summaries = [
        compare_store(before_snapshot, after_snapshot, args.project_stem, store_file, terms, report_dir)
        for store_file in store_files
    ]

    report = {
        "created_at_utc": utc_now(),
        "before_snapshot": str(before_snapshot),
        "after_snapshot": str(after_snapshot),
        "project_stem": args.project_stem,
        "store_files": store_files,
        "terms": terms,
        "report_directory": str(report_dir),
        "store_summaries": store_summaries,
    }
    report_json = report_dir / "snapshot_compare_report.json"
    report_json.write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines = [
        "# Petrel Native Workflow Snapshot Compare",
        "",
        f"- Created UTC: {report['created_at_utc']}",
        f"- Before snapshot: {before_snapshot}",
        f"- After snapshot: {after_snapshot}",
        f"- Project stem: {args.project_stem}",
        f"- Report directory: {report_dir}",
        "",
        "## Store Summary",
        "",
        "| Store | Changed | Before bytes | After bytes | Length delta | Diff ranges | Term hits | BXML markers |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for store in store_summaries:
        lines.append(
            f"| {store['store_file']} | {store['changed']} | {store['before_length']} | "
            f"{store['after_length']} | {store['length_delta']} | {store['diff_range_count']} | "
            f"{store['term_hit_count']} | {store['bxml_marker_count']} |"
        )
    lines.extend(["", "## Outputs", "", f"- JSON report: {report_json}"])
    for store in store_summaries:
        lines.append(f"- {store['store_file']} diff ranges: {store['diff_ranges_csv']}")
        lines.append(f"- {store['store_file']} diff previews: {store['diff_previews_csv']}")
        lines.append(f"- {store['store_file']} term map: {store['term_map_csv']}")
        lines.append(f"- {store['store_file']} BXML chunks: {store['bxml_chunks_csv']}")

    report_md = report_dir / "snapshot_compare_summary.md"
    report_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("Native workflow snapshot compare complete")
    print(f"Report: {report_json}")
    print(f"Summary: {report_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
