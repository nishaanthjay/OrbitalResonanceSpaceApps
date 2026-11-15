"""Stream a large NISAR GCOV window, block-averaged while streaming (validation/PREREG_scale.md).

Reads frequencyA HHHH / HVHV (20 m) in row strips, averages non-overlapping n x n blocks in linear power (NaN and
values <= load.MIN_VALID_POWER skipped, i.e. the same as detect.multilook), and writes a CONTRACTS.md section 1
style stack whose pixels are the blocks: dims (time, y, x), hh_db / hv_db float32 dB, x / y = block centres,
attrs["crs"], attrs["multilook"] = n (already applied: run detect / fnf on it with n = 1).

The window is given in grid coordinates (first pixel centre x0 / y0, size in pixels), so blocks can be aligned with
another stack's blocks. Every date must have the same grid; it refuses otherwise.

  python pipeline/load/load_big.py --x0 62370 --y0 9121770 --nx 3000 --ny 3000 --block 5 \
    --start 2026-06-20 --end 2026-10-20 --track 2 --frame 174 --direction ASCENDING --mode 20+5 \
    --tile big_t2f174 --out-dir data
"""
from __future__ import annotations

import argparse
import os
import time
import warnings

import numpy as np
import xarray as xr

import load

STRIP_ROWS = 1000  # rows per read; must be a multiple of the block size


def block_mean_linear(p: np.ndarray, n: int) -> np.ndarray:
    """Mean of non-overlapping n x n blocks of linear power, skipping NaN and values <= the validity floor.
    Trailing rows / cols that do not fill a block are dropped (as detect.multilook, boundary="trim")."""
    p = np.where(np.isfinite(p) & (p > load.MIN_VALID_POWER), p, np.nan)
    ny, nx = (p.shape[0] // n) * n, (p.shape[1] // n) * n
    b = p[:ny, :nx].reshape(ny // n, n, nx // n, n)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # all-NaN blocks -> NaN
        return np.nanmean(b, axis=(1, 3))


def grid_index(coords: np.ndarray, first: float, size: int) -> slice:
    """Slice of `coords` starting exactly at `first` with `size` elements; refuses if not on the grid."""
    i = np.where(np.isclose(coords, first, rtol=0.0, atol=1e-3))[0]
    if i.size != 1 or i[0] + size > coords.size:
        raise ValueError(f"{first} is not a pixel centre of this grid, or the window runs off it")
    return slice(int(i[0]), int(i[0]) + size)


def block_centres(c: np.ndarray, n: int) -> np.ndarray:
    m = (c.size // n) * n
    return c[:m].reshape(-1, n).mean(axis=1)


def read_blocks(tree: xr.DataTree, x0: float, y0: float, nx: int, ny: int, n: int):
    ds = tree[load.GRID_GROUP].ds
    epsg = int(ds["projection"].attrs["epsg_code"])
    x, y = ds[load.X_COORD].values, ds[load.Y_COORD].values
    xs, ys = grid_index(x, x0, nx), grid_index(y, y0, ny)
    out = {}
    for name, var in (("hh", load.HH_VAR), ("hv", load.HV_VAR)):
        strips = []
        for r in range(ys.start, ys.stop, STRIP_ROWS):
            rs = slice(r, min(r + STRIP_ROWS, ys.stop))
            strips.append(block_mean_linear(ds[var].isel({load.Y_COORD: rs, load.X_COORD: xs}).values, n))
        out[name] = np.concatenate(strips)
    return out, block_centres(x[xs], n), block_centres(y[ys], n), epsg


def window_bbox(x0: float, y0: float, nx: int, ny: int, epsg: int, spacing: float = 20.0) -> load.BBox:
    """lon/lat W S E N of the window's pixel-centre rectangle (used only for the granule search)."""
    from pyproj import Transformer
    xs = [x0, x0 + (nx - 1) * spacing]
    ys = [y0, y0 - (ny - 1) * spacing]
    lon, lat = Transformer.from_crs(epsg, 4326, always_xy=True).transform([xs[0], xs[1], xs[0], xs[1]],
                                                                          [ys[0], ys[0], ys[1], ys[1]])
    return (min(lon), min(lat), max(lon), max(lat))


def build(x0, y0, nx, ny, n, start, end, key: load.GroupKey, tile: str, epsg: int, out_dir: str = "data") -> str:
    if STRIP_ROWS % n:
        raise ValueError("STRIP_ROWS must be a multiple of the block size")
    grans = load.search_granules(window_bbox(x0, y0, nx, ny, epsg), start, end, key)
    hh, hv, dates, names, ref = [], [], [], [], None
    for g in grans:
        p = g.properties
        t = time.time()
        b, xc, yc, e = read_blocks(load.open_granule(p["url"]), x0, y0, nx, ny, n)
        if e != epsg:
            raise ValueError(f"{p['startTime'][:10]}: granule EPSG {e} != --epsg {epsg}")
        if ref is None:
            ref = (xc, yc)
        elif not (np.array_equal(xc, ref[0]) and np.array_equal(yc, ref[1])):
            raise ValueError(f"grid of {p['startTime'][:10]} differs; refusing to stack")
        hh.append(load.to_db(b["hh"]))
        hv.append(load.to_db(b["hv"]))
        dates.append(p["startTime"][:10])
        names.append(p["sceneName"])
        print(f"{dates[-1]}  blocks {b['hv'].shape}  valid {np.isfinite(hv[-1]).mean():.1%}  {time.time() - t:.0f}s", flush=True)
    if len(dates) < 2:
        raise SystemExit(f"only {len(dates)} date(s); a stack needs at least 2")
    xc, yc = ref
    ds = xr.Dataset(
        {"hh_db": (("time", "y", "x"), np.stack(hh)), "hv_db": (("time", "y", "x"), np.stack(hv))},
        coords={"time": np.array(dates, dtype="datetime64[ns]"), "y": yc, "x": xc},
        attrs={"crs": f"EPSG:{epsg}", "tile": tile, "track": key.track, "frame": key.frame,
               "direction": key.direction, "mode": key.mode, "product": "NISAR_L2_GCOV_PROVISIONAL_V1",
               "layers": f"{load.GRID_GROUP}/{{{load.HH_VAR},{load.HV_VAR}}}", "multilook": n,
               "pixel_spacing_m": float(abs(xc[1] - xc[0])), "native_spacing_m": float(abs(xc[1] - xc[0]) / n),
               "window_first_pixel_xy": [float(x0), float(y0)], "window_pixels_nx_ny": [nx, ny],
               "granules": ",".join(names),
               "note": f"{n}x{n} block mean in linear power applied while streaming (NaN / <= {load.MIN_VALID_POWER} "
                       "skipped); pixels are the blocks. Values are RTC gamma0 as delivered."},
    )
    for v in ("hh_db", "hv_db"):
        ds[v].attrs = {"units": "dB", "crs": f"EPSG:{epsg}",
                       "long_name": f"{v[:2].upper()} backscatter, {n}x{n} linear block mean, dB"}
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"stack_{tile}.nc")
    ds.to_netcdf(path, encoding={v: {"zlib": True, "complevel": 4} for v in ("hh_db", "hv_db")})
    return path


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--x0", type=float, required=True, help="first pixel centre x (grid CRS)")
    p.add_argument("--y0", type=float, required=True, help="first pixel centre y (grid CRS, top row)")
    p.add_argument("--nx", type=int, required=True)
    p.add_argument("--ny", type=int, required=True)
    p.add_argument("--block", type=int, default=5)
    p.add_argument("--epsg", type=int, default=32722, help="grid CRS (checked against every granule)")
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--track", type=int, required=True)
    p.add_argument("--frame", type=int, required=True)
    p.add_argument("--direction", required=True, choices=["ASCENDING", "DESCENDING"])
    p.add_argument("--mode", required=True)
    p.add_argument("--tile", required=True)
    p.add_argument("--out-dir", default="data")
    a = p.parse_args()
    key = load.GroupKey(a.track, a.frame, a.direction, a.mode)
    print(build(a.x0, a.y0, a.nx, a.ny, a.block, a.start, a.end, key, a.tile, a.epsg, a.out_dir))


if __name__ == "__main__":
    main()
