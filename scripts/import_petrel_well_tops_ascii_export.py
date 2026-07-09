#!/usr/bin/env python3
"""Parse a Petrel-exported Well Tops ASCII file into package CSV artifacts."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import re
import shlex
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


PROJECT_NAME_DEFAULT = "Petrel2010 demo project"
PETREL_VERSION_DEFAULT = "2018.2.0.5333"

PETREL_ASCII_OUTPUT_FIELDS = [
    "record_class",
    "is_actual_pick_record",
    "petrel_export_confirmed",
    "native_binary_confirmed",
    "petrel_ascii_row_number",
    "well_name",
    "surface",
    "compare_surface_name",
    "x",
    "y",
    "depth",
    "measured_depth",
    "twt_picked",
    "twt_picked_abs",
    "twt_auto",
    "twt_auto_abs",
    "geological_age",
    "tvt",
    "tst",
    "interpreter",
    "observation_number",
    "dip_angle",
    "dip_azimuth",
    "missing",
    "confidence_factor",
    "used_by_dep_conv",
    "used_by_geo_mod",
    "symbol",
    "zone_log",
    "type",
    "source_file",
    "source_row",
    "decode_status",
]

GUI_COMPARE_FIELDS = [
    "comparison_status",
    "well_name",
    "surface",
    "compare_surface_name",
    "petrel_ascii_row_number",
    "gui_row_number",
    "petrel_md",
    "gui_md",
    "md_delta",
    "petrel_depth",
    "gui_depth",
    "depth_delta",
    "petrel_x",
    "gui_x",
    "x_delta",
    "petrel_y",
    "gui_y",
    "y_delta",
    "petrel_twt_picked_abs",
    "gui_twt_picked",
    "twt_picked_delta",
    "petrel_twt_auto_abs",
    "gui_twt_auto",
    "twt_auto_delta",
    "notes",
]

SOURCE_COMPARE_FIELDS = [
    "comparison_status",
    "well_name",
    "surface",
    "compare_surface_name",
    "petrel_ascii_row_number",
    "source_row",
    "petrel_md",
    "source_measured_depth",
    "md_delta",
    "petrel_depth",
    "source_depth",
    "depth_delta",
    "petrel_x",
    "source_x",
    "x_delta",
    "petrel_y",
    "source_y",
    "y_delta",
    "petrel_twt_picked",
    "petrel_twt_auto",
    "source_time",
    "source_time_abs",
    "twt_auto_abs_minus_source_time_abs",
    "twt_picked_abs_minus_source_time_abs",
    "notes",
]


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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def to_float(value: Any) -> float | None:
    text = clean(value)
    if not text or text == "-999":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def format_float(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.6f}".rstrip("0").rstrip(".")


def delta(left: Any, right: Any) -> str:
    left_value = to_float(left)
    right_value = to_float(right)
    if left_value is None or right_value is None:
        return ""
    return format_float(left_value - right_value)


def abs_text(value: Any) -> str:
    number = to_float(value)
    if number is None:
        return ""
    return format_float(abs(number))


def compare_surface_name(raw_name: str) -> str:
    name = clean(raw_name)
    lower = name.lower()
    aliases = {
        "base cretaceous": "BCU",
        "bcu": "BCU",
        "top tarbert": "T_Tarbert",
        "t_tarbert": "T_Tarbert",
        "t_tarbert [converted]": "T_Tarbert",
        "top ness": "T_Ness",
        "t_ness": "T_Ness",
        "top etive": "T_Etive",
        "t_etive": "T_Etive",
        "seabed": "Seabed",
    }
    if lower in aliases:
        return aliases[lower]
    return name


def load_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def parse_crs_sidecar(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        root = ET.fromstring(path.read_text(encoding="utf-8", errors="replace"))
    except ET.ParseError:
        return {"path": str(path), "parse_status": "failed"}

    early = root.find(".//IEarlyBoundCoordinateReferenceSystem")
    late = root.find(".//ILateBoundCoordinateReferenceSystem")
    early_authority = early.findtext("AuthorityCode", default="") if early is not None else ""
    late_authority = late.findtext("AuthorityCode", default="") if late is not None else ""
    return {
        "path": str(path),
        "parse_status": "parsed",
        "crs_name": early.attrib.get("name", "") if early is not None else "",
        "crs_type": early.attrib.get("crsType", "") if early is not None else "",
        "authority_code": early_authority,
        "late_bound_name": late.attrib.get("name", "") if late is not None else "",
        "late_bound_authority_code": late_authority,
    }


def parse_petrel_ascii(path: Path) -> tuple[list[dict[str, Any]], list[str], dict[str, Any]]:
    lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    headers: list[str] = []
    rows: list[dict[str, Any]] = []
    in_header = False
    header_done = False
    comments: list[str] = []
    version = ""

    for line_number, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            comments.append(line)
            continue
        if line.upper().startswith("VERSION "):
            version = line
            continue
        if line == "BEGIN HEADER":
            in_header = True
            continue
        if line == "END HEADER":
            in_header = False
            header_done = True
            continue
        if in_header:
            headers.append(line)
            continue
        if not header_done:
            continue

        values = shlex.split(raw, posix=True)
        if len(values) != len(headers):
            raise ValueError(f"Line {line_number} has {len(values)} values, expected {len(headers)} from header.")
        raw_row = dict(zip(headers, values))
        row = {
            "record_class": "petrel_exported_well_tops_ascii",
            "is_actual_pick_record": "yes",
            "petrel_export_confirmed": "yes",
            "native_binary_confirmed": "no",
            "petrel_ascii_row_number": str(len(rows) + 1),
            "well_name": raw_row.get("Well", ""),
            "surface": raw_row.get("Surface", ""),
            "compare_surface_name": compare_surface_name(raw_row.get("Surface", "")),
            "x": raw_row.get("X", ""),
            "y": raw_row.get("Y", ""),
            "depth": raw_row.get("Z", ""),
            "measured_depth": raw_row.get("MD", ""),
            "twt_picked": raw_row.get("TWT picked", ""),
            "twt_picked_abs": abs_text(raw_row.get("TWT picked", "")),
            "twt_auto": raw_row.get("TWT auto", ""),
            "twt_auto_abs": abs_text(raw_row.get("TWT auto", "")),
            "geological_age": raw_row.get("Geological age", ""),
            "tvt": raw_row.get("TVT", ""),
            "tst": raw_row.get("TST", ""),
            "interpreter": raw_row.get("Interpreter", ""),
            "observation_number": raw_row.get("Observation number", ""),
            "dip_angle": raw_row.get("Dip angle", ""),
            "dip_azimuth": raw_row.get("Dip azimuth", ""),
            "missing": raw_row.get("Missing", ""),
            "confidence_factor": raw_row.get("Confidence factor", ""),
            "used_by_dep_conv": raw_row.get("Used by dep.conv.", ""),
            "used_by_geo_mod": raw_row.get("Used by geo mod", ""),
            "symbol": raw_row.get("Symbol", ""),
            "zone_log": raw_row.get("Zone log", ""),
            "type": raw_row.get("Type", ""),
            "source_file": project_rel(path),
            "source_row": line_number,
            "decode_status": "parsed_from_petrel_exported_well_tops_ascii_file",
        }
        rows.append(row)

    if not headers:
        raise ValueError(f"No BEGIN HEADER/END HEADER block found in {path}")
    if not rows:
        raise ValueError(f"No data rows parsed from {path}")
    metadata = {"version": version, "comments": comments, "header_columns": headers}
    return rows, headers, metadata


def choose_best_match(left: dict[str, Any], candidates: list[dict[str, Any]], md_field: str) -> dict[str, Any] | None:
    if not candidates:
        return None
    left_md = to_float(left.get("measured_depth"))
    if left_md is None:
        return candidates[0]

    def score(row: dict[str, Any]) -> float:
        right_md = to_float(row.get(md_field))
        if right_md is None:
            return 1_000_000_000.0
        return abs(left_md - right_md)

    return sorted(candidates, key=score)[0]


def numeric_differences(petrel: dict[str, Any], other: dict[str, Any], pairs: list[tuple[str, str, str]], tolerance: float) -> list[str]:
    differences: list[str] = []
    for name, left_field, right_field in pairs:
        left_value = to_float(petrel.get(left_field))
        right_value = to_float(other.get(right_field))
        if left_value is None or right_value is None:
            continue
        if abs(left_value - right_value) > tolerance:
            differences.append(name)
    return differences


def compare_to_gui(
    petrel_rows: list[dict[str, Any]],
    gui_rows: list[dict[str, Any]],
    tolerance: float,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    gui_by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for gui in gui_rows:
        key = (clean(gui.get("well_name", "")), clean(gui.get("compare_surface_name", "")))
        gui_by_key.setdefault(key, []).append(gui)

    used_gui_ids: set[int] = set()
    compare_rows: list[dict[str, Any]] = []
    status_counts: dict[str, int] = {}

    for petrel in petrel_rows:
        key = (clean(petrel.get("well_name", "")), clean(petrel.get("compare_surface_name", "")))
        gui = choose_best_match(petrel, gui_by_key.get(key, []), "measured_depth")
        if gui is None:
            status = "missing_in_gui_table"
            notes = "Petrel-exported ASCII row is not present in the existing GUI paste table."
            row = gui_compare_row(status, petrel, {}, notes)
        else:
            used_gui_ids.add(id(gui))
            differences = numeric_differences(
                petrel,
                gui,
                [
                    ("md", "measured_depth", "measured_depth"),
                    ("depth", "depth", "depth"),
                    ("x", "x", "x"),
                    ("y", "y", "y"),
                    ("twt_picked", "twt_picked_abs", "twt_picked"),
                    ("twt_auto", "twt_auto_abs", "twt_auto"),
                ],
                tolerance,
            )
            if differences:
                status = "matched_with_numeric_differences"
                notes = "Matched by well/surface, but numeric values differ beyond tolerance: " + "; ".join(differences)
            else:
                status = "matched"
                notes = "Matched by well/surface and numeric values are within tolerance. TWT uses absolute value because the ASCII export stores signed time."
            row = gui_compare_row(status, petrel, gui, notes)
        status_counts[status] = status_counts.get(status, 0) + 1
        compare_rows.append(row)

    for gui in gui_rows:
        if id(gui) in used_gui_ids:
            continue
        status = "missing_in_petrel_ascii_export"
        status_counts[status] = status_counts.get(status, 0) + 1
        notes = "Existing GUI paste row is not present in the Petrel-exported ASCII file."
        compare_rows.append(gui_compare_row(status, {}, gui, notes))

    return compare_rows, {
        "petrel_ascii_row_count": len(petrel_rows),
        "gui_row_count": len(gui_rows),
        "comparison_row_count": len(compare_rows),
        "status_counts": dict(sorted(status_counts.items())),
        "numeric_tolerance": tolerance,
    }


def gui_compare_row(status: str, petrel: dict[str, Any], gui: dict[str, Any], notes: str) -> dict[str, Any]:
    return {
        "comparison_status": status,
        "well_name": petrel.get("well_name") or gui.get("well_name", ""),
        "surface": petrel.get("surface") or gui.get("surface", ""),
        "compare_surface_name": petrel.get("compare_surface_name") or gui.get("compare_surface_name", ""),
        "petrel_ascii_row_number": petrel.get("petrel_ascii_row_number", ""),
        "gui_row_number": gui.get("gui_row_number", ""),
        "petrel_md": petrel.get("measured_depth", ""),
        "gui_md": gui.get("measured_depth", ""),
        "md_delta": delta(petrel.get("measured_depth", ""), gui.get("measured_depth", "")),
        "petrel_depth": petrel.get("depth", ""),
        "gui_depth": gui.get("depth", ""),
        "depth_delta": delta(petrel.get("depth", ""), gui.get("depth", "")),
        "petrel_x": petrel.get("x", ""),
        "gui_x": gui.get("x", ""),
        "x_delta": delta(petrel.get("x", ""), gui.get("x", "")),
        "petrel_y": petrel.get("y", ""),
        "gui_y": gui.get("y", ""),
        "y_delta": delta(petrel.get("y", ""), gui.get("y", "")),
        "petrel_twt_picked_abs": petrel.get("twt_picked_abs", ""),
        "gui_twt_picked": gui.get("twt_picked", ""),
        "twt_picked_delta": delta(petrel.get("twt_picked_abs", ""), gui.get("twt_picked", "")),
        "petrel_twt_auto_abs": petrel.get("twt_auto_abs", ""),
        "gui_twt_auto": gui.get("twt_auto", ""),
        "twt_auto_delta": delta(petrel.get("twt_auto_abs", ""), gui.get("twt_auto", "")),
        "notes": notes,
    }


def compare_to_source(
    petrel_rows: list[dict[str, Any]],
    source_rows: list[dict[str, Any]],
    tolerance: float,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    source_by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for source in source_rows:
        key = (clean(source.get("well_name", "")), compare_surface_name(source.get("top_name", "")))
        source_by_key.setdefault(key, []).append(source)

    used_source_ids: set[int] = set()
    compare_rows: list[dict[str, Any]] = []
    status_counts: dict[str, int] = {}

    for petrel in petrel_rows:
        key = (clean(petrel.get("well_name", "")), clean(petrel.get("compare_surface_name", "")))
        source = choose_best_match(petrel, source_by_key.get(key, []), "measured_depth")
        if source is None:
            status = "missing_in_source_ascii"
            notes = "Petrel-exported ASCII row is not present in the source-ASCII fallback."
            row = source_compare_row(status, petrel, {}, notes)
        else:
            used_source_ids.add(id(source))
            differences = numeric_differences(
                petrel,
                source,
                [
                    ("md", "measured_depth", "measured_depth"),
                    ("depth", "depth", "depth"),
                    ("x", "x", "x"),
                    ("y", "y", "y"),
                ],
                tolerance,
            )
            if differences:
                status = "matched_with_numeric_differences"
                notes = "Matched by well/surface, but numeric values differ beyond tolerance: " + "; ".join(differences)
            else:
                status = "matched"
                notes = "Matched by well/surface and available numeric values are within tolerance."
            row = source_compare_row(status, petrel, source, notes)
        status_counts[status] = status_counts.get(status, 0) + 1
        compare_rows.append(row)

    for source in source_rows:
        if id(source) in used_source_ids:
            continue
        status = "missing_in_petrel_ascii_export"
        status_counts[status] = status_counts.get(status, 0) + 1
        notes = "Source-ASCII fallback row is not present in the Petrel-exported ASCII file."
        compare_rows.append(source_compare_row(status, {}, source, notes))

    return compare_rows, {
        "petrel_ascii_row_count": len(petrel_rows),
        "source_ascii_row_count": len(source_rows),
        "comparison_row_count": len(compare_rows),
        "status_counts": dict(sorted(status_counts.items())),
        "numeric_tolerance": tolerance,
    }


def source_compare_row(status: str, petrel: dict[str, Any], source: dict[str, Any], notes: str) -> dict[str, Any]:
    source_time_abs = abs_text(source.get("time", ""))
    return {
        "comparison_status": status,
        "well_name": petrel.get("well_name") or source.get("well_name", ""),
        "surface": petrel.get("surface") or source.get("top_name", ""),
        "compare_surface_name": petrel.get("compare_surface_name") or compare_surface_name(source.get("top_name", "")),
        "petrel_ascii_row_number": petrel.get("petrel_ascii_row_number", ""),
        "source_row": source.get("source_row", ""),
        "petrel_md": petrel.get("measured_depth", ""),
        "source_measured_depth": source.get("measured_depth", ""),
        "md_delta": delta(petrel.get("measured_depth", ""), source.get("measured_depth", "")),
        "petrel_depth": petrel.get("depth", ""),
        "source_depth": source.get("depth", ""),
        "depth_delta": delta(petrel.get("depth", ""), source.get("depth", "")),
        "petrel_x": petrel.get("x", ""),
        "source_x": source.get("x", ""),
        "x_delta": delta(petrel.get("x", ""), source.get("x", "")),
        "petrel_y": petrel.get("y", ""),
        "source_y": source.get("y", ""),
        "y_delta": delta(petrel.get("y", ""), source.get("y", "")),
        "petrel_twt_picked": petrel.get("twt_picked", ""),
        "petrel_twt_auto": petrel.get("twt_auto", ""),
        "source_time": source.get("time", ""),
        "source_time_abs": source_time_abs,
        "twt_auto_abs_minus_source_time_abs": delta(petrel.get("twt_auto_abs", ""), source_time_abs),
        "twt_picked_abs_minus_source_time_abs": delta(petrel.get("twt_picked_abs", ""), source_time_abs),
        "notes": notes,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-name", default=PROJECT_NAME_DEFAULT)
    parser.add_argument("--petrel-version", default=PETREL_VERSION_DEFAULT)
    parser.add_argument("--export-package", required=True)
    parser.add_argument("--ascii-export", required=True)
    parser.add_argument("--crs-sidecar", default="")
    parser.add_argument("--gui-paste-csv", default="")
    parser.add_argument("--source-ascii-csv", default="")
    parser.add_argument("--numeric-tolerance", type=float, default=0.05)
    parser.add_argument(
        "--creation-method",
        choices=["manual_gui", "deterministic_gui", "unknown"],
        default="manual_gui",
        help="How the Petrel ASCII export file was created before this importer parsed it.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    export_package = Path(args.export_package).resolve()
    ascii_export = Path(args.ascii_export).resolve()
    if not ascii_export.is_file():
        raise FileNotFoundError(f"Petrel Well Tops ASCII export not found: {ascii_export}")

    crs_sidecar = Path(args.crs_sidecar).resolve() if args.crs_sidecar else Path(str(ascii_export) + ".crsmeta.xml")
    gui_paste_csv = (
        Path(args.gui_paste_csv).resolve()
        if args.gui_paste_csv
        else export_package / "02_wells" / "well_tops" / "well_tops_from_petrel_gui_paste.csv"
    )
    source_ascii_csv = (
        Path(args.source_ascii_csv).resolve()
        if args.source_ascii_csv
        else export_package / "02_wells" / "well_tops" / "well_tops_from_source_ascii.csv"
    )

    petrel_rows, header_columns, ascii_metadata = parse_petrel_ascii(ascii_export)
    gui_rows = load_csv(gui_paste_csv)
    source_rows = load_csv(source_ascii_csv)
    gui_compare_rows, gui_summary = compare_to_gui(petrel_rows, gui_rows, args.numeric_tolerance)
    source_compare_rows, source_summary = compare_to_source(petrel_rows, source_rows, args.numeric_tolerance)

    well_top_dir = export_package / "02_wells" / "well_tops"
    report_dir = export_package / "07_workflows_reports" / "zero_gui_well_exports"
    parsed_csv = well_top_dir / "well_tops_from_petrel_ascii_export.csv"
    gui_compare_csv = well_top_dir / "well_tops_petrel_ascii_export_vs_gui_compare.csv"
    source_compare_csv = well_top_dir / "well_tops_petrel_ascii_export_vs_source_ascii_compare.csv"
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d_%H%M%S")
    report_path = report_dir / f"well_tops_petrel_ascii_export_{stamp}.json"

    write_csv(parsed_csv, petrel_rows, PETREL_ASCII_OUTPUT_FIELDS)
    write_csv(gui_compare_csv, gui_compare_rows, GUI_COMPARE_FIELDS)
    write_csv(source_compare_csv, source_compare_rows, SOURCE_COMPARE_FIELDS)

    deterministic_gui_used = args.creation_method == "deterministic_gui"
    manual_gui_used = args.creation_method == "manual_gui"
    if deterministic_gui_used:
        boundary = (
            "This is a Petrel-authored Well Tops ASCII export created through the deterministic GUI workflow runner. "
            "It confirms actual marker-pick rows and depths in a universal text format, but it is not "
            "a zero-GUI native binary decode and not yet a zero-GUI workflow command insertion."
        )
    else:
        boundary = (
            "This is a Petrel-authored Well Tops ASCII export created manually through the Petrel UI. "
            "It confirms actual marker-pick rows and depths in a universal text format, but it is not "
            "a zero-GUI native binary decode and not yet a zero-GUI workflow command insertion."
        )

    report = {
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "project_name": args.project_name,
        "petrel_version": args.petrel_version,
        "export_package": str(export_package),
        "ascii_export": str(ascii_export),
        "ascii_export_sha256": sha256_file(ascii_export),
        "ascii_export_length_bytes": ascii_export.stat().st_size,
        "crs_sidecar": parse_crs_sidecar(crs_sidecar),
        "gui_paste_csv": str(gui_paste_csv) if gui_paste_csv.exists() else "",
        "source_ascii_csv": str(source_ascii_csv) if source_ascii_csv.exists() else "",
        "runtime_gui_used": False,
        "petrel_process_launched": False,
        "petrel_export_creation_method": args.creation_method,
        "manual_petrel_export_used": manual_gui_used,
        "deterministic_gui_workflow_used": deterministic_gui_used,
        "petrel_export_confirmed": True,
        "row_count": len(petrel_rows),
        "header_column_count": len(header_columns),
        "ascii_metadata": ascii_metadata,
        "outputs": {
            "parsed_csv": str(parsed_csv),
            "gui_compare_csv": str(gui_compare_csv),
            "source_compare_csv": str(source_compare_csv),
            "report": str(report_path),
        },
        "gui_comparison": gui_summary,
        "source_ascii_comparison": source_summary,
        "boundary": boundary,
    }
    write_json(report_path, report)

    print(f"PetrelAsciiWellTops: {parsed_csv}")
    print(f"PetrelAsciiVsGuiCompare: {gui_compare_csv}")
    print(f"PetrelAsciiVsSourceCompare: {source_compare_csv}")
    print(f"Report: {report_path}")
    print("SummaryJson:")
    print(json.dumps(report, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
