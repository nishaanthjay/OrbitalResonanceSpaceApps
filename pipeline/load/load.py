"""Pipeline A: stream NISAR L2 GCOV windows and build the analysis stack.

Reads:  NISAR_L2_GCOV_PROVISIONAL_V1 granules via asf_search (metadata) + earthaccess (streamed reads,
        never full downloads). Needs ~/.netrc with Earthdata Login.
Writes: data/stack_<tile>.nc  (CONTRACTS.md section 1: dims (time, y, x), vars hh_db / hv_db float32 dB,
        CRS in attrs["crs"] and as a rioxarray spatial_ref coord, time as datetime64).

Layer paths, CRS and the AOI come from CLAUDE.md "Confirmed facts" (verified by inspecting the datatree).
No multilooking here: pipeline/detect multilooks in linear power (attrs["multilook"] = 1 says so).
Only granules from ONE track / frame / direction / mode are combined, and every date must share the same grid.
"""
from __future__ import annotations

import argparse
import os
import time
from dataclasses import dataclass
from typing import Any

import numpy as np
import xarray as xr

BBox = tuple[float, float, float, float]  # (west, south, east, north), EPSG:4326

# Confirmed in CLAUDE.md (inspected datatree of NISAR_L2_PR_GCOV_*_060_A_173_* granules, 2026-11-14)
GRID_GROUP = "/science/LSAR/GCOV/grids/frequencyA"
HH_VAR, HV_VAR = "HHHH", "HVHV"
X_COORD, Y_COORD = "xCoordinates", "yCoordinates"
# Linear power below this is treated as no data (outside-swath pixels read ~1e-13, i.e. ~-130 dB).
MIN_VALID_POWER = 1e-6  # -60 dB


@dataclass(frozen=True)
class GroupKey:
    track: int
    frame: int
    direction: str
    mode: str


def _wkt(b: BBox) -> str:
    w, s, e, n = b
    return f"POLYGON(({w} {s},{e} {s},{e} {n},{w} {n},{w} {s}))"


def granule_key(props: dict) -> GroupKey:
    return GroupKey(int(props["pathNumber"]), int(props["frameNumber"]), str(props["flightDirection"]),
                    "/".join(props.get("rangeBandwidth") or []))


def is_dual_pol(props: dict) -> bool:
    return {"HH", "HV"} <= set(props.get("mainBandPolarization") or [])


def select_granules(results: list[Any], key: GroupKey) -> list[Any]:
    """Keep dual-pol granules of exactly one track/frame/direction/mode; one per date (latest processing wins)."""
    by_date: dict[str, Any] = {}
    for r in results:
        p = r.properties
        if granule_key(p) != key or not is_dual_pol(p):
            continue
        d = p["startTime"][:10]
        if d not in by_date or p.get("processingDate", "") > by_date[d].properties.get("processingDate", ""):
            by_date[d] = r
    return [by_date[d] for d in sorted(by_date)]


def search_granules(bbox: BBox, start: str, end: str, key: GroupKey) -> list[Any]:
    """Metadata-only search for GCOV granules intersecting bbox, filtered to one track/frame/direction/mode."""
    import asf_search as asf

    res = asf.search(dataset="NISAR", processingLevel="GCOV", intersectsWith=_wkt(bbox), start=start, end=end)
    return select_granules(list(res), key)


def open_granule(url: str) -> xr.DataTree:
    """Open one granule lazily as a DataTree (earthaccess + fsspec + h5netcdf)."""
    import earthaccess

    earthaccess.login(strategy="netrc")
    f = earthaccess.open([url])[0]
    return xr.open_datatree(f, engine="h5netcdf", phony_dims="access")


def window_slices(x: np.ndarray, y: np.ndarray, epsg: int, bbox: BBox) -> tuple[slice, slice]:
    """Index slices (y, x) of the grid cells inside bbox (lon/lat), after projecting bbox corners to the grid CRS."""
    from pyproj import Transformer

    w, s, e, n = bbox
    xs, ys = Transformer.from_crs(4326, epsg, always_xy=True).transform([w, e, w, e], [s, s, n, n])
    xi = np.where((x >= min(xs)) & (x <= max(xs)))[0]
    yi = np.where((y >= min(ys)) & (y <= max(ys)))[0]
    if xi.size == 0 or yi.size == 0:
        raise ValueError(f"bbox {bbox} does not overlap the granule grid")
    return slice(int(yi[0]), int(yi[-1]) + 1), slice(int(xi[0]), int(xi[-1]) + 1)


def to_db(power: xr.DataArray | np.ndarray, min_valid: float = MIN_VALID_POWER):
    """Linear power -> dB (float32). Non-finite or <= min_valid -> NaN."""
    p = np.asarray(power, dtype=np.float64)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where(np.isfinite(p) & (p > min_valid), 10.0 * np.log10(p), np.nan).astype(np.float32)
    if isinstance(power, xr.DataArray):
        return power.copy(data=out)
    return out


def extract_window(tree: xr.DataTree, bbox: BBox) -> tuple[xr.Dataset, int]:
    """Read only the bbox window of HH and HV power (linear). Returns Dataset(y, x) and the EPSG code."""
    ds = tree[GRID_GROUP].ds
    epsg = int(ds["projection"].attrs["epsg_code"])
    x, y = ds[X_COORD].values, ds[Y_COORD].values
    ys, xs = window_slices(x, y, epsg, bbox)
    sub = ds[[HH_VAR, HV_VAR]].isel({Y_COORD: ys, X_COORD: xs})
    out = xr.Dataset(
        {"hh": ((("y", "x")), sub[HH_VAR].values), "hv": ((("y", "x")), sub[HV_VAR].values)},
        coords={"y": sub[Y_COORD].values, "x": sub[X_COORD].values},
    )
    return out, epsg


def stack_windows(windows: list[xr.Dataset], dates: list[str], epsg: int, attrs: dict) -> xr.Dataset:
    """Stack per-date windows (must share the exact grid) into the CONTRACTS.md section 1 Dataset."""
    ref = windows[0]
    for d, w in zip(dates, windows):
        if w.sizes != ref.sizes or not (np.array_equal(w.x, ref.x) and np.array_equal(w.y, ref.y)):
            raise ValueError(f"grid of {d} differs from {dates[0]}; refusing to stack (no resampling in load)")
    hh = np.stack([to_db(w["hh"].values) for w in windows])
    hv = np.stack([to_db(w["hv"].values) for w in windows])
    ds = xr.Dataset(
        {"hh_db": (("time", "y", "x"), hh), "hv_db": (("time", "y", "x"), hv)},
        coords={"time": np.array(dates, dtype="datetime64[ns]"), "y": ref.y.values, "x": ref.x.values},
        attrs={"crs": f"EPSG:{epsg}", **attrs},
    )
    # CRS lives in attrs["crs"] (Dataset and each var), which rioxarray reads as .rio.crs. No spatial_ref var,
    # so a plain xr.open_dataset() shows exactly data_vars = hh_db, hv_db (CONTRACTS.md section 1).
    for v in ("hh_db", "hv_db"):
        ds[v].attrs = {"units": "dB", "crs": f"EPSG:{epsg}",
                       "long_name": f"{v[:2].upper()} backscatter (10*log10 of GCOV {v[:2].upper()*2})"}
    return ds


def build_stack(bbox: BBox, start: str, end: str, tile: str, key: GroupKey,
                out_dir: str = "data", max_dates: int | None = None) -> str:
    """Search, open, window, convert and stack all dates of one track/frame; write data/stack_<tile>.nc."""
    grans = search_granules(bbox, start, end, key)
    if not grans:
        raise SystemExit(f"no dual-pol granules for {key} in {start}..{end}")
    if max_dates:
        grans = grans[:max_dates]
    windows, dates, epsg, names = [], [], None, []
    for g in grans:
        p = g.properties
        t = time.time()
        w, e = extract_window(open_granule(p["url"]), bbox)
        if epsg is not None and e != epsg:
            raise ValueError(f"CRS changed between dates ({epsg} vs {e})")
        epsg = e
        valid = float(np.mean(w["hv"].values > MIN_VALID_POWER))
        print(f"{p['startTime'][:10]}  {dict(w.sizes)}  valid {valid:.0%}  {time.time() - t:.1f}s", flush=True)
        windows.append(w)
        dates.append(p["startTime"][:10])
        names.append(p["sceneName"])
    attrs = {
        "tile": tile, "track": key.track, "frame": key.frame, "direction": key.direction, "mode": key.mode,
        "bbox_wsen": list(bbox), "product": "NISAR_L2_GCOV_PROVISIONAL_V1", "layers": f"{GRID_GROUP}/{{{HH_VAR},{HV_VAR}}}",
        "multilook": 1, "pixel_spacing_m": float(abs(windows[0].x[1] - windows[0].x[0])),
        "granules": ",".join(names),
        "note": "HHHH/HVHV as delivered (possibly RTC gamma0; see CLAUDE.md TODO). No multilook applied.",
    }
    ds = stack_windows(windows, dates, epsg, attrs)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"stack_{tile}.nc")
    ds.to_netcdf(path, encoding={v: {"zlib": True, "complevel": 4} for v in ("hh_db", "hv_db")})
    return path


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--bbox", type=float, nargs=4, metavar=("W", "S", "E", "N"), required=True)
    p.add_argument("--start", required=True, help="YYYY-MM-DD")
    p.add_argument("--end", required=True, help="YYYY-MM-DD")
    p.add_argument("--tile", required=True, help="tile name used in the output filename")
    p.add_argument("--track", type=int, required=True, help="pathNumber")
    p.add_argument("--frame", type=int, required=True, help="frameNumber")
    p.add_argument("--direction", required=True, choices=["ASCENDING", "DESCENDING"])
    p.add_argument("--mode", required=True, help='rangeBandwidth joined by "/", e.g. "20+5"')
    p.add_argument("--max-dates", type=int, default=None, help="keep only the first N dates (for samples)")
    p.add_argument("--out-dir", default="data")
    a = p.parse_args()
    key = GroupKey(a.track, a.frame, a.direction, a.mode)
    print(build_stack(tuple(a.bbox), a.start, a.end, a.tile, key, a.out_dir, a.max_dates))


if __name__ == "__main__":
    main()
