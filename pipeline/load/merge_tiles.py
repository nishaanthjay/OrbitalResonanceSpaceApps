"""Merge load_big.py tiles (a grid of 100 m block stacks) into ONE stack with the same structure.

  python merge_tiles.py --tiles-dir ../../data/tiles_frame --out ../../data/stack_frame_t2f174.nc --tile frame_t2f174

Tiles are laid out by their x / y coordinates; refuses if dates differ, spacing is not uniform, or tiles leave a gap /
overlap (every row of tiles must abut exactly, every column too, and the result must be a full rectangle).
"""
from __future__ import annotations

import argparse
import glob
import os

import numpy as np
import xarray as xr

KEEP = ("crs", "multilook", "track", "frame", "direction", "mode", "product", "granules", "layers",
        "native_spacing_m", "note")


def merge(dss: list[xr.Dataset], tile: str) -> xr.Dataset:
    t0 = dss[0]
    step = float(t0.attrs["pixel_spacing_m"])
    for d in dss:
        if not np.array_equal(d.time.values, t0.time.values):
            raise ValueError("tile dates differ")
        for k in ("crs", "multilook", "granules"):
            if d.attrs[k] != t0.attrs[k]:
                raise ValueError(f"tile attr {k} differs")
        if not (np.allclose(np.diff(d.x), step) and np.allclose(-np.diff(d.y), step)):
            raise ValueError("tile spacing is not the block size")
    xs = sorted({float(d.x[0]) for d in dss})
    ys = sorted({float(d.y[0]) for d in dss}, reverse=True)  # top row first
    if len(xs) * len(ys) != len(dss):
        raise ValueError("tiles do not form a full grid")
    rows = []
    for yt in ys:
        row = sorted((d for d in dss if float(d.y[0]) == yt), key=lambda d: float(d.x[0]))
        for a, b in zip(row, row[1:]):
            if not np.isclose(float(b.x[0]) - float(a.x[-1]), step, atol=1e-6):
                raise ValueError("gap or overlap in x between tiles")
        if len({d.sizes["y"] for d in row}) != 1 or not all(np.array_equal(d.y, row[0].y) for d in row):
            raise ValueError("tiles of one row differ in y")
        rows.append(row)
    for a, b in zip(rows, rows[1:]):
        if not np.isclose(float(a[0].y[-1]) - float(b[0].y[0]), step, atol=1e-6):
            raise ValueError("gap or overlap in y between tiles")
        if not all(np.array_equal(p.x, q.x) for p, q in zip(a, b)):
            raise ValueError("tile columns differ in x")
    out = xr.concat([xr.concat(r, "x") for r in rows], "y")
    out.attrs = {k: t0.attrs[k] for k in KEEP if k in t0.attrs}
    out.attrs["tile"] = tile
    out.attrs["pixel_spacing_m"] = step
    h = float(out.attrs["native_spacing_m"]) * (int(out.attrs["multilook"]) - 1) / 2  # block centre -> first pixel centre
    out.attrs["window_first_pixel_xy"] = [float(out.x[0]) - h, float(out.y[0]) + h]
    out.attrs["window_pixels_nx_ny"] = [out.sizes["x"] * int(out.attrs["multilook"]), out.sizes["y"] * int(out.attrs["multilook"])]
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--tiles-dir", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--tile", default="frame_t2f174")
    a = p.parse_args()
    dss = [xr.load_dataset(f) for f in sorted(glob.glob(os.path.join(a.tiles_dir, "stack_*.nc")))]
    out = merge(dss, a.tile)
    out.to_netcdf(a.out, encoding={v: {"zlib": True, "complevel": 4} for v in ("hh_db", "hv_db")})
    print(a.out, dict(out.sizes))


if __name__ == "__main__":
    main()
