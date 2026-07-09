#!/usr/bin/env python3
"""Import a pasted Petrel GUI Well Tops table and compare it to source rows.

This is a validation helper, not a native binary decoder. It captures the
visible Petrel table as operator-provided ground truth and highlights where the
current zero-GUI/source fallback does not match it.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
from pathlib import Path
from typing import Any


PROJECT_NAME_DEFAULT = "Petrel2010 demo project"
PETREL_VERSION_DEFAULT = "2018.2.0.5333"


PETREL_GUI_COLUMNS = [
    "Well identifier",
    "Surface",
    "X",
    "Y",
    "Depth",
    "MD",
    "TWT Picked",
    "TWT Auto",
    "Geological age",
    "TVT",
    "TST",
    "Interpreter",
    "Observation number",
    "Dip Angle",
    "Dip Azimuth",
    "Missing",
    "Confidence factor",
    "Used by Dep.Conv.",
    "Used by Geo Mod",
    "Symbol",
    "Studio sync status",
    "Last edited",
]


GUI_FIELD_MAP = {
    "Well identifier": "well_name",
    "Surface": "surface",
    "X": "x",
    "Y": "y",
    "Depth": "depth",
    "MD": "measured_depth",
    "TWT Picked": "twt_picked",
    "TWT Auto": "twt_auto",
    "Geological age": "geological_age",
    "TVT": "tvt",
    "TST": "tst",
    "Interpreter": "interpreter",
    "Observation number": "observation_number",
    "Dip Angle": "dip_angle",
    "Dip Azimuth": "dip_azimuth",
    "Missing": "missing",
    "Confidence factor": "confidence_factor",
    "Used by Dep.Conv.": "used_by_dep_conv",
    "Used by Geo Mod": "used_by_geo_mod",
    "Symbol": "symbol",
    "Studio sync status": "studio_sync_status",
    "Last edited": "last_edited",
}


GUI_OUTPUT_FIELDS = [
    "record_class",
    "is_actual_pick_record",
    "native_binary_confirmed",
    "gui_row_number",
    "well_name",
    "surface",
    "compare_surface_name",
    "x",
    "y",
    "depth",
    "measured_depth",
    "twt_picked",
    "twt_auto",
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
    "studio_sync_status",
    "last_edited",
    "source_file",
    "source_row",
    "decode_status",
]


COMPARE_FIELDS = [
    "comparison_status",
    "well_name",
    "surface",
    "compare_surface_name",
    "gui_row_number",
    "source_row",
    "gui_md",
    "source_measured_depth",
    "md_delta",
    "gui_depth",
    "source_depth",
    "depth_delta",
    "gui_x",
    "source_x",
    "x_delta",
    "gui_y",
    "source_y",
    "y_delta",
    "gui_twt_picked",
    "gui_twt_auto",
    "source_time",
    "source_time_abs",
    "twt_auto_minus_source_time_abs",
    "twt_picked_minus_source_time_abs",
    "gui_last_edited",
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
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def delta(left: Any, right: Any) -> str:
    left_value = to_float(left)
    right_value = to_float(right)
    if left_value is None or right_value is None:
        return ""
    return f"{left_value - right_value:.6f}".rstrip("0").rstrip(".")


def abs_text(value: Any) -> str:
    number = to_float(value)
    if number is None:
        return ""
    return f"{abs(number):.6f}".rstrip("0").rstrip(".")


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


def parse_gui_paste(path: Path) -> list[dict[str, Any]]:
    lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    header: list[str] | None = None
    header_line_number = 0
    rows: list[dict[str, Any]] = []

    for line_number, raw in enumerate(lines, start=1):
        if not raw.strip():
            continue
        cells = raw.rstrip("\r\n").split("\t")
        if header is None:
            candidate = cells[1:] if cells and cells[0] == "" else cells
            if "Well identifier" in candidate and "Surface" in candidate:
                header = [clean(item) for item in candidate]
                header_line_number = line_number
            continue

        if len(cells) < 2:
            continue
        row_number = clean(cells[0])
        values = cells[1:]
        if not row_number or not row_number.lstrip("-").isdigit():
            continue
        padded_values = values + [""] * max(0, len(header) - len(values))
        raw_row = dict(zip(header, padded_values[: len(header)]))
        row: dict[str, Any] = {
            "record_class": "petrel_gui_well_top_table_paste",
            "is_actual_pick_record": "yes",
            "native_binary_confirmed": "no",
            "gui_row_number": row_number,
            "source_file": project_rel(path),
            "source_row": line_number,
            "decode_status": "parsed_from_petrel_gui_table_paste_manual_validation_artifact",
        }
        for gui_name, field_name in GUI_FIELD_MAP.items():
            row[field_name] = raw_row.get(gui_name, "")
        row["compare_surface_name"] = compare_surface_name(str(row.get("surface", "")))
        rows.append(row)

    if header is None:
        raise ValueError(f"No Petrel GUI well tops header found in {path}")

    missing = [column for column in PETREL_GUI_COLUMNS if column not in header]
    if missing:
        raise ValueError(
            f"Petrel GUI well tops header is missing expected columns after line {header_line_number}: "
            + ", ".join(missing)
        )
    return rows


def load_source_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def choose_best_source_match(gui_row: dict[str, Any], source_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not source_rows:
        return None
    gui_md = to_float(gui_row.get("measured_depth"))
    if gui_md is None:
        return source_rows[0]

    def score(row: dict[str, Any]) -> float:
        source_md = to_float(row.get("measured_depth"))
        if source_md is None:
            return 1_000_000_000.0
        return abs(gui_md - source_md)

    return sorted(source_rows, key=score)[0]


def compare_gui_to_source(
    gui_rows: list[dict[str, Any]],
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

    for gui in gui_rows:
        key = (clean(gui.get("well_name", "")), clean(gui.get("compare_surface_name", "")))
        source_candidates = source_by_key.get(key, [])
        source = choose_best_source_match(gui, source_candidates)
        if source is None:
            status = "missing_in_source_ascii"
            notes = "Visible in Petrel GUI paste but not present in the current source-ASCII fallback."
            row = comparison_row(status, gui, {}, notes)
        else:
            used_source_ids.add(id(source))
            numeric_issue_names = numeric_differences(gui, source, tolerance)
            if numeric_issue_names:
                status = "matched_with_numeric_differences"
                notes = "Matched by well/surface, but numeric values differ beyond tolerance: " + "; ".join(numeric_issue_names)
            else:
                status = "matched"
                notes = "Matched by well/surface and available numeric values are within tolerance."
            row = comparison_row(status, gui, source, notes)
        status_counts[status] = status_counts.get(status, 0) + 1
        compare_rows.append(row)

    for source in source_rows:
        if id(source) in used_source_ids:
            continue
        status = "missing_in_gui_paste"
        status_counts[status] = status_counts.get(status, 0) + 1
        notes = "Present in the current source-ASCII fallback but not visible in the pasted Petrel GUI table."
        compare_rows.append(comparison_row(status, {}, source, notes))

    summary = {
        "gui_row_count": len(gui_rows),
        "source_ascii_row_count": len(source_rows),
        "comparison_row_count": len(compare_rows),
        "status_counts": dict(sorted(status_counts.items())),
        "gui_wells": sorted({clean(row.get("well_name", "")) for row in gui_rows if clean(row.get("well_name", ""))}),
        "source_ascii_wells": sorted(
            {clean(row.get("well_name", "")) for row in source_rows if clean(row.get("well_name", ""))}
        ),
        "gui_surfaces": sorted({clean(row.get("surface", "")) for row in gui_rows if clean(row.get("surface", ""))}),
        "source_ascii_compare_surfaces": sorted(
            {compare_surface_name(row.get("top_name", "")) for row in source_rows if clean(row.get("top_name", ""))}
        ),
        "numeric_tolerance": tolerance,
    }
    return compare_rows, summary


def numeric_differences(gui: dict[str, Any], source: dict[str, Any], tolerance: float) -> list[str]:
    checks = [
        ("md", gui.get("measured_depth"), source.get("measured_depth")),
        ("depth", gui.get("depth"), source.get("depth")),
        ("x", gui.get("x"), source.get("x")),
        ("y", gui.get("y"), source.get("y")),
    ]
    differences: list[str] = []
    for name, left, right in checks:
        left_value = to_float(left)
        right_value = to_float(right)
        if left_value is None or right_value is None:
            continue
        if abs(left_value - right_value) > tolerance:
            differences.append(name)
    return differences


def comparison_row(status: str, gui: dict[str, Any], source: dict[str, Any], notes: str) -> dict[str, Any]:
    source_time_abs = abs_text(source.get("time", ""))
    return {
        "comparison_status": status,
        "well_name": gui.get("well_name") or source.get("well_name", ""),
        "surface": gui.get("surface") or source.get("top_name", ""),
        "compare_surface_name": gui.get("compare_surface_name") or compare_surface_name(source.get("top_name", "")),
        "gui_row_number": gui.get("gui_row_number", ""),
        "source_row": source.get("source_row", ""),
        "gui_md": gui.get("measured_depth", ""),
        "source_measured_depth": source.get("measured_depth", ""),
        "md_delta": delta(gui.get("measured_depth", ""), source.get("measured_depth", "")),
        "gui_depth": gui.get("depth", ""),
        "source_depth": source.get("depth", ""),
        "depth_delta": delta(gui.get("depth", ""), source.get("depth", "")),
        "gui_x": gui.get("x", ""),
        "source_x": source.get("x", ""),
        "x_delta": delta(gui.get("x", ""), source.get("x", "")),
        "gui_y": gui.get("y", ""),
        "source_y": source.get("y", ""),
        "y_delta": delta(gui.get("y", ""), source.get("y", "")),
        "gui_twt_picked": gui.get("twt_picked", ""),
        "gui_twt_auto": gui.get("twt_auto", ""),
        "source_time": source.get("time", ""),
        "source_time_abs": source_time_abs,
        "twt_auto_minus_source_time_abs": delta(gui.get("twt_auto", ""), source_time_abs),
        "twt_picked_minus_source_time_abs": delta(gui.get("twt_picked", ""), source_time_abs),
        "gui_last_edited": gui.get("last_edited", ""),
        "notes": notes,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-name", default=PROJECT_NAME_DEFAULT)
    parser.add_argument("--petrel-version", default=PETREL_VERSION_DEFAULT)
    parser.add_argument("--gui-table-paste", required=True)
    parser.add_argument("--export-package", required=True)
    parser.add_argument("--source-ascii-csv", default="")
    parser.add_argument("--numeric-tolerance", type=float, default=0.05)
    args = parser.parse_args()

    gui_table_paste = Path(args.gui_table_paste).resolve()
    export_package = Path(args.export_package).resolve()
    source_ascii_csv = (
        Path(args.source_ascii_csv).resolve()
        if args.source_ascii_csv
        else export_package / "02_wells" / "well_tops" / "well_tops_from_source_ascii.csv"
    )

    gui_rows = parse_gui_paste(gui_table_paste)
    source_rows = load_source_rows(source_ascii_csv)
    compare_rows, compare_summary = compare_gui_to_source(gui_rows, source_rows, args.numeric_tolerance)

    well_top_dir = export_package / "02_wells" / "well_tops"
    report_dir = export_package / "07_workflows_reports" / "zero_gui_well_exports"
    gui_csv = well_top_dir / "well_tops_from_petrel_gui_paste.csv"
    compare_csv = well_top_dir / "well_tops_gui_vs_source_ascii_compare.csv"
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d_%H%M%S")
    report_path = report_dir / f"well_tops_gui_paste_compare_{stamp}.json"

    write_csv(gui_csv, gui_rows, GUI_OUTPUT_FIELDS)
    write_csv(compare_csv, compare_rows, COMPARE_FIELDS)

    report = {
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "project_name": args.project_name,
        "petrel_version": args.petrel_version,
        "gui_table_paste": str(gui_table_paste),
        "export_package": str(export_package),
        "source_ascii_csv": str(source_ascii_csv) if source_ascii_csv.exists() else "",
        "runtime_gui_used": False,
        "petrel_process_launched": False,
        "manual_gui_table_capture_used": True,
        "outputs": {
            "gui_paste_csv": str(gui_csv),
            "gui_vs_source_compare_csv": str(compare_csv),
            "report": str(report_path),
        },
        "summary": compare_summary,
        "boundary": (
            "The GUI-paste table is a manual Petrel GUI ground-truth artifact. "
            "It validates and guides the zero-GUI/native decode work, but it is not itself "
            "a native binary marker-pick decode."
        ),
    }
    write_json(report_path, report)

    print(f"GuiPasteWellTops: {gui_csv}")
    print(f"GuiVsSourceCompare: {compare_csv}")
    print(f"Report: {report_path}")
    print("SummaryJson:")
    print(json.dumps(report, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
