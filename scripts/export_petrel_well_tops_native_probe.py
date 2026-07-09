#!/usr/bin/env python3
"""Probe Petrel native stores for well-top names and candidate LAS links.

This is a zero-GUI probe. It does not use Ocean and does not claim to decode
Petrel's native marker-pick payload. It produces inspectable evidence rows that
connect native top-name strings and LAS zone-log values linked to Well Tops.
When the original Petrel well-tops ASCII source file is present locally, it also
parses that file into a clean table and labels it as source-derived rather than
native-binary-decoded.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
import shlex
from pathlib import Path
from typing import Any


PROJECT_NAME_DEFAULT = "Petrel2010 demo project"
PETREL_VERSION_DEFAULT = "2018.2.0.5333"
SOURCE_WELL_TOPS_DEFAULT_REL = Path("petrel_manuals") / "Petrel Course - Sayed Fathy" / "DATA" / "Well Tops" / "Well tops"
CANONICAL_NATIVE_TOPS = ["T_Tarbert [Converted]", "T_Ness", "T_Etive", "Seabed", "BCU"]


def clean(value: Any) -> str:
    text = "" if value is None else str(value)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def win_rel(base: Path, path: Path) -> str:
    return os.path.relpath(path, base).replace("/", "\\")


def project_rel(path: Path) -> str:
    root = Path(__file__).resolve().parents[1]
    try:
        return win_rel(root, path)
    except ValueError:
        return str(path)


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: clean(row.get(field, "")) for field in fieldnames})


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def canonical_top_name(raw_name: str) -> str:
    name = clean(raw_name)
    if name.startswith("T_Tarber"):
        return "T_Tarbert [Converted]" if "Converted" in name else "T_Tarbert"
    if name.startswith("T_Ne") or name == "T_N":
        return "T_Ness"
    if name.startswith("T_E"):
        return "T_Etive"
    if name.startswith("Seabe"):
        return "Seabed"
    if name == "BCU":
        return "BCU"
    return name


def canonical_source_top_name(raw_name: str) -> str:
    name = clean(raw_name)
    lower = name.lower()
    if lower in {"base cretaceous", "bcu"}:
        return "BCU"
    if lower.startswith("top tarbert") or lower.startswith("tarbert"):
        return "T_Tarbert [Converted]"
    if lower.startswith("top ness") or lower.startswith("ness"):
        return "T_Ness"
    if lower.startswith("top etive"):
        return "T_Etive"
    if lower.startswith("seabed"):
        return "Seabed"
    return name


def native_files_for_probe(project_file: Path) -> list[Path]:
    ptd_dir = project_file.with_suffix(".ptd")
    candidates = [
        project_file,
        ptd_dir / "Model.ptd",
        ptd_dir / "Data.ptd",
        ptd_dir / "SMD" / "ModelingData.xml",
    ]
    return [path for path in candidates if path.exists() and path.is_file()]


def native_top_name_occurrences(project_file: Path) -> tuple[list[dict[str, Any]], list[str]]:
    patterns: list[tuple[str, bytes]] = [
        ("T_Tarbert [Converted]", b"T_Tarbert [Converted]"),
        ("T_Tarbert", b"T_Tarbert"),
        ("T_Ness", b"T_Ness"),
        ("T_Etive", b"T_Etive"),
        ("Seabed", b"Seabe"),
        ("BCU", b"BCU"),
    ]
    hits: list[dict[str, Any]] = []
    for native_file in native_files_for_probe(project_file):
        data = native_file.read_bytes()
        for canonical, pattern in patterns:
            start = 0
            while True:
                offset = data.find(pattern, start)
                if offset < 0:
                    break
                hits.append(
                    {
                        "top_name": canonical,
                        "source_file": project_rel(native_file),
                        "byte_offset": offset,
                    }
                )
                start = offset + 1

    best_cluster: list[dict[str, Any]] = []
    best_score = -1
    for anchor in hits:
        anchor_file = anchor["source_file"]
        anchor_offset = int(anchor["byte_offset"])
        cluster = [
            hit
            for hit in hits
            if hit["source_file"] == anchor_file and abs(int(hit["byte_offset"]) - anchor_offset) <= 350
        ]
        unique_names = {str(hit["top_name"]) for hit in cluster}
        score = len(unique_names) * 100 - len(cluster)
        if "T_Tarbert [Converted]" in unique_names:
            score += 25
        if score > best_score:
            best_score = score
            best_cluster = cluster

    ordered_names: list[str] = []
    rows: list[dict[str, Any]] = []
    for hit in sorted(best_cluster, key=lambda item: int(item["byte_offset"])):
        name = str(hit["top_name"])
        if name == "T_Tarbert" and "T_Tarbert [Converted]" in ordered_names:
            continue
        if name not in ordered_names:
            ordered_names.append(name)
            rows.append(
                {
                    "evidence_class": "native_binary_top_name_dictionary",
                    "native_binary_confirmed": "no",
                    "well_name": "",
                    "top_name": name,
                    "canonical_top_name": canonical_top_name(name),
                    "measured_depth": "",
                    "depth_unit": "",
                    "source_value": "",
                    "source_file": hit["source_file"],
                    "byte_offset": hit["byte_offset"],
                    "decode_status": "top_name_string_cluster_found_pick_depth_payload_not_decoded",
                    "evidence_summary": "Canonical top-name string found in a native cluster; no marker-pick depth row decoded from this string.",
                }
            )

    return rows, ordered_names


def native_history_rows(project_file: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    ptd_dir = project_file.with_suffix(".ptd")
    data_file = ptd_dir / "Data.ptd"
    if not data_file.exists():
        return rows
    data = data_file.read_bytes()
    for term in (b"Well Tops (depth)", b"Zone log from 'Well Tops'", b"Zone log linked to 'Well Tops'"):
        start = 0
        while True:
            offset = data.find(term, start)
            if offset < 0:
                break
            rows.append(
                {
                    "evidence_class": "native_binary_history_or_dictionary",
                    "native_binary_confirmed": "no",
                    "well_name": "",
                    "top_name": "Well Tops",
                    "canonical_top_name": "",
                    "measured_depth": "",
                    "depth_unit": "",
                    "source_value": term.decode("ascii", errors="replace"),
                    "source_file": project_rel(data_file),
                    "byte_offset": offset,
                    "decode_status": "native_history_or_dictionary_string_found_pick_rows_not_decoded",
                    "evidence_summary": "Readable native BXML/history string; useful provenance but not a decoded marker-pick table.",
                }
            )
            start = offset + 1
    return rows


def split_las_sections(lines: list[str]) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current = ""
    for raw in lines:
        stripped = raw.strip()
        if stripped.startswith("~"):
            match = re.match(r"^~\s*([A-Za-z]+)", stripped)
            current = match.group(1).lower() if match else "other"
            sections.setdefault(current, [])
            continue
        if current:
            sections.setdefault(current, []).append(raw.rstrip("\r\n"))
    return sections


def parse_las_record(line: str) -> dict[str, str] | None:
    before_colon, _, description = line.strip().partition(":")
    match = re.match(r"^\s*([^.\s]+)\s*\.([^\s]*)\s*(.*?)\s*$", before_colon)
    if not match:
        return None
    return {
        "mnemonic": clean(match.group(1)),
        "unit": clean(match.group(2)),
        "value": clean(match.group(3)),
        "description": clean(description),
    }


def is_null(value: str, null_value: str) -> bool:
    try:
        return abs(float(value) - float(null_value)) < 1e-9
    except ValueError:
        return clean(value) == clean(null_value)


def las_zone_link_candidates(export_package: Path, top_order: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for las_path in sorted((export_package / "02_wells" / "well_logs_las").rglob("*.las")):
        lines = las_path.read_text(encoding="utf-8", errors="replace").splitlines()
        sections = split_las_sections(lines)
        well_records = [item for line in sections.get("well", []) if (item := parse_las_record(line))]
        curve_records = [item for line in sections.get("curve", []) if (item := parse_las_record(line))]
        header = {record["mnemonic"].upper(): record for record in well_records}
        null_value = header.get("NULL", {}).get("value", "-999.25")
        well_name = header.get("WELL", {}).get("value", las_path.stem)
        top_curve_index = None
        top_curve = None
        for index, curve in enumerate(curve_records):
            probe = f"{curve.get('mnemonic', '')} {curve.get('description', '')}".lower()
            if "welltops" in probe or "well tops" in probe or "marker" in probe:
                top_curve_index = index
                top_curve = curve
                break
        if top_curve_index is None:
            continue
        for row_index, raw in enumerate(sections.get("ascii", []), start=1):
            values = re.split(r"\s+", raw.strip())
            if top_curve_index >= len(values):
                continue
            source_value = clean(values[top_curve_index])
            if not source_value or is_null(source_value, null_value):
                continue
            mapped_top = ""
            mapping_status = "candidate_zone_value_without_confirmed_native_index_mapping"
            try:
                index_value = int(float(source_value))
                if 0 <= index_value < len(top_order):
                    mapped_top = top_order[index_value]
                    mapping_status = "candidate_zone_value_mapped_to_native_top_order_unverified"
            except ValueError:
                pass
            rows.append(
                {
                    "evidence_class": "las_zone_log_candidate",
                    "native_binary_confirmed": "no",
                    "well_name": well_name,
                    "top_name": mapped_top or f"zone_log_value_{source_value}",
                    "canonical_top_name": canonical_top_name(mapped_top) if mapped_top else "",
                    "measured_depth": values[0] if values else "",
                    "depth_unit": curve_records[0].get("unit", "") if curve_records else "",
                    "source_value": source_value,
                    "source_file": win_rel(export_package, las_path),
                    "byte_offset": "",
                    "decode_status": mapping_status,
                    "evidence_summary": f"{top_curve.get('mnemonic', '') if top_curve else ''} LAS row {row_index}; mapping through native top order is unverified.",
                }
            )
    return rows


def parse_petrel_well_tops_ascii(path: Path | None) -> list[dict[str, Any]]:
    if path is None or not path.exists():
        return []

    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    fields: list[str] = []
    in_header = False
    rows: list[dict[str, Any]] = []
    for line_number, raw in enumerate(lines, start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#Petrel") or stripped.startswith("VERSION"):
            continue
        if stripped == "BEGIN HEADER":
            in_header = True
            continue
        if stripped == "END HEADER":
            in_header = False
            continue
        if in_header:
            parts = stripped.split(maxsplit=1)
            if len(parts) == 2:
                fields.append(parts[1])
            continue
        if not fields:
            continue
        try:
            values = shlex.split(stripped)
        except ValueError:
            continue
        if len(values) != len(fields):
            continue
        item = dict(zip(fields, values))
        top_name = clean(item.get("Horizon Name", ""))
        rows.append(
            {
                "record_class": "source_petrel_ascii_well_top",
                "is_actual_pick_record": "yes",
                "native_binary_confirmed": "no",
                "well_name": item.get("Well Name", ""),
                "top_name": top_name,
                "canonical_top_name": canonical_source_top_name(top_name),
                "measured_depth": item.get("Measured Depth", ""),
                "depth": item.get("Depth", ""),
                "time": item.get("Time", ""),
                "x": item.get("X", ""),
                "y": item.get("Y", ""),
                "depth_unit": "m_inferred_from_project_las_headers",
                "xy_unit": "m_inferred_from_project_context",
                "type": item.get("Type", ""),
                "symbol": item.get("Symbol", ""),
                "pick_name": item.get("Pick Name", ""),
                "interpreter": item.get("Interpreter", ""),
                "dip_angle": item.get("Dip Angle", ""),
                "dip_azimuth": item.get("Dip Azimuth", ""),
                "source_file": project_rel(path),
                "source_row": line_number,
                "decode_status": "parsed_from_petrel_ascii_source_file_binary_payload_not_decoded",
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-name", default=PROJECT_NAME_DEFAULT)
    parser.add_argument("--petrel-version", default=PETREL_VERSION_DEFAULT)
    parser.add_argument("--project-file", required=True)
    parser.add_argument("--export-package", required=True)
    parser.add_argument("--source-well-tops-file", default="")
    args = parser.parse_args()

    project_file = Path(args.project_file).resolve()
    export_package = Path(args.export_package).resolve()
    project_root = Path(__file__).resolve().parents[1]
    source_well_tops_file = (
        Path(args.source_well_tops_file).resolve()
        if args.source_well_tops_file
        else (project_root / SOURCE_WELL_TOPS_DEFAULT_REL).resolve()
    )
    top_occurrences, top_order = native_top_name_occurrences(project_file)
    history_rows = native_history_rows(project_file)
    las_candidates = las_zone_link_candidates(export_package, top_order)
    source_rows = parse_petrel_well_tops_ascii(source_well_tops_file)

    rows = top_occurrences + history_rows + las_candidates
    out_csv = export_package / "02_wells" / "well_tops" / "well_tops_native_binary_probe.csv"
    source_csv = export_package / "02_wells" / "well_tops" / "well_tops_from_source_ascii.csv"
    decode_attempt_csv = export_package / "02_wells" / "well_tops" / "well_tops_native_decode_attempt.csv"
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_report = export_package / "07_workflows_reports" / "zero_gui_well_exports" / f"well_tops_native_probe_{stamp}.json"
    fieldnames = [
        "evidence_class",
        "native_binary_confirmed",
        "well_name",
        "top_name",
        "canonical_top_name",
        "measured_depth",
        "depth_unit",
        "source_value",
        "source_file",
        "byte_offset",
        "decode_status",
        "evidence_summary",
    ]
    write_csv(out_csv, rows, fieldnames)
    source_fieldnames = [
        "record_class",
        "is_actual_pick_record",
        "native_binary_confirmed",
        "well_name",
        "top_name",
        "canonical_top_name",
        "measured_depth",
        "depth",
        "time",
        "x",
        "y",
        "depth_unit",
        "xy_unit",
        "type",
        "symbol",
        "pick_name",
        "interpreter",
        "dip_angle",
        "dip_azimuth",
        "source_file",
        "source_row",
        "decode_status",
    ]
    write_csv(source_csv, source_rows, source_fieldnames)
    write_csv(decode_attempt_csv, source_rows, source_fieldnames)
    report = {
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "project_name": args.project_name,
        "petrel_version": args.petrel_version,
        "project_file": str(project_file),
        "export_package": str(export_package),
        "source_well_tops_file": str(source_well_tops_file) if source_well_tops_file.exists() else "",
        "runtime_gui_used": False,
        "petrel_process_launched": False,
        "native_top_name_occurrences": len(top_occurrences),
        "native_top_order_candidate": top_order,
        "native_history_rows": len(history_rows),
        "las_zone_log_candidate_rows": len(las_candidates),
        "source_ascii_pick_rows": len(source_rows),
        "usable_source_ascii_pick_rows": len(source_rows),
        "actual_well_top_pick_rows_from_native_binary": 0,
        "actual_well_top_pick_rows": len(source_rows),
        "native_binary_marker_pick_rows": 0,
        "well_top_export_status": "source_ascii_recovered_native_binary_marker_payload_not_decoded",
        "outputs": {
            "native_binary_probe_csv": str(out_csv),
            "source_ascii_well_tops_csv": str(source_csv),
            "native_decode_attempt_csv": str(decode_attempt_csv),
            "report": str(out_report),
        },
        "boundary": (
            "The native binary pass found canonical top-name/history strings and LAS zone-log values linked to Well Tops, "
            "but did not decode the Petrel native marker-pick payload. The clean pick table is parsed from a local "
            "Petrel Well Tops ASCII source file and is labeled as source-derived, not native-binary-confirmed."
        ),
    }
    write_json(out_report, report)
    print(f"NativeWellTopProbe: {out_csv}")
    print(f"SourceAsciiWellTops: {source_csv}")
    print(f"NativeDecodeAttempt: {decode_attempt_csv}")
    print(f"Report: {out_report}")
    print("SummaryJson:")
    print(json.dumps(report, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
