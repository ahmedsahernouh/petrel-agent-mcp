#!/usr/bin/env python3
"""Zero-GUI Petrel seismic export from native ZGY cubes.

Tier-1 (zero_gui_python) exporter. ZGY is SLB's open seismic format; this script
reads the ZGY cubes inside the copied native project store with pyzgy (no Petrel,
no GUI, no donor commands), writes per-cube geometry/statistics reports, exports
orthogonal mid-slices as .npy arrays (small, evidence-grade), and optionally the
full decompressed volume as .npy with a JSON geometry sidecar for the
extract -> process externally chain.

The cube annotation grid (inline/xline ranges) ties directly to the survey
transform reported by petrel_survey_geometry, which georeferences every trace.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXPORT_PACKAGE = REPO_ROOT / "build" / "export_pilots" / "petrel2010_demo_project_export_20260701_060609"


def cube_report(f, path: Path) -> dict:
    ilines = np.asarray(f.ilines)
    xlines = np.asarray(f.xlines)
    samples = np.asarray(f.samples)
    # Decimated amplitude statistics: every 8th inline keeps this fast and
    # representative without decompressing the whole volume twice.
    mins, maxs, sums, sqs, count = [], [], 0.0, 0.0, 0
    for il in ilines[::8]:
        block = np.asarray(f.iline[int(il)], dtype=np.float64)
        mins.append(float(block.min()))
        maxs.append(float(block.max()))
        sums += float(block.sum())
        sqs += float((block * block).sum())
        count += block.size
    mean = sums / count
    rms = (sqs / count) ** 0.5
    return {
        "zgy_file": str(path),
        "zgy_bytes": path.stat().st_size,
        "inline_range": [int(ilines[0]), int(ilines[-1])],
        "inline_count": int(len(ilines)),
        "inline_step": int(ilines[1] - ilines[0]) if len(ilines) > 1 else None,
        "xline_range": [int(xlines[0]), int(xlines[-1])],
        "xline_count": int(len(xlines)),
        "xline_step": int(xlines[1] - xlines[0]) if len(xlines) > 1 else None,
        "sample_range": [float(samples[0]), float(samples[-1])],
        "sample_count": int(len(samples)),
        "sample_step": float(samples[1] - samples[0]) if len(samples) > 1 else None,
        "amplitude_stats_decimated": {
            "every_nth_inline": 8,
            "min": min(mins),
            "max": max(maxs),
            "mean": mean,
            "rms": rms,
        },
        "georeference_note": "Inline/xline annotations match the seismic survey grid; use petrel_survey_geometry (SEG-Y donor trace headers) for the world transform.",
    }


def export_slices(f, out_dir: Path, gid: str) -> list[dict]:
    ilines, xlines, samples = f.ilines, f.xlines, f.samples
    out_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    mid_il = int(ilines[len(ilines) // 2])
    mid_xl = int(xlines[len(xlines) // 2])
    mid_z = len(samples) // 2
    slabs = {
        f"{gid}_inline_{mid_il}.npy": np.asarray(f.iline[mid_il], dtype=np.float32),
        f"{gid}_xline_{mid_xl}.npy": np.asarray(f.xline[mid_xl], dtype=np.float32),
        f"{gid}_zslice_{mid_z}.npy": np.asarray(f.depth_slice[mid_z], dtype=np.float32),
    }
    for name, arr in slabs.items():
        target = out_dir / name
        np.save(target, arr)
        entries.append({"file": str(target), "shape": list(arr.shape), "bytes": target.stat().st_size})
    return entries


def export_volume(f, out_dir: Path, gid: str) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    ilines = f.ilines
    volume = np.stack([np.asarray(f.iline[int(il)], dtype=np.float32) for il in ilines])
    target = out_dir / f"{gid}_volume.npy"
    np.save(target, volume)
    sidecar = {
        "axes": ["inline", "xline", "sample"],
        "inline_annotations": [int(v) for v in f.ilines],
        "xline_annotations_range": [int(f.xlines[0]), int(f.xlines[-1])],
        "sample_annotations_range": [float(f.samples[0]), float(f.samples[-1])],
        "dtype": "float32",
        "shape": list(volume.shape),
    }
    sidecar_path = out_dir / f"{gid}_volume.json"
    sidecar_path.write_text(json.dumps(sidecar, indent=2), encoding="utf-8")
    return {"file": str(target), "shape": list(volume.shape), "bytes": target.stat().st_size, "sidecar": str(sidecar_path)}


def main() -> int:
    import pyzgy

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--export-package", default=str(DEFAULT_EXPORT_PACKAGE))
    ap.add_argument("--store-subdir", default="08_native_project/ptd_store")
    ap.add_argument("--out-subdir", default="03_seismic/zgy_arrays")
    ap.add_argument("--export-volume", action="store_true", help="Also export the full decompressed volume as .npy (~100 MB per cube).")
    ap.add_argument("--no-slices", action="store_true")
    args = ap.parse_args()

    pkg = Path(args.export_package)
    store = pkg / args.store_subdir
    if not store.exists():
        print(f"ERROR: native store not found: {store}", file=sys.stderr)
        return 2

    report = {
        "operation": "export_seismic_zgy_zero_gui",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "runtime_gui_used": False,
        "petrel_process_launched": False,
        "export_package": str(pkg),
        "cubes": [],
    }
    out_root = pkg / args.out_subdir
    for zgy_path in sorted(glob.glob(str(store / "*.zgy"))):
        path = Path(zgy_path)
        gid = path.stem[:8]
        entry: dict = {"guid": path.stem}
        try:
            with pyzgy.open(str(path)) as f:
                entry.update(cube_report(f, path))
                if not args.no_slices:
                    entry["slices"] = export_slices(f, out_root / path.stem, gid)
                if args.export_volume:
                    entry["volume"] = export_volume(f, out_root / path.stem, gid)
            entry["status"] = "exported"
        except Exception as exc:
            entry["status"] = "failed"
            entry["error"] = f"{type(exc).__name__}: {exc}"
        report["cubes"].append(entry)

    exported = [c for c in report["cubes"] if c["status"] == "exported"]
    report["summary"] = {
        "total": len(report["cubes"]),
        "exported": len(exported),
        "status": "passed" if exported and len(exported) == len(report["cubes"]) else ("partial" if exported else "failed"),
    }
    report_dir = pkg / "07_workflows_reports" / "seismic_zgy_export"
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = report_dir / f"seismic_zgy_export_{stamp}.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"ZGY zero-GUI export: {report['summary']['status']}")
    for c in report["cubes"]:
        if c["status"] == "exported":
            st = c["amplitude_stats_decimated"]
            print(f"  {c['guid'][:8]}: {c['inline_count']}x{c['xline_count']}x{c['sample_count']}  samples {c['sample_range'][0]:.0f}-{c['sample_range'][1]:.0f}  amp[{st['min']:.0f},{st['max']:.0f}] rms={st['rms']:.1f}")
        else:
            print(f"  {c['guid'][:8]}: FAILED {c.get('error','')[:80]}")
    print(f"Report: {report_path}")
    return 0 if report["summary"]["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
