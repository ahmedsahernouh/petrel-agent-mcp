"""Zero-GUI Petrel project audit report.

Reads an existing export package (manifest, report JSONs, derived CSVs) and
writes a self-contained HTML audit plus a JSON summary. Never launches Petrel
and needs no Petrel license: every input is a file the export chain already
produced. Every section is optional; missing inputs render as "not available"
so the report still works on packages where only part of the chain has run.

Usage:
    python scripts/report_petrel_project_audit.py --export-package <path>
        [--output-dir <path>] [--title <text>]

Prints a single "SummaryJson:{...}" line for the MCP chain-tool runner.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

TOOL_VERSION = "1.0"
NOT_AVAILABLE = "not available in this export package"


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json_file(path: Path) -> dict | None:
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None


def read_csv_rows(path: Path) -> list[dict]:
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))
    except OSError:
        return []


def latest_report(directory: Path, prefix: str) -> Path | None:
    if not directory.is_dir():
        return None
    matches = sorted(directory.glob(prefix + "*.json"))
    return matches[-1] if matches else None


def to_float(value: str | None) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except ValueError:
        return None


def gather_project_summary(package: Path) -> dict:
    summary = load_json_file(package / "01_project_metadata" / "project_summary.json") or {}
    return {
        "project_name": summary.get("project_name", ""),
        "petrel_version": summary.get("petrel_version", ""),
        "project_path": summary.get("project_path", ""),
        "export_id": summary.get("export_id", package.name),
        "coordinate_reference_system": summary.get("coordinate_reference_system", ""),
        "available": bool(summary),
    }


def gather_manifest(package: Path) -> dict:
    manifest_path = package / "00_manifest" / "export_manifest.csv"
    rows = read_csv_rows(manifest_path)
    if not rows:
        return {"available": False, "row_count": 0}
    by_type: dict[str, int] = {}
    by_format: dict[str, int] = {}
    by_validation: dict[str, int] = {}
    crs_values: dict[str, int] = {}
    dates: list[str] = []
    checksum_rows = 0
    for row in rows:
        by_type[row.get("source_object_type", "")] = by_type.get(row.get("source_object_type", ""), 0) + 1
        by_format[row.get("export_format", "")] = by_format.get(row.get("export_format", ""), 0) + 1
        by_validation[row.get("validation_status", "")] = by_validation.get(row.get("validation_status", ""), 0) + 1
        crs = (row.get("coordinate_reference_system") or "").strip()
        if crs and crs.lower() != "unknown":
            crs_values[crs] = crs_values.get(crs, 0) + 1
        if row.get("sha256"):
            checksum_rows += 1
        date = (row.get("export_date_utc") or "").strip()
        if date:
            dates.append(date)
    return {
        "available": True,
        "path": str(manifest_path),
        "row_count": len(rows),
        "by_source_object_type": dict(sorted(by_type.items(), key=lambda item: -item[1])),
        "by_export_format": dict(sorted(by_format.items(), key=lambda item: -item[1])),
        "by_validation_status": by_validation,
        "checksummed_rows": checksum_rows,
        "crs_values": crs_values,
        "export_date_range": [min(dates), max(dates)] if dates else [],
    }


def gather_wells(package: Path) -> dict:
    headers = read_csv_rows(package / "02_wells" / "well_headers" / "las_well_headers.csv")
    curves = read_csv_rows(package / "02_wells" / "well_headers" / "las_curve_inventory.csv")
    wells = []
    for row in headers:
        wells.append(
            {
                "well_name": row.get("well_name", ""),
                "curve_count": row.get("curve_count", ""),
                "data_row_count": row.get("data_row_count", ""),
                "start_depth": to_float(row.get("start_depth")),
                "stop_depth": to_float(row.get("stop_depth")),
                "depth_unit": row.get("depth_unit", ""),
                "null_value": row.get("null_value", ""),
            }
        )
    mnemonics = sorted({row.get("mnemonic", "") for row in curves if row.get("mnemonic")})
    return {
        "available": bool(wells),
        "well_count": len(wells),
        "wells": wells,
        "curve_rows": len(curves),
        "distinct_mnemonics": mnemonics,
    }


def gather_well_tops(package: Path) -> dict:
    rows = read_csv_rows(package / "02_wells" / "well_tops" / "well_tops_from_petrel_ascii_export.csv")
    picks = [row for row in rows if (row.get("is_actual_pick_record") or "").lower() == "yes"]
    if not picks:
        return {"available": False, "pick_count": 0}
    per_surface: dict[str, int] = {}
    per_well: dict[str, int] = {}
    z_values: list[float] = []
    md_values: list[float] = []
    for row in picks:
        per_surface[row.get("surface", "")] = per_surface.get(row.get("surface", ""), 0) + 1
        per_well[row.get("well_name", "")] = per_well.get(row.get("well_name", ""), 0) + 1
        z = to_float(row.get("depth"))
        md = to_float(row.get("measured_depth"))
        if z is not None:
            z_values.append(z)
        if md is not None:
            md_values.append(md)
    return {
        "available": True,
        "pick_count": len(picks),
        "well_count": len(per_well),
        "surface_count": len(per_surface),
        "per_surface": dict(sorted(per_surface.items(), key=lambda item: -item[1])),
        "per_well": dict(sorted(per_well.items())),
        "z_range": [min(z_values), max(z_values)] if z_values else [],
        "md_range": [min(md_values), max(md_values)] if md_values else [],
        "petrel_export_confirmed": all((row.get("petrel_export_confirmed") or "").lower() == "yes" for row in picks),
    }


def gather_surfaces(package: Path) -> dict:
    report_path = latest_report(package / "07_workflows_reports" / "surfaces_export", "surfaces_zero_gui_export_")
    report = load_json_file(report_path) if report_path else None
    if not report:
        return {"available": False}
    surfaces = []
    for entry in report.get("surfaces", []):
        surfaces.append(
            {
                "guid": entry.get("guid", ""),
                "dims": entry.get("dims", []),
                "status": entry.get("status", ""),
                "live_nodes": entry.get("live_nodes"),
                "z_min": entry.get("z_min"),
                "z_max": entry.get("z_max"),
                "mask_agreement": entry.get("mask_agreement"),
            }
        )
    transform = report.get("survey_transform") or {}
    return {
        "available": True,
        "report_path": str(report_path),
        "summary": report.get("summary", {}),
        "surfaces": surfaces,
        "survey_origin": transform.get("origin_trace", {}),
    }


def gather_seismic(package: Path) -> dict:
    report_path = latest_report(package / "07_workflows_reports" / "seismic_zgy_export", "seismic_zgy_export_")
    report = load_json_file(report_path) if report_path else None
    if not report:
        return {"available": False}
    cubes = []
    for entry in report.get("cubes", []):
        stats = entry.get("amplitude_stats_decimated") or {}
        cubes.append(
            {
                "guid": entry.get("guid", ""),
                "status": entry.get("status", ""),
                "inline_count": entry.get("inline_count"),
                "xline_count": entry.get("xline_count"),
                "sample_count": entry.get("sample_count"),
                "inline_range": entry.get("inline_range", []),
                "xline_range": entry.get("xline_range", []),
                "sample_range": entry.get("sample_range", []),
                "zgy_bytes": entry.get("zgy_bytes"),
                "amplitude_min": stats.get("min"),
                "amplitude_max": stats.get("max"),
                "amplitude_rms": stats.get("rms"),
            }
        )
    return {
        "available": True,
        "report_path": str(report_path),
        "cube_count": len(cubes),
        "cubes": cubes,
        "summary": report.get("summary", {}),
    }


def gather_native_semantic(package: Path) -> dict:
    report_path = latest_report(
        package / "07_workflows_reports" / "native_semantic_export", "zero_gui_native_semantic_export_"
    )
    report = load_json_file(report_path) if report_path else None
    if not report:
        return {"available": False}
    return {
        "available": True,
        "report_path": str(report_path),
        "counts": report.get("counts", {}),
        "validation_status": report.get("validation_status", ""),
    }


def gather_domain_files(package: Path) -> dict:
    counts: dict[str, int] = {}
    for child in sorted(package.iterdir()):
        if child.is_dir() and child.name[:2].isdigit():
            counts[child.name] = sum(1 for item in child.rglob("*") if item.is_file())
    return counts


def build_qc_flags(audit: dict) -> list[dict]:
    flags: list[dict] = []

    def add(severity: str, message: str) -> None:
        flags.append({"severity": severity, "message": message})

    manifest = audit["manifest"]
    if not manifest["available"]:
        add("warning", "No export manifest found; run the export pipeline and register_and_validate first.")
    else:
        bad = {k: v for k, v in manifest["by_validation_status"].items() if k != "validated"}
        if bad:
            add("warning", f"Manifest rows not in 'validated' state: {bad}.")
        if not manifest["crs_values"]:
            add("warning", "No manifest row carries an explicit coordinate reference system; CRS is only in sidecar files.")
    project = audit["project"]
    if project["available"] and (project["coordinate_reference_system"] or "unknown").lower() == "unknown":
        add("info", "project_summary.json CRS is 'unknown'; fill it from Petrel project settings when available.")
    surfaces = audit["surfaces"]
    if surfaces["available"]:
        unresolved = [s["guid"][:8] for s in surfaces["surfaces"] if s["status"] != "exported"]
        if unresolved:
            add("info", f"{len(unresolved)} surface grid(s) refused as layout-unresolved (fail-closed): {', '.join(unresolved)}.")
    wells = audit["wells"]
    if wells["available"]:
        sparse = [w["well_name"] for w in wells["wells"] if (to_float(w["data_row_count"]) or 0) < 10]
        if sparse:
            add("info", f"{len(sparse)} LAS export(s) have fewer than 10 data rows: {', '.join(sparse)}.")
    tops = audit["well_tops"]
    if tops["available"] and not tops.get("petrel_export_confirmed", False):
        add("warning", "Well top rows are not all confirmed against a Petrel-authored export.")
    for name, section in (("wells", wells), ("well tops", tops), ("surfaces", surfaces), ("seismic", audit["seismic"])):
        if not section["available"]:
            add("info", f"No {name} evidence in this package; the corresponding export tool has not run here.")
    return flags


def esc(value: object) -> str:
    return html.escape("" if value is None else str(value))


def fmt_num(value: object, digits: int = 2) -> str:
    if value is None or value == "":
        return "-"
    try:
        return f"{float(value):,.{digits}f}"
    except (TypeError, ValueError):
        return esc(value)


def html_table(headers: list[str], rows: list[list[object]]) -> str:
    head = "".join(f"<th>{esc(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    return f'<div class="scroll"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def kpi_tile(label: str, value: str) -> str:
    return f'<div class="tile"><div class="tile-value">{esc(value)}</div><div class="tile-label">{esc(label)}</div></div>'


def render_html(audit: dict, title: str) -> str:
    project = audit["project"]
    manifest = audit["manifest"]
    wells = audit["wells"]
    tops = audit["well_tops"]
    surfaces = audit["surfaces"]
    seismic = audit["seismic"]
    semantic = audit["native_semantic"]

    tiles = [
        kpi_tile("Wells (LAS)", str(wells["well_count"]) if wells["available"] else "-"),
        kpi_tile("Log curve rows", str(wells["curve_rows"]) if wells["available"] else "-"),
        kpi_tile("Well top picks", str(tops["pick_count"]) if tops["available"] else "-"),
        kpi_tile(
            "Surfaces exported",
            f"{surfaces['summary'].get('exported', 0)}/{surfaces['summary'].get('total', 0)}" if surfaces["available"] else "-",
        ),
        kpi_tile("Seismic cubes", str(seismic["cube_count"]) if seismic["available"] else "-"),
        kpi_tile("Manifest rows", f"{manifest['row_count']:,}" if manifest["available"] else "-"),
    ]

    sections: list[str] = []

    qc_items = "".join(
        f'<li class="{esc(flag["severity"])}"><strong>{esc(flag["severity"].upper())}</strong> {esc(flag["message"])}</li>'
        for flag in audit["qc_flags"]
    ) or "<li>No findings.</li>"
    sections.append(f"<section><h2>QC findings</h2><ul class='qc'>{qc_items}</ul></section>")

    if wells["available"]:
        rows = [
            [
                esc(w["well_name"]),
                esc(w["curve_count"]),
                esc(w["data_row_count"]),
                fmt_num(w["start_depth"]),
                fmt_num(w["stop_depth"]),
                esc(w["depth_unit"]),
            ]
            for w in wells["wells"]
        ]
        mnemonics = ", ".join(wells["distinct_mnemonics"])
        sections.append(
            "<section><h2>Wells and logs</h2>"
            + html_table(["Well", "Curves", "Data rows", "Start depth", "Stop depth", "Unit"], rows)
            + f"<p class='note'>Distinct curve mnemonics ({len(wells['distinct_mnemonics'])}): {esc(mnemonics)}</p></section>"
        )
    else:
        sections.append(f"<section><h2>Wells and logs</h2><p class='note'>{NOT_AVAILABLE}</p></section>")

    if tops["available"]:
        surface_rows = [[esc(name), str(count)] for name, count in tops["per_surface"].items()]
        z_range = tops["z_range"]
        md_range = tops["md_range"]
        confirmed = "yes" if tops.get("petrel_export_confirmed") else "no"
        sections.append(
            "<section><h2>Well tops</h2>"
            + f"<p>{tops['pick_count']} marker picks across {tops['well_count']} wells and {tops['surface_count']} surfaces. "
            + (f"Z (elevation) range {fmt_num(z_range[0])} to {fmt_num(z_range[1])}. " if z_range else "")
            + (f"MD range {fmt_num(md_range[0])} to {fmt_num(md_range[1])}. " if md_range else "")
            + f"Confirmed against Petrel-authored ASCII export: {confirmed}.</p>"
            + html_table(["Surface / marker", "Picks"], surface_rows)
            + "</section>"
        )
    else:
        sections.append(f"<section><h2>Well tops</h2><p class='note'>{NOT_AVAILABLE}</p></section>")

    if surfaces["available"]:
        rows = [
            [
                esc(s["guid"][:8]),
                esc("x".join(str(d) for d in s["dims"])),
                esc(s["status"]),
                esc(s["live_nodes"] if s["live_nodes"] is not None else "-"),
                fmt_num(s["z_min"]),
                fmt_num(s["z_max"]),
                fmt_num((s["mask_agreement"] or 0) * 100, 2) + "%" if s["mask_agreement"] is not None else "-",
            ]
            for s in surfaces["surfaces"]
        ]
        origin = surfaces["survey_origin"]
        origin_note = (
            f"Survey origin trace: inline {esc(origin.get('inline'))}, xline {esc(origin.get('xline'))}, "
            f"X {fmt_num(origin.get('x'))}, Y {fmt_num(origin.get('y'))}."
            if origin
            else ""
        )
        sections.append(
            "<section><h2>Surfaces (native decode)</h2>"
            + html_table(["GUID", "Grid", "Status", "Live nodes", "Z min", "Z max", "Mask agreement"], rows)
            + f"<p class='note'>{origin_note} Non-exported grids are fail-closed refusals, not data loss.</p></section>"
        )
    else:
        sections.append(f"<section><h2>Surfaces</h2><p class='note'>{NOT_AVAILABLE}</p></section>")

    if seismic["available"]:
        rows = [
            [
                esc(c["guid"][:8]),
                esc(f"{c['inline_count']} x {c['xline_count']} x {c['sample_count']}"),
                esc(f"{c['inline_range'][0]}-{c['inline_range'][1]}" if c["inline_range"] else "-"),
                esc(f"{c['xline_range'][0]}-{c['xline_range'][1]}" if c["xline_range"] else "-"),
                esc(
                    f"{fmt_num(c['sample_range'][0], 1)} to {fmt_num(c['sample_range'][1], 1)}"
                    if c["sample_range"]
                    else "-"
                ),
                fmt_num(c["amplitude_rms"]),
                fmt_num((c["zgy_bytes"] or 0) / (1024 * 1024), 1) + " MB",
                esc(c["status"]),
            ]
            for c in seismic["cubes"]
        ]
        sections.append(
            "<section><h2>Seismic cubes (ZGY)</h2>"
            + html_table(
                ["GUID", "Dimensions", "Inlines", "Xlines", "Sample range", "RMS amplitude", "Size", "Status"], rows
            )
            + "</section>"
        )
    else:
        sections.append(f"<section><h2>Seismic cubes</h2><p class='note'>{NOT_AVAILABLE}</p></section>")

    if semantic["available"]:
        rows = [[esc(name.replace("_", " ")), str(count)] for name, count in semantic["counts"].items()]
        sections.append(
            "<section><h2>Native project store (semantic decode)</h2>"
            + html_table(["Object class", "Count"], rows)
            + f"<p class='note'>Validation status: {esc(semantic['validation_status'])}</p></section>"
        )
    else:
        sections.append(f"<section><h2>Native project store</h2><p class='note'>{NOT_AVAILABLE}</p></section>")

    if manifest["available"]:
        type_rows = [[esc(name), str(count)] for name, count in manifest["by_source_object_type"].items()]
        format_rows = [[esc(name), str(count)] for name, count in manifest["by_export_format"].items()]
        crs_text = ", ".join(f"{name} ({count} rows)" for name, count in manifest["crs_values"].items()) or "none recorded on rows"
        date_range = manifest["export_date_range"]
        sections.append(
            "<section><h2>Export manifest</h2>"
            + f"<p>{manifest['row_count']:,} rows, {manifest['checksummed_rows']:,} with SHA-256 checksums. "
            + f"Validation: {esc(manifest['by_validation_status'])}. CRS on rows: {esc(crs_text)}."
            + (f" Export dates {esc(date_range[0][:10])} to {esc(date_range[1][:10])}." if date_range else "")
            + "</p><div class='cols'><div><h3>By object type</h3>"
            + html_table(["Object type", "Rows"], type_rows)
            + "</div><div><h3>By format</h3>"
            + html_table(["Format", "Rows"], format_rows)
            + "</div></div></section>"
        )

    domain_rows = [[esc(name), str(count)] for name, count in audit["domain_file_counts"].items()]
    sections.append(
        "<section><h2>Package file inventory</h2>" + html_table(["Domain folder", "Files"], domain_rows) + "</section>"
    )

    evidence = [
        [esc(name), esc(path)]
        for name, path in (
            ("Export manifest", manifest.get("path", "")),
            ("Surfaces report", surfaces.get("report_path", "")),
            ("Seismic report", seismic.get("report_path", "")),
            ("Native semantic report", semantic.get("report_path", "")),
        )
        if path
    ]
    sections.append("<section><h2>Evidence</h2>" + html_table(["Source", "Path"], evidence) + "</section>")

    style = """
    body { font-family: 'Segoe UI', Arial, sans-serif; margin: 0; color: #1c2733; background: #f4f6f8; }
    header { background: #12303f; color: #fff; padding: 24px 32px; }
    header h1 { margin: 0 0 6px 0; font-size: 24px; }
    header p { margin: 2px 0; color: #b8ccd6; font-size: 13px; }
    main { max-width: 1080px; margin: 0 auto; padding: 20px 32px 48px; }
    .tiles { display: flex; flex-wrap: wrap; gap: 12px; margin: 20px 0; }
    .tile { background: #fff; border: 1px solid #dbe3e8; border-radius: 8px; padding: 14px 20px; min-width: 130px; }
    .tile-value { font-size: 26px; font-weight: 600; color: #12303f; }
    .tile-label { font-size: 12px; color: #5b7282; margin-top: 2px; }
    section { background: #fff; border: 1px solid #dbe3e8; border-radius: 8px; padding: 18px 22px; margin: 16px 0; }
    h2 { margin: 0 0 10px 0; font-size: 17px; color: #12303f; }
    h3 { margin: 8px 0; font-size: 14px; color: #12303f; }
    table { border-collapse: collapse; width: 100%; font-size: 13px; }
    th { text-align: left; background: #eef2f5; padding: 6px 10px; border-bottom: 2px solid #dbe3e8; white-space: nowrap; }
    td { padding: 5px 10px; border-bottom: 1px solid #edf1f4; }
    .scroll { overflow-x: auto; }
    .cols { display: flex; flex-wrap: wrap; gap: 20px; }
    .cols > div { flex: 1; min-width: 260px; }
    .note { font-size: 12px; color: #5b7282; }
    ul.qc { margin: 0; padding-left: 18px; font-size: 13px; }
    ul.qc li { margin: 4px 0; }
    ul.qc li.warning strong { color: #b3541e; }
    ul.qc li.info strong { color: #2a6f8f; }
    footer { text-align: center; color: #5b7282; font-size: 12px; padding: 12px; }
    """
    header_lines = [
        f"Project: {esc(project['project_name'] or 'unknown')} | Petrel version: {esc(project['petrel_version'] or 'unknown')}",
        f"Export package: {esc(audit['export_package'])}",
        f"Generated {esc(audit['created_at_utc'])} by report_petrel_project_audit.py v{TOOL_VERSION} - zero-GUI, Petrel was not launched.",
    ]
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<title>{esc(title)}</title><style>{style}</style></head><body>"
        f"<header><h1>{esc(title)}</h1>" + "".join(f"<p>{line}</p>" for line in header_lines) + "</header>"
        f"<main><div class='tiles'>{''.join(tiles)}</div>{''.join(sections)}</main>"
        "<footer>Produced from exported evidence files only. No Petrel process or license was used.</footer>"
        "</body></html>"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Zero-GUI Petrel project audit report")
    parser.add_argument("--export-package", required=True, help="Export package root directory")
    parser.add_argument("--output-dir", default="", help="Output directory (default: <package>/07_workflows_reports/project_audit)")
    parser.add_argument("--title", default="", help="Report title (default: 'Petrel Project Audit - <project>')")
    args = parser.parse_args()

    package = Path(args.export_package)
    if not package.is_dir():
        print("SummaryJson:" + json.dumps({"status": "failed", "error": f"export package not found: {package}"}))
        return 1

    audit: dict = {
        "operation": "project_audit_report",
        "tool_version": TOOL_VERSION,
        "created_at_utc": utc_iso(),
        "export_package": str(package),
        "runtime_gui_used": False,
        "petrel_process_launched": False,
        "project": gather_project_summary(package),
        "manifest": gather_manifest(package),
        "wells": gather_wells(package),
        "well_tops": gather_well_tops(package),
        "surfaces": gather_surfaces(package),
        "seismic": gather_seismic(package),
        "native_semantic": gather_native_semantic(package),
        "domain_file_counts": gather_domain_files(package),
    }
    audit["qc_flags"] = build_qc_flags(audit)

    title = args.title or f"Petrel Project Audit - {audit['project']['project_name'] or package.name}"
    output_dir = Path(args.output_dir) if args.output_dir else package / "07_workflows_reports" / "project_audit"
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = utc_stamp()
    html_path = output_dir / f"petrel_project_audit_{stamp}.html"
    json_path = output_dir / f"petrel_project_audit_{stamp}.json"
    html_path.write_text(render_html(audit, title), encoding="utf-8")
    json_path.write_text(json.dumps(audit, indent=2), encoding="utf-8")

    warnings = sum(1 for flag in audit["qc_flags"] if flag["severity"] == "warning")
    summary = {
        "status": "passed",
        "html_report": str(html_path),
        "json_report": str(json_path),
        "project_name": audit["project"]["project_name"],
        "petrel_version": audit["project"]["petrel_version"],
        "manifest_rows": audit["manifest"]["row_count"],
        "wells": audit["wells"]["well_count"] if audit["wells"]["available"] else 0,
        "well_top_picks": audit["well_tops"]["pick_count"] if audit["well_tops"]["available"] else 0,
        "surfaces_exported": audit["surfaces"]["summary"].get("exported", 0) if audit["surfaces"]["available"] else 0,
        "seismic_cubes": audit["seismic"]["cube_count"] if audit["seismic"]["available"] else 0,
        "qc_warnings": warnings,
        "qc_flags": len(audit["qc_flags"]),
        "runtime_gui_used": False,
        "petrel_process_launched": False,
    }
    print("Report:" + str(json_path))
    print("SummaryJson:" + json.dumps(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
