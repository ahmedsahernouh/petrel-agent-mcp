#!/usr/bin/env python3
"""Build zero-GUI well tables from the current Petrel export package.

This script does not launch Petrel, does not use Ocean, and does not mutate
native .pet/.ptd files. It derives well headers and LAS curve inventory from
already exported LAS files, then emits a conservative well-top reference
inventory from decodable LAS top-link curves and native XML marker references.
It does not decode Petrel's native marker pick records.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import html
import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote


PROJECT_NAME_DEFAULT = "Petrel2010 demo project"
PETREL_VERSION_DEFAULT = "2018.2.0.5333"


def clean(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def win_rel(base: Path, path: Path) -> str:
    return os.path.relpath(path, base).replace("/", "\\")


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    ensure_parent(path)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: clean(row.get(field, "")) for field in fieldnames})


def write_json(path: Path, payload: Any) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def split_las_sections(lines: list[str]) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current = ""
    for raw in lines:
        stripped = raw.strip()
        if stripped.startswith("~"):
            match = re.match(r"^~\s*([A-Za-z]+)", stripped)
            current = (match.group(1).lower() if match else "other")
            sections.setdefault(current, [])
            continue
        if current:
            sections.setdefault(current, []).append(raw.rstrip("\n\r"))
    return sections


def parse_las_record(line: str) -> dict[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "." not in stripped:
        return None
    before_colon, _, description = stripped.partition(":")
    match = re.match(r"^\s*([^.\s]+)\s*\.([^\s]*)\s*(.*?)\s*$", before_colon)
    if not match:
        return None
    mnemonic = clean(match.group(1))
    unit = clean(match.group(2))
    value = clean(match.group(3))
    if not mnemonic:
        return None
    return {
        "mnemonic": mnemonic,
        "unit": unit,
        "value": value,
        "description": clean(description),
    }


def parse_las(path: Path, export_package: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    sections = split_las_sections(lines)
    well_records = [item for line in sections.get("well", []) if (item := parse_las_record(line))]
    curve_records = [item for line in sections.get("curve", []) if (item := parse_las_record(line))]
    ascii_rows = [
        line.strip()
        for line in sections.get("ascii", [])
        if line.strip() and not line.strip().startswith("#")
    ]
    well_by_mnemonic = {record["mnemonic"].upper(): record for record in well_records}
    null_value = well_by_mnemonic.get("NULL", {}).get("value", "-999.25")
    top_curve_index = None
    top_curve_record: dict[str, str] | None = None
    for index, curve in enumerate(curve_records):
        name = f"{curve.get('mnemonic', '')} {curve.get('description', '')}".lower()
        if "welltops" in name or "well tops" in name or "well_top" in name or "marker" in name:
            top_curve_index = index
            top_curve_record = curve
            break

    top_values: list[str] = []
    top_link_rows: list[dict[str, str]] = []
    depth_unit = curve_records[0]["unit"] if curve_records else well_by_mnemonic.get("STRT", {}).get("unit", "")
    for row_index, ascii_row in enumerate(ascii_rows, start=1):
        values = re.split(r"\s+", ascii_row.strip())
        if top_curve_index is None or top_curve_index >= len(values):
            continue
        value = clean(values[top_curve_index])
        if not value or is_null_value(value, null_value):
            continue
        depth = values[0] if values else ""
        top_values.append(value)
        top_link_rows.append(
            {
                "record_class": "las_zone_log_reference",
                "is_actual_pick_record": "no",
                "well_name": well_by_mnemonic.get("WELL", {}).get("value", path.stem),
                "top_name": f"zone_log_value_{value}",
                "measured_depth": depth,
                "depth_unit": depth_unit,
                "source_file": win_rel(export_package, path),
                "source_field": top_curve_record["mnemonic"] if top_curve_record else "",
                "source_value": value,
                "source_row": str(row_index),
                "decode_status": "las_zone_log_value_without_marker_name_mapping",
            }
        )

    return {
        "path": path,
        "relative_path": win_rel(export_package, path),
        "well_records": well_records,
        "well_by_mnemonic": well_by_mnemonic,
        "curve_records": curve_records,
        "ascii_row_count": len(ascii_rows),
        "top_curve_record": top_curve_record,
        "top_values": sorted(set(top_values)),
        "top_link_rows": top_link_rows,
    }


def is_null_value(value: str, null_value: str) -> bool:
    try:
        return abs(float(value) - float(null_value)) < 1e-9
    except ValueError:
        return value.strip() == null_value.strip()


def build_header_rows(project_name: str, parsed_las: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for las in parsed_las:
        header = las["well_by_mnemonic"]
        top_curve = las.get("top_curve_record") or {}
        rows.append(
            {
                "project_name": project_name,
                "well_name": header.get("WELL", {}).get("value", las["path"].stem),
                "source_las_file": las["relative_path"],
                "source_las_directory": str(Path(las["relative_path"]).parent),
                "curve_count": len(las["curve_records"]),
                "data_row_count": las["ascii_row_count"],
                "top_link_curve_present": "yes" if top_curve else "no",
                "top_link_curve_name": top_curve.get("mnemonic", ""),
                "top_link_non_null_count": len(las["top_link_rows"]),
                "top_link_unique_values": ";".join(las["top_values"]),
                "start_depth": header.get("STRT", {}).get("value", ""),
                "stop_depth": header.get("STOP", {}).get("value", ""),
                "step": header.get("STEP", {}).get("value", ""),
                "depth_unit": header.get("STRT", {}).get("unit", ""),
                "null_value": header.get("NULL", {}).get("value", ""),
                "uwi": header.get("UWI", {}).get("value", ""),
                "api": header.get("API", {}).get("value", ""),
                "company": header.get("COMP", {}).get("value", ""),
                "field": header.get("FLD", {}).get("value", ""),
                "location": header.get("LOC", {}).get("value", ""),
                "service_company": header.get("SRVC", {}).get("value", ""),
                "province": header.get("PROV", {}).get("value", ""),
                "las_export_date": header.get("DATE", {}).get("value", ""),
                "source_status": "derived_from_validated_las_export",
            }
        )
    return rows


def build_curve_rows(project_name: str, parsed_las: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for las in parsed_las:
        header = las["well_by_mnemonic"]
        well_name = header.get("WELL", {}).get("value", las["path"].stem)
        top_curve = las.get("top_curve_record") or {}
        top_curve_name = top_curve.get("mnemonic", "")
        for index, curve in enumerate(las["curve_records"], start=1):
            mnemonic = curve.get("mnemonic", "")
            rows.append(
                {
                    "project_name": project_name,
                    "well_name": well_name,
                    "source_las_file": las["relative_path"],
                    "curve_index": index,
                    "mnemonic": mnemonic,
                    "unit": curve.get("unit", ""),
                    "description": curve.get("description", ""),
                    "is_depth_curve": "yes" if index == 1 or mnemonic.upper() in {"DEPT", "DEPTH"} else "no",
                    "is_well_top_link_curve": "yes" if mnemonic == top_curve_name else "no",
                }
            )
    return rows


def xml_reference_rows(export_package: Path, max_rows: int) -> list[dict[str, str]]:
    native_root = export_package / "08_native_project" / "ptd_store" / "Ocean"
    if not native_root.exists():
        return []

    patterns = [
        "FlattenFromWellTop",
        "ReferenceWellTops",
        "MarkerCollection.Name=Well%20Tops",
        "WellTopsTemplateDefinitionStyle",
        "WellTopStyle",
        "Zone%20log%20linked%20to%20%27Well%20Tops%27",
        "Zone log linked to 'Well Tops'",
    ]
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for xml_path in sorted(native_root.rglob("*.xml")):
        if len(rows) >= max_rows:
            break
        text = xml_path.read_text(encoding="utf-8", errors="replace")
        if not re.search(r"WellTop|Well Tops|WellTops|MarkerCollection|Marker", text, re.I):
            continue
        rel = win_rel(export_package, xml_path)

        for tag in ("FlattenFromWellTop", "ReferenceWellTops", "PrimaryDomainObject", "DomainObject", "SecondaryDomainObject", "Name"):
            for match in re.finditer(rf"<{tag}>(.*?)</{tag}>", text, flags=re.I | re.S):
                raw_value = clean(match.group(1))
                decoded = unquote(html.unescape(raw_value))
                if not decoded:
                    continue
                if not any(pattern.lower() in decoded.lower() for pattern in patterns) and not re.search(
                    r"WellTop|Well Tops|WellTops|MarkerCollection|Marker", decoded, re.I
                ):
                    continue
                key = (rel, tag, decoded)
                if key in seen:
                    continue
                seen.add(key)
                rows.append(
                    {
                        "record_class": "native_xml_reference",
                        "is_actual_pick_record": "no",
                        "well_name": "",
                        "top_name": marker_name_from_value(decoded),
                        "measured_depth": "",
                        "depth_unit": "",
                        "source_file": rel,
                        "source_field": tag,
                        "source_value": decoded,
                        "source_row": "",
                        "decode_status": "native_xml_reference_only_no_pick_depth_decoded",
                    }
                )
                if len(rows) >= max_rows:
                    break
            if len(rows) >= max_rows:
                break
    return rows


def marker_name_from_value(value: str) -> str:
    for pattern in (r"MarkerCollection\.Name=([^&;]+)", r"DictionaryWellLogVersion\.Name=([^&;]+)"):
        match = re.search(pattern, value)
        if match:
            return clean(match.group(1).replace("%20", " "))
    if "Well Tops" in value or "WellTops" in value:
        return "Well Tops"
    if "Marker" in value:
        return "Marker"
    return ""


def build_top_rows(export_package: Path, parsed_las: list[dict[str, Any]], max_native_xml_rows: int) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for las in parsed_las:
        rows.extend(las["top_link_rows"])
    rows.extend(xml_reference_rows(export_package, max_native_xml_rows))
    if rows:
        return rows
    return [
        {
            "record_class": "decode_status",
            "is_actual_pick_record": "no",
            "well_name": "",
            "top_name": "",
            "measured_depth": "",
            "depth_unit": "",
            "source_file": "",
            "source_field": "",
            "source_value": "",
            "source_row": "",
            "decode_status": "no_well_top_records_decoded_from_current_zero_gui_sources",
        }
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-name", default=PROJECT_NAME_DEFAULT)
    parser.add_argument("--petrel-version", default=PETREL_VERSION_DEFAULT)
    parser.add_argument("--export-package", required=True)
    parser.add_argument("--inventory-package", default="")
    parser.add_argument("--max-native-xml-rows", type=int, default=200)
    args = parser.parse_args()

    export_package = Path(args.export_package).resolve()
    las_root = export_package / "02_wells" / "well_logs_las"
    if not las_root.exists():
        raise FileNotFoundError(f"LAS folder not found: {las_root}")

    las_files = sorted(las_root.rglob("*.las"))
    if not las_files:
        raise FileNotFoundError(f"No LAS files found under: {las_root}")

    parsed_las = [parse_las(path, export_package) for path in las_files]
    header_rows = build_header_rows(args.project_name, parsed_las)
    curve_rows = build_curve_rows(args.project_name, parsed_las)
    top_rows = build_top_rows(export_package, parsed_las, args.max_native_xml_rows)

    headers_path = export_package / "02_wells" / "well_headers" / "las_well_headers.csv"
    curves_path = export_package / "02_wells" / "well_headers" / "las_curve_inventory.csv"
    tops_path = export_package / "02_wells" / "well_tops" / "well_tops_from_zero_gui_sources.csv"
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d_%H%M%S")
    report_path = export_package / "07_workflows_reports" / "zero_gui_well_exports" / f"well_tables_zero_gui_{stamp}.json"

    write_csv(
        headers_path,
        header_rows,
        [
            "project_name",
            "well_name",
            "source_las_file",
            "source_las_directory",
            "curve_count",
            "data_row_count",
            "top_link_curve_present",
            "top_link_curve_name",
            "top_link_non_null_count",
            "top_link_unique_values",
            "start_depth",
            "stop_depth",
            "step",
            "depth_unit",
            "null_value",
            "uwi",
            "api",
            "company",
            "field",
            "location",
            "service_company",
            "province",
            "las_export_date",
            "source_status",
        ],
    )
    write_csv(
        curves_path,
        curve_rows,
        [
            "project_name",
            "well_name",
            "source_las_file",
            "curve_index",
            "mnemonic",
            "unit",
            "description",
            "is_depth_curve",
            "is_well_top_link_curve",
        ],
    )
    write_csv(
        tops_path,
        top_rows,
        [
            "record_class",
            "is_actual_pick_record",
            "well_name",
            "top_name",
            "measured_depth",
            "depth_unit",
            "source_file",
            "source_field",
            "source_value",
            "source_row",
            "decode_status",
        ],
    )

    actual_top_pick_rows = sum(1 for row in top_rows if clean(row.get("is_actual_pick_record", "")).lower() == "yes")
    well_top_reference_rows = len(top_rows) - actual_top_pick_rows
    report = {
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "project_name": args.project_name,
        "petrel_version": args.petrel_version,
        "export_package": str(export_package),
        "inventory_package": args.inventory_package,
        "runtime_gui_used": False,
        "petrel_process_launched": False,
        "las_files": len(las_files),
        "well_header_rows": len(header_rows),
        "curve_inventory_rows": len(curve_rows),
        "well_top_reference_rows": well_top_reference_rows,
        "actual_well_top_pick_rows": actual_top_pick_rows,
        "well_top_export_status": "actual_petrel_marker_pick_table_not_exported",
        "well_top_rows": len(top_rows),
        "las_top_link_rows": sum(len(las["top_link_rows"]) for las in parsed_las),
        "well_top_decode_status_counts": count_values(top_rows, "decode_status"),
        "outputs": {
            "well_headers": str(headers_path),
            "curve_inventory": str(curves_path),
            "well_top_reference_inventory": str(tops_path),
        },
        "boundary": (
            "Well headers and curve inventory are derived from exported LAS files. "
            "The well-top CSV is a reference inventory only: LAS zone-log values and native XML references. "
            "It is not an actual Petrel marker pick table, and binary marker pick-depth records are not "
            "decoded by this zero-GUI pass."
        ),
    }
    write_json(report_path, report)

    print(f"WellHeaders: {headers_path}")
    print(f"CurveInventory: {curves_path}")
    print(f"WellTopReferenceInventory: {tops_path}")
    print(f"Report: {report_path}")
    print("SummaryJson:")
    print(json.dumps(report, indent=2, ensure_ascii=True))
    return 0


def count_values(rows: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = clean(row.get(field, "")) or "(blank)"
        counts[value] = counts.get(value, 0) + 1
    return counts


if __name__ == "__main__":
    raise SystemExit(main())
