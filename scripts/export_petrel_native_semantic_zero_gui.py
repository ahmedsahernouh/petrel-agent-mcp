#!/usr/bin/env python3
"""Extract safe zero-GUI semantic metadata from copied Petrel native stores.

This script reads the exported native store package created by
export_petrel_native_project_zero_gui.ps1. It does not launch Petrel, does not
use Ocean, and does not modify .pet/.ptd project files. Outputs are metadata
CSV/JSON files with explicit boundaries: native geometry arrays and proprietary
payloads are not decoded here.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET


PROJECT_NAME_DEFAULT = "Petrel2010 demo project"
PETREL_VERSION_DEFAULT = "2018.2.0.5333"
DOTNET_EPOCH_TICKS = 621355968000000000


def win_rel(base: Path, path: Path) -> str:
    return os.path.relpath(path, base).replace("/", "\\")


def slug(value: str) -> str:
    out = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()
    return out or "native_semantic"


def short_hash(value: str, length: int = 10) -> str:
    return hashlib.sha256(value.lower().encode("utf-8")).hexdigest()[:length]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def clean(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def child_text(element: ET.Element, name: str) -> str:
    child = element.find(name)
    if child is None:
        return ""
    return clean(child.text)


def dotnet_ticks_to_iso(value: str) -> str:
    try:
        ticks = int(value)
    except (TypeError, ValueError):
        return ""
    try:
        seconds = (ticks - DOTNET_EPOCH_TICKS) / 10_000_000
        return dt.datetime.fromtimestamp(seconds, tz=dt.timezone.utc).isoformat()
    except (OSError, OverflowError, ValueError):
        return ""


def parse_droid_id(droid: str) -> str:
    match = re.search(r"(?:&|[?])Id=([^&\s]+)", droid)
    if match:
        return match.group(1)
    match = re.search(r"/([0-9a-fA-F-]{16,})$", droid)
    if match:
        return match.group(1)
    return ""


def parse_droid_type(droid: str) -> str:
    match = re.search(r"(?:&|[?])Type=([^&\s]+)", droid)
    return match.group(1) if match else ""


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


def read_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def load_native_inventory(export_package: Path) -> dict[str, dict[str, str]]:
    inventory = export_package / "00_manifest" / "native_store_inventory.csv"
    if not inventory.exists():
        return {}
    _, rows = read_csv_rows(inventory)
    return {row.get("source_relative_path", ""): row for row in rows}


def manifest_blank_row(headers: list[str]) -> dict[str, str]:
    return {header: "" for header in headers}


def upsert_manifest(export_package: Path, rows: list[dict[str, str]]) -> dict[str, int]:
    manifest_path = export_package / "00_manifest" / "export_manifest.csv"
    headers, existing_rows = read_csv_rows(manifest_path)
    if not headers:
        raise RuntimeError(f"Manifest has no headers: {manifest_path}")

    by_file = {row["export_file"]: row for row in rows}
    used: set[str] = set()
    output: list[dict[str, str]] = []
    updated = 0
    for existing in existing_rows:
        export_file = existing.get("export_file", "")
        if export_file in by_file:
            output.append(by_file[export_file])
            used.add(export_file)
            updated += 1
        else:
            output.append(existing)

    appended = 0
    for row in rows:
        export_file = row["export_file"]
        if export_file not in used:
            output.append(row)
            used.add(export_file)
            appended += 1

    with manifest_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        for row in output:
            writer.writerow({header: row.get(header, "") for header in headers})

    return {"updated": updated, "appended": appended}


def new_manifest_row(
    headers: list[str],
    export_package: Path,
    path: Path,
    project_name: str,
    petrel_version: str,
    export_date_utc: str,
    source_type: str,
    export_format: str,
    notes: str,
) -> dict[str, str]:
    row = manifest_blank_row(headers)
    rel = win_rel(export_package, path)
    row["export_id"] = f"zero_gui_semantic_{slug(rel)}_{short_hash(rel)}"
    row["project_name"] = project_name
    row["petrel_version"] = petrel_version
    row["export_date_utc"] = export_date_utc
    row["source_object_path"] = f"Petrel native semantic extraction/{rel}"
    row["source_object_type"] = source_type
    row["export_format"] = export_format
    row["export_file"] = rel
    row["export_status"] = "exported_zero_gui_semantic"
    row["validation_status"] = "unchecked"
    row["sha256"] = sha256(path)
    row["notes"] = notes
    return row


def parse_modeling_data(modeling_xml: Path) -> dict[str, list[dict[str, str]]]:
    result = {
        "frameworks": [],
        "faults": [],
        "horizons": [],
        "zones": [],
        "object_counts": [],
    }
    if not modeling_xml.exists():
        return result

    root = ET.parse(modeling_xml).getroot()
    source_rel = "SMD\\ModelingData.xml"
    counts = Counter(child.tag for child in list(root))
    for tag, count in sorted(counts.items()):
        result["object_counts"].append(
            {
                "source_relative_path": source_rel,
                "object_class": tag,
                "count": str(count),
            }
        )

    def base_row(element: ET.Element, object_class: str) -> dict[str, str]:
        droid = child_text(element, "DroidString")
        last_ticks = child_text(element, "LastModificationTime")
        return {
            "object_class": object_class,
            "object_id": parse_droid_id(droid),
            "object_droid_type": parse_droid_type(droid),
            "name": child_text(element, "Name"),
            "volcan_name": child_text(element, "VolcanName"),
            "domain_name": child_text(element, "DomainName"),
            "droid_string": droid,
            "last_modification_time_raw": last_ticks,
            "last_modification_time_utc": dotnet_ticks_to_iso(last_ticks),
            "last_modification_user": child_text(element, "LastModificationUser"),
            "source_relative_path": source_rel,
            "decode_status": "xml_metadata_only_no_geometry_arrays_decoded",
        }

    for element in root.findall("StructuralFrameworkImpl"):
        row = base_row(element, "StructuralFrameworkImpl")
        row.update(
            {
                "fault_model_collection_droid": child_text(element, "FaultModelCollectionDroid"),
                "horizon_model_collection_droid": child_text(element, "HorizonModelCollectionDroid"),
                "structural_framework_file": child_text(element, "StructuralFrameworkFile"),
                "fault_horizon_parameter_file": child_text(element, "FaultHorizonParameterFile"),
            }
        )
        result["frameworks"].append(row)

    for element in root.findall("FaultModelImpl"):
        row = base_row(element, "FaultModelImpl")
        row.update(
            {
                "initial_fault_droid": child_text(element, "InitialFaultDroid"),
                "prototype_droid": child_text(element, "PrototypeDroid"),
                "fault_associations_file": child_text(element, "FaultAssociationsFile"),
            }
        )
        result["faults"].append(row)

    for element in root.findall("HorizonModelImpl"):
        row = base_row(element, "HorizonModelImpl")
        row.update(
            {
                "prototype_droid": child_text(element, "PrototypeDroid"),
                "horizon_file": child_text(element, "HorizonFile"),
                "top_zone_droid": child_text(element, "TopZoneDroid"),
                "base_zone_droid": child_text(element, "BaseZoneDroid"),
            }
        )
        result["horizons"].append(row)

    for element in root.findall("ZoneModelImpl"):
        row = base_row(element, "ZoneModelImpl")
        row.update(
            {
                "top_horizon_droid": child_text(element, "TopHorizonDroid"),
                "base_horizon_droid": child_text(element, "BaseHorizonDroid"),
                "prototype_droid": child_text(element, "PrototypeDroid"),
            }
        )
        result["zones"].append(row)

    return result


def parse_prop_file(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    lines = [line.strip() for line in text.splitlines()]
    start = 1 if lines and re.fullmatch(r"\d+", lines[0]) else 0
    props: dict[str, str] = {}
    i = start
    while i + 1 < len(lines):
        key = lines[i].strip()
        value = lines[i + 1].strip()
        if key:
            props[key] = value
        i += 2
    return props


def infer_prop_kind(keys: list[str]) -> str:
    joined = "\n".join(keys)
    if "Surface.Fault." in joined:
        return "fault_surface_property_metadata"
    if "Horizon" in joined:
        return "horizon_property_metadata"
    if "GridLattice" in joined or "Pillar" in joined:
        return "grid_property_metadata"
    return "native_property_metadata"


def parse_gms_properties(gms_dir: Path, export_package: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if not gms_dir.exists():
        return rows

    selected_keys = [
        "Surface.Fault.Type",
        "Surface.Fault.GridInterval",
        "Surface.Fault.Smoothing",
        "Surface.Fault.Size",
        "Surface.Fault.NumListOfFaultRelationships",
        "Surface.Fault.NumDisplacementData",
        "Surface.Fault.FaultBestFitPlaneGrid.IsDefined",
        "Surface.Fault.FaultBestFitPlaneGrid.SurfaceSetGrid.GridLattice.X.Range.Min",
        "Surface.Fault.FaultBestFitPlaneGrid.SurfaceSetGrid.GridLattice.X.Range.Max",
        "Surface.Fault.FaultBestFitPlaneGrid.SurfaceSetGrid.GridLattice.X.Range.Num",
        "Surface.Fault.FaultBestFitPlaneGrid.SurfaceSetGrid.GridLattice.Y.Range.Min",
        "Surface.Fault.FaultBestFitPlaneGrid.SurfaceSetGrid.GridLattice.Y.Range.Max",
        "Surface.Fault.FaultBestFitPlaneGrid.SurfaceSetGrid.GridLattice.Y.Range.Num",
        "Surface.Fault.FaultBestFitPlaneGrid.SurfaceSetGrid.GridLattice.Origin.Point3D.X",
        "Surface.Fault.FaultBestFitPlaneGrid.SurfaceSetGrid.GridLattice.Origin.Point3D.Y",
        "Surface.Fault.FaultBestFitPlaneGrid.SurfaceSetGrid.GridLattice.Origin.Point3D.Z",
    ]

    for prop in sorted(gms_dir.glob("*.prop.ptd")):
        props = parse_prop_file(prop)
        keys = sorted(props)
        bulk = prop.with_name(prop.name.replace(".prop.ptd", ".bulk.ptd"))
        prefix_counts = Counter(key.split(".")[0] for key in keys)
        truncating_faults = sorted(
            {
                value
                for key, value in props.items()
                if key.endswith("TruncatingFault.UniqueName") and value
            }
        )
        row = {
            "property_file_id": prop.name.replace(".prop.ptd", ""),
            "property_file": win_rel(export_package, prop),
            "bulk_file": win_rel(export_package, bulk) if bulk.exists() else "",
            "bulk_size_bytes": str(bulk.stat().st_size) if bulk.exists() else "",
            "property_count": str(len(props)),
            "property_kind": infer_prop_kind(keys),
            "top_key_prefixes": ";".join(f"{key}:{count}" for key, count in prefix_counts.most_common(8)),
            "referenced_truncating_fault_unique_names": ";".join(truncating_faults[:20]),
            "decode_status": "key_value_metadata_only_no_bulk_geometry_decoded",
        }
        for key in selected_keys:
            row[slug(key)] = props.get(key, "")
        rows.append(row)
    return rows


def sqlite_schema_rows(qr_dir: Path, export_package: Path) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    schema_rows: list[dict[str, str]] = []
    value_rows: list[dict[str, str]] = []
    if not qr_dir.exists():
        return schema_rows, value_rows

    for db in sorted(qr_dir.glob("*.db")):
        rel = win_rel(export_package, db)
        con = sqlite3.connect(str(db))
        try:
            tables = con.execute(
                "select name, type from sqlite_master where type in ('table','view') order by type,name"
            ).fetchall()
            for table_name, table_type in tables:
                cols = con.execute(f'pragma table_info("{table_name}")').fetchall()
                col_desc = ";".join(f"{col[1]}:{col[2]}" for col in cols)
                try:
                    row_count = con.execute(f'select count(*) from "{table_name}"').fetchone()[0]
                except sqlite3.DatabaseError:
                    row_count = -1
                schema_rows.append(
                    {
                        "database_file": rel,
                        "sqlite_object_type": table_type,
                        "table_name": table_name,
                        "row_count": str(row_count),
                        "column_count": str(len(cols)),
                        "columns": col_desc,
                    }
                )

                if row_count > 0 and row_count <= 250 and len(cols) <= 4:
                    column_names = [col[1] for col in cols]
                    for values in con.execute(f'select * from "{table_name}" limit 250').fetchall():
                        value_rows.append(
                            {
                                "database_file": rel,
                                "table_name": table_name,
                                "columns": ";".join(column_names),
                                "values": ";".join(clean(value) for value in values),
                            }
                        )
        finally:
            con.close()
    return schema_rows, value_rows


def extract_xml_metadata(ptd_root: Path, export_package: Path, max_names: int) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    files = sorted(list(ptd_root.rglob("*.xml")) + list(ptd_root.rglob("*.bxml")))
    name_pattern = re.compile(r"<(?:Name|DisplayName|ObjectName|TemplateName|WindowName)>([^<]{1,220})</", re.I)
    droid_pattern = re.compile(r"://[^<\s]+(?:Type=|/)[^<\s]+", re.I)
    terms = ["Well", "WellLog", "Surface", "Horizon", "Fault", "Seismic", "Grid", "Workflow", "Report", "Window"]

    for path in files:
        rel = win_rel(export_package, path)
        raw = path.read_bytes()
        text = raw.decode("utf-8", errors="ignore")
        parse_status = "not_xml_parsed"
        root_tag = ""
        direct_child_count = ""
        first_lt = text.find("<")
        if first_lt >= 0:
            xml_candidate = text[first_lt:]
            try:
                root = ET.fromstring(xml_candidate)
                parse_status = "xml_parsed"
                root_tag = root.tag.split("}")[-1]
                direct_child_count = str(len(list(root)))
            except ET.ParseError:
                parse_status = "xml_text_scanned_parse_failed"

        names = [clean(match.group(1)) for match in name_pattern.finditer(text)]
        droids = [clean(match.group(0)) for match in droid_pattern.finditer(text)]
        term_flags = [term for term in terms if re.search(term, text, re.I)]
        rows.append(
            {
                "source_relative_path": win_rel(ptd_root, path),
                "package_relative_path": rel,
                "size_bytes": str(path.stat().st_size),
                "parse_status": parse_status,
                "root_tag": root_tag,
                "direct_child_count": direct_child_count,
                "name_count": str(len(names)),
                "first_names": ";".join(names[:max_names]),
                "droid_reference_count": str(len(droids)),
                "first_droid_references": ";".join(droids[:max_names]),
                "term_flags": ";".join(term_flags),
            }
        )
    return rows


def zgy_rows(export_package: Path, native_inventory: dict[str, dict[str, str]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    ptd_root = export_package / "08_native_project" / "ptd_store"
    for path in sorted(ptd_root.glob("*.zgy")):
        source_rel = win_rel(ptd_root, path)
        inv = native_inventory.get(source_rel, {})
        rows.append(
            {
                "source_relative_path": source_rel,
                "package_relative_path": win_rel(export_package, path),
                "file_name": path.name,
                "size_bytes": str(path.stat().st_size),
                "sha256": inv.get("sha256", sha256(path)),
                "format_signature": inv.get("format_signature", "ZGY"),
                "decode_status": "native_zgy_inventory_only_cube_samples_not_decoded",
            }
        )
    return rows


def output_definitions(export_package: Path) -> dict[str, tuple[Path, str, str, list[str]]]:
    return {
        "project_object_counts": (
            export_package / "01_project_metadata" / "native_project_object_counts.csv",
            "project_metadata",
            "CSV",
            ["source_relative_path", "object_class", "count"],
        ),
        "project_metadata": (
            export_package / "01_project_metadata" / "native_project_metadata_zero_gui.json",
            "project_metadata",
            "JSON",
            [],
        ),
        "ocean_xml_metadata": (
            export_package / "01_project_metadata" / "native_ocean_xml_metadata.csv",
            "native_xml_metadata",
            "CSV",
            [
                "source_relative_path",
                "package_relative_path",
                "size_bytes",
                "parse_status",
                "root_tag",
                "direct_child_count",
                "name_count",
                "first_names",
                "droid_reference_count",
                "first_droid_references",
                "term_flags",
            ],
        ),
        "sqlite_schema": (
            export_package / "01_project_metadata" / "native_sqlite_schema.csv",
            "sqlite_metadata",
            "CSV",
            ["database_file", "sqlite_object_type", "table_name", "row_count", "column_count", "columns"],
        ),
        "sqlite_values": (
            export_package / "01_project_metadata" / "native_sqlite_reference_values.csv",
            "sqlite_metadata",
            "CSV",
            ["database_file", "table_name", "columns", "values"],
        ),
        "faults": (
            export_package / "05_interpretation" / "faults" / "native_fault_models.csv",
            "fault_metadata",
            "CSV",
            [
                "object_class",
                "object_id",
                "object_droid_type",
                "name",
                "volcan_name",
                "domain_name",
                "droid_string",
                "initial_fault_droid",
                "prototype_droid",
                "fault_associations_file",
                "last_modification_time_raw",
                "last_modification_time_utc",
                "last_modification_user",
                "source_relative_path",
                "decode_status",
            ],
        ),
        "horizons": (
            export_package / "05_interpretation" / "horizons" / "native_horizon_models.csv",
            "horizon_metadata",
            "CSV",
            [
                "object_class",
                "object_id",
                "object_droid_type",
                "name",
                "volcan_name",
                "domain_name",
                "droid_string",
                "prototype_droid",
                "horizon_file",
                "top_zone_droid",
                "base_zone_droid",
                "last_modification_time_raw",
                "last_modification_time_utc",
                "last_modification_user",
                "source_relative_path",
                "decode_status",
            ],
        ),
        "zones": (
            export_package / "05_interpretation" / "horizons" / "native_zone_models.csv",
            "zone_metadata",
            "CSV",
            [
                "object_class",
                "object_id",
                "object_droid_type",
                "name",
                "volcan_name",
                "domain_name",
                "droid_string",
                "top_horizon_droid",
                "base_horizon_droid",
                "prototype_droid",
                "last_modification_time_raw",
                "last_modification_time_utc",
                "last_modification_user",
                "source_relative_path",
                "decode_status",
            ],
        ),
        "frameworks": (
            export_package / "06_models_properties" / "structural_models" / "native_structural_frameworks.csv",
            "structural_framework_metadata",
            "CSV",
            [
                "object_class",
                "object_id",
                "object_droid_type",
                "name",
                "volcan_name",
                "domain_name",
                "droid_string",
                "fault_model_collection_droid",
                "horizon_model_collection_droid",
                "structural_framework_file",
                "fault_horizon_parameter_file",
                "last_modification_time_raw",
                "last_modification_time_utc",
                "last_modification_user",
                "source_relative_path",
                "decode_status",
            ],
        ),
        "gms_properties": (
            export_package / "06_models_properties" / "structural_models" / "native_gms_property_files.csv",
            "native_gms_property_metadata",
            "CSV",
            [
                "property_file_id",
                "property_file",
                "bulk_file",
                "bulk_size_bytes",
                "property_count",
                "property_kind",
                "top_key_prefixes",
                "referenced_truncating_fault_unique_names",
                "surface_fault_type",
                "surface_fault_gridinterval",
                "surface_fault_smoothing",
                "surface_fault_size",
                "surface_fault_numlistoffaultrelationships",
                "surface_fault_numdisplacementdata",
                "surface_fault_faultbestfitplanegrid_isdefined",
                "surface_fault_faultbestfitplanegrid_surfacesetgrid_gridlattice_x_range_min",
                "surface_fault_faultbestfitplanegrid_surfacesetgrid_gridlattice_x_range_max",
                "surface_fault_faultbestfitplanegrid_surfacesetgrid_gridlattice_x_range_num",
                "surface_fault_faultbestfitplanegrid_surfacesetgrid_gridlattice_y_range_min",
                "surface_fault_faultbestfitplanegrid_surfacesetgrid_gridlattice_y_range_max",
                "surface_fault_faultbestfitplanegrid_surfacesetgrid_gridlattice_y_range_num",
                "surface_fault_faultbestfitplanegrid_surfacesetgrid_gridlattice_origin_point3d_x",
                "surface_fault_faultbestfitplanegrid_surfacesetgrid_gridlattice_origin_point3d_y",
                "surface_fault_faultbestfitplanegrid_surfacesetgrid_gridlattice_origin_point3d_z",
                "decode_status",
            ],
        ),
        "zgy": (
            export_package / "03_seismic" / "seismic_metadata" / "native_zgy_inventory.csv",
            "seismic_metadata",
            "CSV",
            ["source_relative_path", "package_relative_path", "file_name", "size_bytes", "sha256", "format_signature", "decode_status"],
        ),
    }


def run_validation(script_dir: Path, export_package: Path) -> tuple[str, str, str]:
    validator = script_dir / "validate_export_package.ps1"
    command = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(validator),
        "-ExportPackage",
        str(export_package),
        "-UpdateManifest",
        "-WriteChecksums",
    ]
    proc = subprocess.run(command, cwd=str(script_dir.parent), capture_output=True, text=True, timeout=600)
    stdout = proc.stdout.strip()
    stderr = proc.stderr.strip()
    status = "failed" if proc.returncode else "passed"
    report = ""
    for line in stdout.splitlines():
        if line.startswith("Validation status:"):
            status = line.split(":", 1)[1].strip()
        if line.startswith("Report:"):
            report = line.split(":", 1)[1].strip()
    return status, report, stderr


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-name", default=PROJECT_NAME_DEFAULT)
    parser.add_argument("--project-file", default="")
    parser.add_argument("--petrel-version", default=PETREL_VERSION_DEFAULT)
    parser.add_argument("--export-package", required=True)
    parser.add_argument("--inventory-package", default="")
    parser.add_argument("--max-xml-names", type=int, default=20)
    parser.add_argument("--no-validate", action="store_true")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    export_package = Path(args.export_package).resolve()
    ptd_root = export_package / "08_native_project" / "ptd_store"
    if not ptd_root.exists():
        raise SystemExit(f"Native store export not found: {ptd_root}")
    manifest_path = export_package / "00_manifest" / "export_manifest.csv"
    if not manifest_path.exists():
        raise SystemExit(f"Manifest not found: {manifest_path}")

    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    export_date_utc = dt.datetime.now(dt.timezone.utc).isoformat()
    native_inventory = load_native_inventory(export_package)
    outputs = output_definitions(export_package)

    modeling = parse_modeling_data(ptd_root / "SMD" / "ModelingData.xml")
    gms = parse_gms_properties(ptd_root / "SMD" / "GMS", export_package)
    sqlite_schema, sqlite_values = sqlite_schema_rows(ptd_root / "Ocean" / "QR", export_package)
    xml_metadata = extract_xml_metadata(ptd_root, export_package, args.max_xml_names)
    zgy = zgy_rows(export_package, native_inventory)

    path, _, _, fields = outputs["project_object_counts"]
    write_csv(path, modeling["object_counts"], fields)
    path, _, _, fields = outputs["faults"]
    write_csv(path, modeling["faults"], fields)
    path, _, _, fields = outputs["horizons"]
    write_csv(path, modeling["horizons"], fields)
    path, _, _, fields = outputs["zones"]
    write_csv(path, modeling["zones"], fields)
    path, _, _, fields = outputs["frameworks"]
    write_csv(path, modeling["frameworks"], fields)
    path, _, _, fields = outputs["gms_properties"]
    write_csv(path, gms, fields)
    path, _, _, fields = outputs["sqlite_schema"]
    write_csv(path, sqlite_schema, fields)
    path, _, _, fields = outputs["sqlite_values"]
    write_csv(path, sqlite_values, fields)
    path, _, _, fields = outputs["ocean_xml_metadata"]
    write_csv(path, xml_metadata, fields)
    path, _, _, fields = outputs["zgy"]
    write_csv(path, zgy, fields)

    project_metadata_path, _, _, _ = outputs["project_metadata"]
    project_metadata = {
        "created_at_utc": export_date_utc,
        "project_name": args.project_name,
        "project_file": args.project_file,
        "petrel_version": args.petrel_version,
        "export_package": str(export_package),
        "runtime_gui_used": False,
        "petrel_process_launched": False,
        "semantic_extract_status": "completed",
        "decode_boundary": "Metadata decoded from XML, SQLite, text-like property stores, and native file inventory. Proprietary arrays, seismic samples, grid bulk geometry, and full object payloads are not decoded.",
        "counts": {
            "structural_frameworks": len(modeling["frameworks"]),
            "fault_models": len(modeling["faults"]),
            "horizon_models": len(modeling["horizons"]),
            "zone_models": len(modeling["zones"]),
            "gms_property_files": len(gms),
            "sqlite_schema_rows": len(sqlite_schema),
            "sqlite_reference_rows": len(sqlite_values),
            "xml_metadata_files": len(xml_metadata),
            "zgy_files": len(zgy),
        },
    }
    write_json(project_metadata_path, project_metadata)

    report_root = export_package / "07_workflows_reports" / "native_semantic_export"
    report_json = report_root / f"zero_gui_native_semantic_export_{stamp}.json"
    report_md = report_root / f"zero_gui_native_semantic_export_{stamp}.md"

    headers, _ = read_csv_rows(manifest_path)
    manifest_rows: list[dict[str, str]] = []
    notes = {
        "project_metadata": "Zero-GUI project/native semantic metadata summary.",
        "project_object_counts": "Zero-GUI object-class counts parsed from SMD/ModelingData.xml.",
        "ocean_xml_metadata": "Zero-GUI scan of XML/BXML metadata names and references; binary BXML payloads are not decoded.",
        "sqlite_schema": "Zero-GUI SQLite schema and row-count metadata from copied Ocean QR stores.",
        "sqlite_values": "Zero-GUI SQLite small reference table values from copied Ocean QR stores.",
        "faults": "Fault metadata parsed from SMD/ModelingData.xml; geometry arrays are not decoded.",
        "horizons": "Horizon metadata parsed from SMD/ModelingData.xml; surfaces are not converted.",
        "zones": "Zone metadata parsed from SMD/ModelingData.xml.",
        "frameworks": "Structural framework metadata parsed from SMD/ModelingData.xml.",
        "gms_properties": "Structural GMS property-store key/value metadata; bulk geometry stores are not decoded.",
        "zgy": "Native ZGY seismic file inventory; seismic cube samples are not decoded.",
    }
    for key, (path, source_type, export_format, _fields) in outputs.items():
        manifest_rows.append(
            new_manifest_row(
                headers,
                export_package,
                path,
                args.project_name,
                args.petrel_version,
                export_date_utc,
                source_type,
                export_format,
                notes.get(key, "Zero-GUI native semantic metadata export."),
            )
        )

    summary = {
        "run_id": f"zero_gui_native_semantic_export_{stamp}",
        "created_at_utc": export_date_utc,
        "project_name": args.project_name,
        "project_file": args.project_file,
        "petrel_version": args.petrel_version,
        "export_package": str(export_package),
        "runtime_gui_used": False,
        "petrel_process_launched": False,
        "export_mode": "zero_gui_native_semantic_metadata_extraction",
        "universal_conversion_status": "metadata_only_no_proprietary_array_decode",
        "outputs": {
            key: win_rel(export_package, path)
            for key, (path, _source_type, _export_format, _fields) in outputs.items()
        },
        "counts": project_metadata["counts"],
        "manifest_path": str(manifest_path),
    }
    write_json(report_json, summary)
    report_md.write_text(
        "\n".join(
            [
                "# Zero-GUI Native Semantic Export",
                "",
                f"- Project: {args.project_name}",
                f"- Export package: {export_package}",
                "- Runtime GUI used: false",
                "- Petrel launched: false",
                f"- Fault models: {len(modeling['faults'])}",
                f"- Horizon models: {len(modeling['horizons'])}",
                f"- Zone models: {len(modeling['zones'])}",
                f"- Structural frameworks: {len(modeling['frameworks'])}",
                f"- GMS property files: {len(gms)}",
                f"- SQLite schema rows: {len(sqlite_schema)}",
                f"- XML/BXML metadata files scanned: {len(xml_metadata)}",
                f"- ZGY native files inventoried: {len(zgy)}",
                "",
                "## Boundary",
                "",
                "This pass decodes safe metadata from copied native stores only. It does not convert proprietary Petrel arrays, grid bulk geometry, or seismic cube samples to LAS/SEG-Y/ZMAP/RESQML.",
            ]
        ),
        encoding="utf-8",
    )

    for report_path in (report_json, report_md):
        manifest_rows.append(
            new_manifest_row(
                headers,
                export_package,
                report_path,
                args.project_name,
                args.petrel_version,
                export_date_utc,
                "native_semantic_report",
                "JSON" if report_path.suffix.lower() == ".json" else "MD",
                "Zero-GUI native semantic extraction run report.",
            )
        )

    upsert = upsert_manifest(export_package, manifest_rows)
    summary["manifest_updated"] = upsert["updated"]
    summary["manifest_appended"] = upsert["appended"]

    validation_status = "skipped"
    validation_report = ""
    validation_stderr = ""
    if not args.no_validate:
        validation_status, validation_report, validation_stderr = run_validation(script_dir, export_package)

    summary["validation_status"] = validation_status
    summary["validation_report"] = validation_report
    if validation_stderr:
        summary["validation_stderr"] = validation_stderr
    write_json(report_json, summary)

    print("Zero-GUI native semantic export: completed")
    print(f"Export package: {export_package}")
    print(f"Fault models: {len(modeling['faults'])}")
    print(f"Horizon models: {len(modeling['horizons'])}")
    print(f"Zone models: {len(modeling['zones'])}")
    print(f"Structural frameworks: {len(modeling['frameworks'])}")
    print(f"GMS property files: {len(gms)}")
    print(f"SQLite schema rows: {len(sqlite_schema)}")
    print(f"XML/BXML metadata files: {len(xml_metadata)}")
    print(f"ZGY native files: {len(zgy)}")
    print(f"Summary: {report_json}")
    print(f"Validation: {validation_status}")
    if validation_report:
        print(f"Validation report: {validation_report}")

    return 5 if validation_status == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
