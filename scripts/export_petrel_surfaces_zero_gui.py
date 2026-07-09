#!/usr/bin/env python3
"""Zero-GUI Petrel surface export: decode native .zhz 2D arrays to XYZ CSV and ZMAP+.

Tier-1 (zero_gui_python) exporter. Reads the copied native project store inside an
export package, decodes SLB-PETRELSERVER-3.2-ARRAY2DFILE surface grids plus their
u8 validity masks, georeferences them with the seismic survey transform taken from
a Petrel-authored SEG-Y export, validates each decode against the mask footprint
(fail-closed per file), cross-checks depth grids against parsed well-top picks,
and writes XYZ CSV (exact node coordinates) plus ZMAP+ .dat (axis-aligned resample
using the operator's zmapio conventions).

Evidence contract (2026-07-08):
- Data layout: 64 KiB blocks; block 0 header; 128x128 float32 tiles row-major.
- Mask layout: block 0 header; 256x256 uint8 tiles row-major; nonzero = defined.
- A file is exported only when data/mask footprint agreement >= 99.9%. The two
  known 10-block variants (28fe5a0a*, b6c0e07e*) fail this gate and are reported
  as layout_unresolved instead of being exported wrong.
- Survey transform derived from SEG-Y trace headers (inline/xline/X/Y), validated
  against well tops: T_Tarbert grid matched picks at RMS ~11 m.
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import math
import os
import struct
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

BLOCK = 65536
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXPORT_PACKAGE = REPO_ROOT / "build" / "export_pilots" / "petrel2010_demo_project_export_20260701_060609"
AGREEMENT_GATE = 0.999
ZMAP_NULL = 1.0e30


def read_header(raw: bytes) -> dict:
    magic = raw[:70].split(b"\x00")[0].decode("ascii", "replace")
    elem = struct.unpack_from("<I", raw, 130)[0]
    tx, ty = struct.unpack_from("<II", raw, 134)
    nx, ny = struct.unpack_from("<II", raw, 174)
    return {"magic": magic, "elem": elem, "tile": (tx, ty), "dims": (nx, ny)}


def decode_tiled(raw: bytes, nx: int, ny: int, tx: int, ty: int, fmt: str, start_block: int = 1):
    esz = struct.calcsize(fmt)
    tiles_x, tiles_y = math.ceil(nx / tx), math.ceil(ny / ty)
    need = BLOCK * start_block + tiles_x * tiles_y * tx * ty * esz
    if need > len(raw) + BLOCK:  # trailing block may be footer; tiles themselves must fit
        return None
    dt = np.dtype("<f4") if fmt == "f" else np.dtype("<u1")
    grid = np.full((ny, nx), np.nan if fmt == "f" else 0, dtype=np.float64 if fmt == "f" else np.uint8)
    for t in range(tiles_x * tiles_y):
        tj, ti = divmod(t, tiles_x)
        off = BLOCK * start_block + t * tx * ty * esz
        if off + tx * ty * esz > len(raw):
            return None
        tile = np.frombuffer(raw, dtype=dt, count=tx * ty, offset=off).reshape(ty, tx)
        y0, x0 = tj * ty, ti * tx
        y1, x1 = min(y0 + ty, ny), min(x0 + tx, nx)
        grid[y0:y1, x0:x1] = tile[: y1 - y0, : x1 - x0]
    return grid


def survey_transform(segy_path: Path) -> dict:
    """Derive origin and inline/xline unit vectors from SEG-Y trace headers."""
    with open(segy_path, "rb") as f:
        f.seek(3220)
        ns = struct.unpack(">H", f.read(2))[0]
        trace_len = 240 + ns * 4
        size = segy_path.stat().st_size
        ntraces = (size - 3600) // trace_len

        def hdr(i):
            f.seek(3600 + i * trace_len)
            h = f.read(240)
            g4 = lambda pos: struct.unpack_from(">i", h, pos - 1)[0]
            return g4(189), g4(193), g4(181), g4(185)

        il0, xl0, x0, y0 = hdr(0)
        # find xlines-per-inline by scanning for the first inline change
        per_inline = None
        for i in range(1, min(ntraces, 2000)):
            il, _, _, _ = hdr(i)
            if il != il0:
                per_inline = i
                break
        if per_inline is None:
            raise SystemExit("Could not determine xlines per inline from SEG-Y")
        il1, xl1, x1, y1 = hdr(per_inline - 1)          # end of first inline
        il2, xl2, x2, y2 = hdr((ntraces // per_inline - 1) * per_inline)  # first trace of last inline
    xlv = ((x1 - x0) / (xl1 - xl0), (y1 - y0) / (xl1 - xl0))
    ilv = ((x2 - x0) / (il2 - il0), (y2 - y0) / (il2 - il0))
    return {
        "segy": str(segy_path),
        "origin_trace": {"inline": il0, "xline": xl0, "x": float(x0), "y": float(y0)},
        "xline_unit_vector": [float(xlv[0]), float(xlv[1])],
        "inline_unit_vector": [float(ilv[0]), float(ilv[1])],
        "xlines_per_inline": per_inline,
        "ntraces": int(ntraces),
    }


def node_world(tr: dict, i: np.ndarray, j: np.ndarray):
    """Grid indices -> world coordinates. Cell-center convention validated vs picks:
    node(i, j) sits at origin + xline_unit*(2i+1) + inline_unit*(2j+1)."""
    xlv, ilv = tr["xline_unit_vector"], tr["inline_unit_vector"]
    o = tr["origin_trace"]
    u = 2.0 * i + 1.0
    v = 2.0 * j + 1.0
    x = o["x"] + xlv[0] * u + ilv[0] * v
    y = o["y"] + xlv[1] * u + ilv[1] * v
    return x, y


def load_picks(tops_csv: Path):
    picks = defaultdict(list)
    if not tops_csv.exists():
        return picks
    for r in csv.DictReader(open(tops_csv, encoding="utf-8-sig")):
        if r.get("is_actual_pick_record") != "yes":
            continue
        try:
            x, y, z = float(r["x"]), float(r["y"]), float(r["depth"])
        except (KeyError, ValueError):
            continue
        picks[r["compare_surface_name"].strip()].append((x, y, z))
    return picks


def sample_bilinear(grid: np.ndarray, fx: float, fy: float):
    ny, nx = grid.shape
    if not (0 <= fx <= nx - 1 and 0 <= fy <= ny - 1):
        return None
    i0, j0 = int(fx), int(fy)
    i1, j1 = min(i0 + 1, nx - 1), min(j0 + 1, ny - 1)
    q = np.array([grid[j0, i0], grid[j0, i1], grid[j1, i0], grid[j1, i1]])
    if np.isnan(q).any():
        return None
    wx, wy = fx - i0, fy - j0
    return float((q[0] * (1 - wx) + q[1] * wx) * (1 - wy) + (q[2] * (1 - wx) + q[3] * wx) * wy)


def pick_fit(grid: np.ndarray, tr: dict, picks: dict):
    """Best-fitting pick group for a grid; returns (name, rms, n) or None."""
    xlv, ilv = tr["xline_unit_vector"], tr["inline_unit_vector"]
    o = tr["origin_trace"]
    det = xlv[0] * ilv[1] - xlv[1] * ilv[0]
    best = None
    for name, plist in picks.items():
        errs = []
        for x, y, z in plist:
            dx, dy = x - o["x"], y - o["y"]
            u = (dx * ilv[1] - dy * ilv[0]) / det
            v = (xlv[0] * dy - xlv[1] * dx) / det
            s = sample_bilinear(grid, (u - 1.0) / 2.0, (v - 1.0) / 2.0)
            if s is not None:
                errs.append(s - z)
        if len(errs) >= 5:
            rms = math.sqrt(sum(e * e for e in errs) / len(errs))
            if best is None or rms < best[1]:
                best = (name, rms, len(errs))
    return best


def write_xyz(path: Path, grid: np.ndarray, tr: dict):
    ny, nx = grid.shape
    jj, ii = np.mgrid[0:ny, 0:nx]
    x, y = node_world(tr, ii.astype(float), jj.astype(float))
    live = ~np.isnan(grid)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["x", "y", "z"])
        for xv, yv, zv in zip(x[live], y[live], grid[live]):
            w.writerow([f"{xv:.2f}", f"{yv:.2f}", f"{zv:.3f}"])
    return int(live.sum())


def write_zmap(path: Path, grid: np.ndarray, tr: dict, name: str, cell: float = 12.5):
    """Axis-aligned nearest-node resample written with the operator's zmapio conventions."""
    from zmapio import ZMAPGrid

    ny, nx = grid.shape
    jj, ii = np.mgrid[0:ny, 0:nx]
    x, y = node_world(tr, ii.astype(float), jj.astype(float))
    xmin, xmax, ymin, ymax = x.min(), x.max(), y.min(), y.max()
    gx = np.arange(xmin, xmax + cell / 2, cell)
    gy = np.arange(ymin, ymax + cell / 2, cell)
    out = np.full((len(gy), len(gx)), np.nan)
    # inverse transform: world -> fractional indices (same math as pick sampling)
    xlv, ilv = tr["xline_unit_vector"], tr["inline_unit_vector"]
    o = tr["origin_trace"]
    det = xlv[0] * ilv[1] - xlv[1] * ilv[0]
    GX, GY = np.meshgrid(gx, gy)
    dx, dy = GX - o["x"], GY - o["y"]
    u = (dx * ilv[1] - dy * ilv[0]) / det
    v = (xlv[0] * dy - xlv[1] * dx) / det
    fi = np.rint((u - 1.0) / 2.0).astype(int)
    fj = np.rint((v - 1.0) / 2.0).astype(int)
    ok = (fi >= 0) & (fi < nx) & (fj >= 0) & (fj < ny)
    out[ok] = grid[fj[ok], fi[ok]]
    z = np.where(np.isnan(out), ZMAP_NULL, out)
    # zmapio z_values convention (probed empirically): axis0 = X columns, axis1 = Y
    # scanning ymax -> ymin, so flip the ascending-y rows before transposing.
    zg = ZMAPGrid(z_values=z[::-1, :].T, min_x=float(xmin), max_x=float(xmax), min_y=float(ymin), max_y=float(ymax))
    zg.comments = [
        f"Exported by export_petrel_surfaces_zero_gui.py from native .zhz {name}",
        "Axis-aligned nearest-node resample of survey-rotated lattice (~-0.8 deg)",
        "Exact node coordinates are in the sibling xyz_ascii CSV export",
    ]
    zg.nodes_per_line = 5
    # 40 (not the notebook's 30): the 1e30 null renders as 36 fixed-point chars at
    # 4 decimals, and a narrower field fuses adjacent numbers into unparseable runs.
    zg.field_width = 40
    zg.decimal_places = 4
    zg.null_value = ZMAP_NULL
    zg.name = name
    zg.write(str(path))
    return out.shape


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--export-package", default=str(DEFAULT_EXPORT_PACKAGE))
    ap.add_argument("--store-subdir", default="08_native_project/ptd_store")
    ap.add_argument("--segy", default="03_seismic/segy/orig_amp_exportpilot_donor.sgy")
    ap.add_argument("--tops-csv", default="02_wells/well_tops/well_tops_from_petrel_ascii_export.csv")
    ap.add_argument("--out-subdir", default="04_surfaces_maps")
    args = ap.parse_args()

    pkg = Path(args.export_package)
    store = pkg / args.store_subdir
    if not store.exists():
        print(f"ERROR: native store not found: {store}", file=sys.stderr)
        return 2

    tr = survey_transform(pkg / args.segy)
    picks = load_picks(pkg / args.tops_csv)

    out_xyz = pkg / args.out_subdir / "xyz_ascii"
    out_zmap = pkg / args.out_subdir / "zmap_dat"
    out_xyz.mkdir(parents=True, exist_ok=True)
    out_zmap.mkdir(parents=True, exist_ok=True)

    report = {
        "operation": "export_petrel_surfaces_zero_gui",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "runtime_gui_used": False,
        "petrel_process_launched": False,
        "export_package": str(pkg),
        "survey_transform": tr,
        "agreement_gate": AGREEMENT_GATE,
        "surfaces": [],
    }

    for zhz in sorted(glob.glob(str(store / "*.zhz"))):
        gid = os.path.basename(zhz)[:-4]
        raw = open(zhz, "rb").read()
        hdr = read_header(raw)
        nx, ny = hdr["dims"]
        tx, ty = hdr["tile"]
        entry = {"guid": gid, "dims": [nx, ny], "data_bytes": len(raw)}
        grid = decode_tiled(raw, nx, ny, tx, ty, "f")
        msk_path = zhz + "_msk"
        mask = None
        if os.path.exists(msk_path):
            mraw = open(msk_path, "rb").read()
            mh = read_header(mraw)
            mask = decode_tiled(mraw, nx, ny, mh["tile"][0], mh["tile"][1], "B")
        if grid is None or mask is None:
            entry["status"] = "decode_failed"
            report["surfaces"].append(entry)
            continue
        agreement = float((( ~np.isnan(grid)) == (mask > 0)).mean())
        entry["mask_agreement"] = round(agreement, 6)
        if agreement < AGREEMENT_GATE:
            entry["status"] = "layout_unresolved"
            entry["note"] = "data/mask footprint mismatch; not exported to avoid wrong geometry"
            report["surfaces"].append(entry)
            continue

        fit = pick_fit(grid, tr, picks)
        if fit:
            entry["well_tops_best_fit"] = {"surface": fit[0], "rms_m": round(fit[1], 2), "n_picks": fit[2]}

        stem = f"surface_{gid[:8]}"
        n_nodes = write_xyz(out_xyz / f"{stem}.csv", grid, tr)
        write_zmap(out_zmap / f"{stem}.dat", grid, tr, stem)
        entry["status"] = "exported"
        entry["live_nodes"] = n_nodes
        entry["xyz_csv"] = str(out_xyz / f"{stem}.csv")
        entry["zmap_dat"] = str(out_zmap / f"{stem}.dat")
        entry["z_min"] = float(np.nanmin(grid))
        entry["z_max"] = float(np.nanmax(grid))
        report["surfaces"].append(entry)

    exported = [s for s in report["surfaces"] if s["status"] == "exported"]
    unresolved = [s for s in report["surfaces"] if s["status"] == "layout_unresolved"]
    report["summary"] = {
        "total": len(report["surfaces"]),
        "exported": len(exported),
        "layout_unresolved": len(unresolved),
        "status": "passed" if exported else "failed",
    }
    report_dir = pkg / "07_workflows_reports" / "surfaces_export"
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = report_dir / f"surfaces_zero_gui_export_{stamp}.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"Surfaces zero-GUI export: {report['summary']['status']}")
    print(f"Exported: {len(exported)}/{len(report['surfaces'])} (layout_unresolved: {len(unresolved)})")
    for s in exported:
        fitxt = ""
        if "well_tops_best_fit" in s:
            f = s["well_tops_best_fit"]
            fitxt = f"  picks-fit ~{f['surface']} rms={f['rms_m']}m (n={f['n_picks']})"
        print(f"  {s['guid'][:8]}: {s['live_nodes']} nodes  z=({s['z_min']:.1f},{s['z_max']:.1f}){fitxt}")
    print(f"Report: {report_path}")
    return 0 if exported else 1


if __name__ == "__main__":
    raise SystemExit(main())
