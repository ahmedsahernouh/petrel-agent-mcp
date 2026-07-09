#!/usr/bin/env python3
"""Map saved SystemCmd records in the Petrel native workflow store."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROJECT_DIR = REPO_ROOT / "Petrel_DemoData_project"
DEFAULT_PROJECT_STEM = "Petrel2010 demo project ExportPilot"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "build" / "native_edit_experiments"
DEFAULT_TERMS = [
    "SystemCmd",
    "SimpleCmd",
    "powershell.exe",
    "NoProfile",
    "ExecutionPolicy",
    "Policy",
    "Bypass",
    "File",
    "mvp_bridge",
    "petrel_export_mvp_bridge.ps1",
    "StepName",
    "post",
    "register_validate",
    "bridge",
    "validate",
    "BXML",
    "LZ4",
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


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def term_hits(data: bytes, terms: list[str], start: int, end: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for term in terms:
        for offset in find_offsets(data, term):
            if start <= offset < end:
                rows.append(
                    {
                        "term": term,
                        "offset": offset,
                        "relative_offset": offset - start,
                        "context": printable_context(data, offset - 80, 300),
                    }
                )
    return sorted(rows, key=lambda row: (row["offset"], row["term"]))


def map_data_records(data: bytes, terms: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    bxml_offsets = sorted(find_offsets(data, "BXML"))
    lz4_offsets = sorted(find_offsets(data, "LZ4"))
    command_offsets = find_offsets(data, "SystemCmd")
    records: list[dict[str, Any]] = []
    token_rows: list[dict[str, Any]] = []

    for index, command_offset in enumerate(command_offsets):
        previous_bxml = nearest_before(bxml_offsets, command_offset)
        previous_lz4 = nearest_before(lz4_offsets, command_offset)
        next_bxml = nearest_after(bxml_offsets, command_offset)
        next_lz4 = nearest_after(lz4_offsets, command_offset)
        next_next_bxml = nearest_after(bxml_offsets, next_bxml or command_offset) if next_bxml is not None else None
        envelope_start = previous_lz4 if previous_lz4 is not None else previous_bxml if previous_bxml is not None else command_offset
        envelope_end = next_next_bxml if next_next_bxml is not None else next_bxml if next_bxml is not None else min(len(data), command_offset + 4096)
        hits = term_hits(data, terms, envelope_start, envelope_end)
        for hit in hits:
            token_rows.append({"record_index": index, **hit})

        records.append(
            {
                "record_index": index,
                "command_offset": command_offset,
                "previous_lz4_offset": previous_lz4,
                "previous_bxml_offset": previous_bxml,
                "next_bxml_offset": next_bxml,
                "next_lz4_offset": next_lz4,
                "next_next_bxml_offset": next_next_bxml,
                "envelope_start": envelope_start,
                "envelope_end": envelope_end,
                "envelope_length": envelope_end - envelope_start,
                "command_span_to_next_bxml": (next_bxml - previous_bxml) if previous_bxml is not None and next_bxml is not None else None,
                "context": printable_context(data, command_offset - 240, 1000),
            }
        )

    return records, token_rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-directory", default=str(DEFAULT_PROJECT_DIR))
    parser.add_argument("--project-stem", default=DEFAULT_PROJECT_STEM)
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--terms", default="|".join(DEFAULT_TERMS))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_dir = Path(args.project_directory).resolve()
    ptd_dir = project_dir / f"{args.project_stem}.ptd"
    data_path = ptd_dir / "Data.ptd"
    model_path = ptd_dir / "Model.ptd"
    if not data_path.is_file():
        raise FileNotFoundError(f"Data.ptd not found: {data_path}")
    if not model_path.is_file():
        raise FileNotFoundError(f"Model.ptd not found: {model_path}")

    terms = [term for term in args.terms.split("|") if term]
    data = data_path.read_bytes()
    model = model_path.read_bytes()
    records, token_rows = map_data_records(data, terms)

    model_hits = []
    for term in terms:
        for offset in find_offsets(model, term):
            model_hits.append(
                {
                    "term": term,
                    "offset": offset,
                    "context": printable_context(model, offset - 100, 360),
                }
            )
    model_hits.sort(key=lambda row: (row["offset"], row["term"]))

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = Path(args.output_root).resolve() / f"systemcmd_record_map_{stamp}"
    report_dir.mkdir(parents=True, exist_ok=True)
    records_csv = report_dir / "systemcmd_records.csv"
    tokens_csv = report_dir / "systemcmd_token_hits.csv"
    model_csv = report_dir / "systemcmd_model_hits.csv"
    report_json = report_dir / "systemcmd_record_map.json"
    summary_md = report_dir / "systemcmd_record_map_summary.md"

    write_csv(
        records_csv,
        records,
        [
            "record_index",
            "command_offset",
            "previous_lz4_offset",
            "previous_bxml_offset",
            "next_bxml_offset",
            "next_lz4_offset",
            "next_next_bxml_offset",
            "envelope_start",
            "envelope_end",
            "envelope_length",
            "command_span_to_next_bxml",
            "context",
        ],
    )
    write_csv(tokens_csv, token_rows, ["record_index", "term", "offset", "relative_offset", "context"])
    write_csv(model_csv, model_hits, ["term", "offset", "context"])

    report = {
        "created_at_utc": utc_now(),
        "project_directory": str(project_dir),
        "project_stem": args.project_stem,
        "data_path": str(data_path),
        "model_path": str(model_path),
        "data_sha256": sha256_bytes(data),
        "model_sha256": sha256_bytes(model),
        "record_count": len(records),
        "terms": terms,
        "records_csv": str(records_csv),
        "token_hits_csv": str(tokens_csv),
        "model_hits_csv": str(model_csv),
        "records": records,
        "token_hits": token_rows,
        "model_hits": model_hits,
    }
    report_json.write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines = [
        "# SystemCmd Record Map",
        "",
        f"- Created UTC: {report['created_at_utc']}",
        f"- Data.ptd: {data_path}",
        f"- Data SHA256: {report['data_sha256']}",
        f"- Model SHA256: {report['model_sha256']}",
        f"- SystemCmd records: {len(records)}",
        "",
        "## Records",
        "",
        "| Index | Command Offset | Previous LZ4 | Previous BXML | Next BXML | Envelope Length |",
        "| ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in records:
        lines.append(
            f"| {row['record_index']} | {row['command_offset']} | {row['previous_lz4_offset']} | "
            f"{row['previous_bxml_offset']} | {row['next_bxml_offset']} | {row['envelope_length']} |"
        )
    lines.extend(["", "## Bridge Token Candidates", ""])
    candidate_terms = {"powershell.exe", "NoProfile", "Policy", "Bypass", "mvp_bridge", "StepName", "post", "register_validate"}
    for row in token_rows:
        if row["term"] in candidate_terms:
            lines.append(f"- record {row['record_index']}: `{row['term']}` at Data.ptd offset `{row['offset']}`")
    lines.extend(
        [
            "",
            "## Outputs",
            "",
            f"- JSON: {report_json}",
            f"- Records CSV: {records_csv}",
            f"- Token hits CSV: {tokens_csv}",
            f"- Model hits CSV: {model_csv}",
        ]
    )
    summary_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("SystemCmd record map complete")
    print(f"Report: {report_json}")
    print(f"Summary: {summary_md}")
    print(f"Records: {records_csv}")
    print(f"Token hits: {tokens_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
