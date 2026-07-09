#!/usr/bin/env python3
"""Convert gridded surface files between ZMAP+ .dat and XYZ CSV.

Chain tool for the extract -> process externally -> (re)import route: pairs with
export_petrel_surfaces_zero_gui.py, using the operator's zmapio conventions
(null 1.0E+30, 5 nodes/line, 4 decimals, field width 40) and the empirically
verified zmapio axis convention (z_values axis0 = X columns, axis1 = Y
descending). XYZ CSV is x,y,z with a header row; ZMAP round-trips only for
regular, axis-aligned grids - irregular scatter fails closed.

Prints a single-line JSON summary prefixed with "SummaryJson:" for MCP parsing.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

ZMAP_NULL = 1.0e30


def read_zmap(path: Path):
    from zmapio import ZMAPGrid

    g = ZMAPGrid(str(path))
    z = np.asarray(g.z_values, dtype=float)  # [x][y descending]
    z = np.where(z >= 1e29, np.nan, z)
    grid = z.T[::-1, :]  # -> [y ascending][x]
    ny, nx = grid.shape
    xs = np.linspace(float(g.min_x), float(g.max_x), nx)
    ys = np.linspace(float(g.min_y), float(g.max_y), ny)
    return xs, ys, grid


def write_zmap(path: Path, xs: np.ndarray, ys: np.ndarray, grid: np.ndarray, name: str):
    from zmapio import ZMAPGrid

    z = np.where(np.isnan(grid), ZMAP_NULL, grid)
    zg = ZMAPGrid(z_values=z[::-1, :].T, min_x=float(xs.min()), max_x=float(xs.max()),
                  min_y=float(ys.min()), max_y=float(ys.max()))
    zg.comments = [f"Converted by convert_petrel_grid.py from {name}"]
    zg.nodes_per_line = 5
    zg.field_width = 40
    zg.decimal_places = 4
    zg.null_value = ZMAP_NULL
    zg.name = name
    zg.write(str(path))


def read_xyz_csv(path: Path):
    xs_raw, ys_raw, zs_raw = [], [], []
    with open(path, newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        if not any(h.strip().lower() in ("x", "easting") for h in header):
            # no header; treat first row as data
            f.seek(0)
            reader = csv.reader(f)
        for row in reader:
            if len(row) < 3:
                continue
            try:
                xs_raw.append(float(row[0])); ys_raw.append(float(row[1])); zs_raw.append(float(row[2]))
            except ValueError:
                continue
    xs_u = np.unique(np.round(np.asarray(xs_raw), 4))
    ys_u = np.unique(np.round(np.asarray(ys_raw), 4))
    if len(xs_u) < 2 or len(ys_u) < 2:
        raise SystemExit("irregular_grid: fewer than 2 unique x or y values")
    # Regularity gate: spacing must be uniform within tolerance, and the point
    # count must be consistent with a (possibly sparse) regular lattice.
    for label, u in (("x", xs_u), ("y", ys_u)):
        d = np.diff(u)
        if d.max() - d.min() > max(1e-3, d.min() * 0.01):
            raise SystemExit(f"irregular_grid: non-uniform {label} spacing (min {d.min():.4f}, max {d.max():.4f}); ZMAP requires a regular axis-aligned lattice")
    grid = np.full((len(ys_u), len(xs_u)), np.nan)
    xi = {v: i for i, v in enumerate(xs_u)}
    yi = {v: i for i, v in enumerate(ys_u)}
    for x, y, z in zip(xs_raw, ys_raw, zs_raw):
        grid[yi[round(y, 4)], xi[round(x, 4)]] = z
    return xs_u, ys_u, grid


def write_xyz_csv(path: Path, xs: np.ndarray, ys: np.ndarray, grid: np.ndarray):
    live = 0
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["x", "y", "z"])
        for j, y in enumerate(ys):
            for i, x in enumerate(xs):
                v = grid[j, i]
                if v == v:
                    w.writerow([f"{x:.2f}", f"{y:.2f}", f"{v:.3f}"])
                    live += 1
    return live


def infer_format(path: Path, explicit: str | None) -> str:
    if explicit:
        return explicit
    suffix = path.suffix.lower()
    if suffix in (".dat", ".zmap"):
        return "zmap"
    if suffix in (".csv", ".xyz", ".txt"):
        return "xyz_csv"
    raise SystemExit(f"cannot infer format from extension '{suffix}'; pass --input-format/--output-format")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--input-format", choices=["zmap", "xyz_csv"])
    ap.add_argument("--output-format", choices=["zmap", "xyz_csv"])
    args = ap.parse_args()

    src, dst = Path(args.input), Path(args.output)
    if not src.exists():
        print(f"ERROR: input not found: {src}", file=sys.stderr)
        return 2
    in_fmt = infer_format(src, args.input_format)
    out_fmt = infer_format(dst, args.output_format)

    xs, ys, grid = read_zmap(src) if in_fmt == "zmap" else read_xyz_csv(src)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if out_fmt == "zmap":
        write_zmap(dst, xs, ys, grid, dst.stem)
        live = int(np.isfinite(grid).sum())
    else:
        live = write_xyz_csv(dst, xs, ys, grid)

    finite = grid[np.isfinite(grid)]
    summary = {
        "operation": "convert_petrel_grid",
        "status": "passed",
        "input": str(src), "input_format": in_fmt,
        "output": str(dst), "output_format": out_fmt,
        "nx": int(grid.shape[1]), "ny": int(grid.shape[0]),
        "live_nodes": live,
        "z_min": float(finite.min()) if finite.size else None,
        "z_max": float(finite.max()) if finite.size else None,
        "x_range": [float(xs.min()), float(xs.max())],
        "y_range": [float(ys.min()), float(ys.max())],
        "output_bytes": dst.stat().st_size,
    }
    print("SummaryJson:" + json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
