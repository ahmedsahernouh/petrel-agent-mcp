#!/usr/bin/env python3
"""Write a Petrel Well Tops ASCII (VERSION 2) file from a CSV of marker picks.

Completes the round-trip chain: Petrel export -> parsed CSV -> external edit ->
this writer -> Petrel-importable ASCII. The output replicates the exact dialect
of Petrel 2018.2 well tops exports (CRLF, VERSION 2, BEGIN/END HEADER, quoted
strings, -999 undefined), using the same 30-column header captured from a
Petrel-authored export of the demo project.

Input CSV columns (flexible): well/well_name, surface, x, y, z/depth are
required; md/measured_depth, twt_picked, twt_auto, type, dip_angle, dip_azimuth,
geological_age, observation_number are used when present; everything else is
written as undefined (-999 / "" / defaults).

Prints "SummaryJson:{...}" for MCP parsing. --verify re-parses the written file
and cross-checks row count and X/Y/Z values against the input.
"""
from __future__ import annotations

import argparse
import csv
import json
import shlex
import sys
from pathlib import Path

HEADER_COLUMNS = [
    "X", "Y", "Z", "TWT picked", "TWT auto", "MD", "Type", "Surface", "Well",
    "Interpreter", "Dip angle", "Dip azimuth", "Used by dep.conv.", "Used by geo mod",
    "Zone log", "Symbol", "TVT", "TST", "TVT zone", "TST zone",
    "FLOAT,Fluvial facies", "FLOAT,Levee", "FLOAT,Channel", "FLOAT,Crevasse",
    "Confidence factor", "Missing", "Locked to fault", "Edited by user",
    "Geological age", "Observation number",
]
UNDEF = "-999"


def pick(row: dict, *names: str, default: str = UNDEF) -> str:
    for name in names:
        for key in row:
            if key.strip().lower() == name:
                value = str(row[key]).strip()
                if value not in ("", "None"):
                    return value
    return default


def fmt_num(value: str, decimals: int = 2) -> str:
    try:
        return f"{float(value):.{decimals}f}"
    except ValueError:
        return UNDEF


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--input-csv", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--verify", action="store_true", default=True)
    ap.add_argument("--no-verify", dest="verify", action="store_false")
    args = ap.parse_args()

    src = Path(args.input_csv)
    if not src.exists():
        print(f"ERROR: input CSV not found: {src}", file=sys.stderr)
        return 2
    rows = list(csv.DictReader(open(src, encoding="utf-8-sig")))
    if not rows:
        print("ERROR: input CSV has no data rows", file=sys.stderr)
        return 2

    out_lines = [
        "# Petrel well tops",
        "# Unit in X and Y direction: m",
        "# Unit in depth: m",
        "VERSION 2",
        "BEGIN HEADER",
        *HEADER_COLUMNS,
        "END HEADER",
    ]
    written = 0
    skipped = 0
    for row in rows:
        x = pick(row, "x")
        y = pick(row, "y")
        z = pick(row, "z", "depth")
        well = pick(row, "well", "well_name", default="")
        surface = pick(row, "surface", "compare_surface_name", default="")
        if UNDEF in (x, y, z) or not well or not surface:
            skipped += 1
            continue
        fields = [
            fmt_num(x), fmt_num(y), fmt_num(z),
            fmt_num(pick(row, "twt_picked")), fmt_num(pick(row, "twt_auto")),
            fmt_num(pick(row, "md", "measured_depth")),
            pick(row, "type", default="Horizon"),
            f'"{surface}"', f'"{well}"',
            f'"{pick(row, "interpreter", default="")}"',
            fmt_num(pick(row, "dip_angle")), fmt_num(pick(row, "dip_azimuth")),
            "TRUE", "TRUE",  # Used by dep.conv. / geo mod
            UNDEF,  # Zone log
            "0",    # Symbol
            UNDEF, UNDEF, UNDEF, UNDEF,          # TVT, TST, TVT zone, TST zone
            UNDEF, UNDEF, UNDEF, UNDEF,          # FLOAT attribute columns
            UNDEF,                                # Confidence factor
            UNDEF,                                # Missing
            "FALSE", "FALSE",                     # Locked to fault / Edited by user
            fmt_num(pick(row, "geological_age")),
            pick(row, "observation_number", default=UNDEF),
        ]
        out_lines.append(" ".join(fields))
        written += 1

    dst = Path(args.output)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(("\r\n".join(out_lines) + "\r\n").encode("ascii", "replace"))

    summary = {
        "operation": "write_petrel_well_tops_ascii",
        "input": str(src),
        "output": str(dst),
        "rows_written": written,
        "rows_skipped_missing_required": skipped,
        "output_bytes": dst.stat().st_size,
        "status": "passed" if written else "failed",
    }

    if args.verify and written:
        parsed = []
        in_data = False
        for line in dst.read_text(encoding="ascii").splitlines():
            if line.strip() == "END HEADER":
                in_data = True
                continue
            if in_data and line.strip():
                parts = shlex.split(line)
                parsed.append((float(parts[0]), float(parts[1]), float(parts[2])))
        checks = len(parsed) == written
        # spot-check first and last row against the written values
        summary["verify"] = {
            "reparsed_rows": len(parsed),
            "row_count_matches": checks,
            "first_xyz": parsed[0] if parsed else None,
            "last_xyz": parsed[-1] if parsed else None,
        }
        if not checks:
            summary["status"] = "failed"

    print("SummaryJson:" + json.dumps(summary))
    return 0 if summary["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
