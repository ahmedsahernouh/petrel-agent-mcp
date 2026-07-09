#!/usr/bin/env python3
"""Convert a Petrel-exported LAS well log file to CSV with a JSON summary.

Chain tool: LAS files exported from Petrel (02_wells/well_logs_las) become
plain CSV (depth + curve columns) for external processing. Uses lasio.

Prints "SummaryJson:{...}" for MCP parsing.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    import lasio

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--input", required=True, help="LAS file path")
    ap.add_argument("--output", required=True, help="CSV output path")
    args = ap.parse_args()

    src, dst = Path(args.input), Path(args.output)
    if not src.exists():
        print(f"ERROR: LAS file not found: {src}", file=sys.stderr)
        return 2

    las = lasio.read(str(src))
    frame = las.df().reset_index()  # index is the depth/index curve
    dst.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(dst, index=False, float_format="%.4f")

    well = {item.mnemonic: str(item.value) for item in las.well}
    summary = {
        "operation": "convert_petrel_las",
        "status": "passed",
        "input": str(src),
        "output": str(dst),
        "well_name": well.get("WELL"),
        "curves": [c.mnemonic for c in las.curves],
        "curve_units": {c.mnemonic: c.unit for c in las.curves},
        "rows": int(len(frame)),
        "index_range": [float(frame.iloc[0, 0]), float(frame.iloc[-1, 0])] if len(frame) else None,
        "null_value": float(las.well.NULL.value) if "NULL" in well else None,
        "output_bytes": dst.stat().st_size,
    }
    print("SummaryJson:" + json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
