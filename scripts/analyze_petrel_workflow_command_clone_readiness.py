#!/usr/bin/env python3
"""Assess whether saved Petrel Workflow Editor command records are ready for safe zero-GUI cloning."""

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
DEFAULT_FIRST_DONOR_COMPARE = (
    DEFAULT_OUTPUT_ROOT / "native_workflow_snapshot_compare_20260703_012602" / "snapshot_compare_report.json"
)
DEFAULT_SECOND_DONOR_COMPARE = (
    DEFAULT_OUTPUT_ROOT / "native_workflow_snapshot_compare_20260703_054200" / "snapshot_compare_report.json"
)
DEFAULT_FILENAME_PATCH_PROOF = (
    DEFAULT_OUTPUT_ROOT / "segy_filename_patch_export_20260703_030410" / "segy_filename_patch_export_report.json"
)
DEFAULT_TOKEN_PATCH_PROOF = (
    DEFAULT_OUTPUT_ROOT / "segy_token_patch_export_20260703_055859" / "segy_token_patch_export_report.json"
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
                        "context": printable_context(data, offset - 80, 260),
                    }
                )
    return sorted(rows, key=lambda row: (row["offset"], row["term"]))


def map_exportseismic_records(data: bytes, terms: list[str], include_context: bool) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    bxml_offsets = sorted(find_offsets(data, "BXML"))
    lz4_offsets = sorted(find_offsets(data, "LZ4"))
    command_offsets = find_offsets(data, "ExportSeismicCmd")
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
            if not include_context:
                hit = {key: value for key, value in hit.items() if key != "context"}
            token_rows.append({"record_index": index, **hit})

        row = {
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
        }
        if include_context:
            row["context"] = printable_context(data, command_offset - 220, 900)
        records.append(row)

    return records, token_rows


def load_compare_summary(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        return {"label": label, "path": str(path), "loaded": False, "error": "report_not_found", "store_summaries": []}
    try:
        report = read_json(path)
    except Exception as exc:
        return {"label": label, "path": str(path), "loaded": False, "error": str(exc), "store_summaries": []}

    stores = []
    for store in report.get("store_summaries", []):
        stores.append(
            {
                "store_file": store.get("store_file"),
                "changed": bool(store.get("changed")),
                "before_length": store.get("before_length"),
                "after_length": store.get("after_length"),
                "length_delta": store.get("length_delta"),
                "diff_range_count": store.get("diff_range_count"),
                "term_hit_count": store.get("term_hit_count"),
                "bxml_marker_count": store.get("bxml_marker_count"),
                "diff_ranges_csv": store.get("diff_ranges_csv"),
                "diff_previews_csv": store.get("diff_previews_csv"),
                "term_map_csv": store.get("term_map_csv"),
                "bxml_chunks_csv": store.get("bxml_chunks_csv"),
            }
        )
    return {
        "label": label,
        "path": str(path),
        "loaded": True,
        "before_snapshot": report.get("before_snapshot"),
        "after_snapshot": report.get("after_snapshot"),
        "terms": report.get("terms", []),
        "store_summaries": stores,
    }


def load_patch_proof(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        return {"label": label, "path": str(path), "loaded": False, "status": "missing"}
    try:
        report = read_json(path)
    except Exception as exc:
        return {"label": label, "path": str(path), "loaded": False, "status": "unreadable", "error": str(exc)}
    validation = report.get("validation") if isinstance(report.get("validation"), dict) else {}
    return {
        "label": label,
        "path": str(path),
        "loaded": True,
        "status": report.get("status"),
        "patch_applied": bool(report.get("patch_applied")),
        "restored": bool(report.get("restored")),
        "restore_compare_clean": report.get("restore_compare_clean"),
        "validation_status": validation.get("status"),
        "validation_failed_count": validation.get("failed_count"),
        "target_output_file": report.get("target_output_file"),
        "target_output": report.get("target_output"),
    }


def store_by_name(compare: dict[str, Any], store_file: str) -> dict[str, Any]:
    for store in compare.get("store_summaries", []):
        if store.get("store_file") == store_file:
            return store
    return {}


def gate(gates: list[dict[str, Any]], gate_id: str, status: str, detail: Any = None, blocker: bool = False) -> None:
    row: dict[str, Any] = {"id": gate_id, "status": status, "blocker": bool(blocker)}
    if detail is not None:
        row["detail"] = detail
    gates.append(row)


def evaluate_readiness(
    records: list[dict[str, Any]],
    first_compare: dict[str, Any],
    second_compare: dict[str, Any],
    patch_proofs: list[dict[str, Any]],
) -> dict[str, Any]:
    gates: list[dict[str, Any]] = []

    gate(gates, "two_exportseismiccmd_records_present", "passed" if len(records) >= 2 else "failed", {"record_count": len(records)}, blocker=len(records) < 2)

    bounded = [
        record
        for record in records
        if record.get("previous_lz4_offset") is not None
        and record.get("previous_bxml_offset") is not None
        and record.get("next_bxml_offset") is not None
        and int(record.get("envelope_length") or 0) > 0
    ]
    gate(gates, "record_envelopes_bounded", "passed" if len(bounded) == len(records) and records else "failed", {"bounded": len(bounded), "record_count": len(records)}, blocker=len(bounded) != len(records))

    span_values = sorted({record.get("command_span_to_next_bxml") for record in records if record.get("command_span_to_next_bxml") is not None})
    envelope_values = sorted({record.get("envelope_length") for record in records if record.get("envelope_length") is not None})
    gate(gates, "record_spans_are_uniform", "passed" if len(span_values) == 1 else "failed", {"command_spans": span_values, "envelope_lengths": envelope_values}, blocker=len(span_values) != 1)

    donor_loaded = first_compare.get("loaded") and second_compare.get("loaded")
    gate(
        gates,
        "donor_compare_reports_loaded",
        "passed" if donor_loaded else "failed",
        {"first": first_compare.get("path"), "second": second_compare.get("path")},
        blocker=not donor_loaded,
    )

    for compare in (first_compare, second_compare):
        label = str(compare.get("label"))
        model = store_by_name(compare, "Model.ptd")
        data = store_by_name(compare, "Data.ptd")
        model_detail = {
            "changed": model.get("changed"),
            "length_delta": model.get("length_delta"),
            "diff_range_count": model.get("diff_range_count"),
        }
        data_detail = {
            "changed": data.get("changed"),
            "length_delta": data.get("length_delta"),
            "diff_range_count": data.get("diff_range_count"),
        }
        model_is_simple = bool(model) and model.get("changed") is False and int(model.get("length_delta") or 0) == 0
        data_is_simple = bool(data) and int(data.get("length_delta") or 0) == 0 and int(data.get("diff_range_count") or 0) <= 10
        gate(gates, f"{label}_model_changes_isolated", "passed" if model_is_simple else "failed", model_detail, blocker=not model_is_simple)
        gate(gates, f"{label}_data_payload_changes_isolated", "passed" if data_is_simple else "failed", data_detail, blocker=not data_is_simple)

    proof_statuses = []
    for proof in patch_proofs:
        validation_failed = proof.get("validation_failed_count")
        try:
            validation_failed_int = int(validation_failed)
        except (TypeError, ValueError):
            validation_failed_int = -1
        passed = (
            proof.get("loaded")
            and proof.get("status") == "passed"
            and proof.get("patch_applied") is True
            and proof.get("restored") is True
            and proof.get("validation_status") == "passed"
            and validation_failed_int == 0
        )
        proof_statuses.append({"label": proof.get("label"), "passed": passed, "path": proof.get("path")})
    gate(
        gates,
        "same_length_parameter_mutation_proven",
        "passed" if proof_statuses and all(item["passed"] for item in proof_statuses) else "failed",
        proof_statuses,
        blocker=False,
    )

    known_unknowns = [
        "workflow command-list index mutation is not isolated",
        "Model.ptd UI tree or object-reference updates are not mapped",
        "BXML/LZ4 record length fields are not mapped for insertion",
        "unique_tag/GUID behavior is not mapped for cloned commands",
        "negative-control clone failure and recovery have not been run",
    ]
    for item in known_unknowns:
        gate(gates, item.replace(" ", "_").replace("/", "_"), "failed", item, blocker=True)

    blocker_count = sum(1 for item in gates if item["status"] != "passed" and item.get("blocker"))
    failed_count = sum(1 for item in gates if item["status"] != "passed")
    clone_safe = blocker_count == 0
    return {
        "clone_safe": clone_safe,
        "status": "blocked" if not clone_safe else "ready",
        "failed_gate_count": failed_count,
        "blocker_count": blocker_count,
        "gates": gates,
        "supported_now": [
            "read-only record mapping",
            "same-length parameter mutation at known offsets",
            "patch-run-restore wrappers for saved donor parameters",
        ],
        "not_supported_yet": [
            "variable-length command insertion",
            "new workflow creation",
            "ExportSeismicCmd object-reference mutation",
            "export-format enum mutation",
            "command clone patch application",
        ],
        "next_required_evidence": [
            "diffs that isolate command-list index updates from unrelated Model.ptd churn",
            "record-envelope and size-field map for inserted BXML/LZ4 payloads",
            "unique_tag/GUID generation or reuse rule",
            "negative-control clone dry-run that refuses a deliberately wrong envelope",
            "restore-and-validate recovery proof after any future clone attempt",
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-directory", default=str(DEFAULT_PROJECT_DIR))
    parser.add_argument("--project-stem", default=DEFAULT_PROJECT_STEM)
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--first-donor-compare-report", default=str(DEFAULT_FIRST_DONOR_COMPARE))
    parser.add_argument("--second-donor-compare-report", default=str(DEFAULT_SECOND_DONOR_COMPARE))
    parser.add_argument("--filename-patch-proof", default=str(DEFAULT_FILENAME_PATCH_PROOF))
    parser.add_argument("--token-patch-proof", default=str(DEFAULT_TOKEN_PATCH_PROOF))
    parser.add_argument("--terms", default="|".join(DEFAULT_TERMS))
    parser.add_argument("--include-context", action="store_true")
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
    records, token_rows = map_exportseismic_records(data, terms, include_context=bool(args.include_context))

    first_compare = load_compare_summary(Path(args.first_donor_compare_report).resolve(), "first_donor")
    second_compare = load_compare_summary(Path(args.second_donor_compare_report).resolve(), "second_donor")
    patch_proofs = [
        load_patch_proof(Path(args.filename_patch_proof).resolve(), "filename_tail_patch"),
        load_patch_proof(Path(args.token_patch_proof).resolve(), "second_command_token_patch"),
    ]
    readiness = evaluate_readiness(records, first_compare, second_compare, patch_proofs)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = Path(args.output_root).resolve() / f"workflow_command_clone_readiness_{stamp}"
    report_dir.mkdir(parents=True, exist_ok=True)
    records_csv = report_dir / "clone_readiness_command_records.csv"
    gates_csv = report_dir / "clone_readiness_gates.csv"
    report_json = report_dir / "workflow_command_clone_readiness.json"
    summary_md = report_dir / "workflow_command_clone_readiness_summary.md"

    record_fields = [
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
    ]
    if args.include_context:
        record_fields.append("context")
    write_csv(records_csv, records, record_fields)
    gate_rows = [
        {
            "id": item["id"],
            "status": item["status"],
            "blocker": item["blocker"],
            "detail_json": json.dumps(item.get("detail", ""), ensure_ascii=False),
        }
        for item in readiness["gates"]
    ]
    write_csv(gates_csv, gate_rows, ["id", "status", "blocker", "detail_json"])

    report = {
        "created_at_utc": utc_now(),
        "project_directory": str(project_dir),
        "project_stem": args.project_stem,
        "data_path": str(data_path),
        "model_path": str(model_path),
        "data_sha256": sha256_bytes(data),
        "model_sha256": sha256_bytes(model),
        "command_type": "ExportSeismicCmd",
        "record_count": len(records),
        "terms": terms,
        "records": records,
        "token_hits": token_rows,
        "first_donor_compare": first_compare,
        "second_donor_compare": second_compare,
        "patch_proofs": patch_proofs,
        "readiness": readiness,
        "records_csv": str(records_csv),
        "gates_csv": str(gates_csv),
    }
    report_json.write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines = [
        "# Workflow Command Clone Readiness",
        "",
        f"- Created UTC: {report['created_at_utc']}",
        f"- Command type: {report['command_type']}",
        f"- Clone safe: {readiness['clone_safe']}",
        f"- Status: {readiness['status']}",
        f"- Blockers: {readiness['blocker_count']}",
        f"- Failed gates: {readiness['failed_gate_count']}",
        f"- Data SHA256: {report['data_sha256']}",
        f"- Model SHA256: {report['model_sha256']}",
        "",
        "## Current Records",
        "",
        "| Index | Command Offset | Previous LZ4 | Previous BXML | Next BXML | Span | Envelope Length |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in records:
        lines.append(
            f"| {row['record_index']} | {row['command_offset']} | {row['previous_lz4_offset']} | "
            f"{row['previous_bxml_offset']} | {row['next_bxml_offset']} | {row['command_span_to_next_bxml']} | "
            f"{row['envelope_length']} |"
        )
    lines.extend(["", "## Gate Summary", ""])
    for item in readiness["gates"]:
        marker = "BLOCKER" if item.get("blocker") and item["status"] != "passed" else "INFO"
        lines.append(f"- {item['status']}: {item['id']} [{marker}]")
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "This is a read-only readiness report. It does not patch, clone, insert, resize, or write any Petrel native store.",
            "Current result should remain `clone_safe=false` until the broad Model/Data donor changes are isolated into a reproducible record/index/length/GUID map.",
            "",
            "## Outputs",
            "",
            f"- JSON: {report_json}",
            f"- Records CSV: {records_csv}",
            f"- Gates CSV: {gates_csv}",
        ]
    )
    summary_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("Workflow command clone readiness complete")
    print(f"Clone safe: {readiness['clone_safe']}")
    print(f"Status: {readiness['status']}")
    print(f"Blockers: {readiness['blocker_count']}")
    print(f"Report: {report_json}")
    print(f"Summary: {summary_md}")
    print(f"Records: {records_csv}")
    print(f"Gates: {gates_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
