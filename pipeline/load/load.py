"""Pipeline A: stream NISAR L2 GCOV windows and build the analysis stack.

Reads:  NISAR_L2_GCOV_PROVISIONAL_V1 granules via earthaccess (streamed, never fully downloaded).
Writes: data/stack_<tile>.nc  (CONTRACTS.md section 1: dims (time, y, x), vars hh_db / hv_db float32 dB,
        CRS in attrs, time as datetime64).

Layer paths come from CLAUDE.md "Confirmed facts". Never guess them: inspect the datatree first.
"""
from __future__ import annotations

import argparse
from typing import Any

import xarray as xr

BBox = tuple[float, float, float, float]  # (west, south, east, north), EPSG:4326


def search_granules(bbox: BBox, start: str, end: str) -> list[Any]:
    """Search earthaccess for GCOV granules intersecting bbox between start and end (YYYY-MM-DD)."""
    # TODO: earthaccess.login(); earthaccess.search_data(short_name=..., bounding_box=bbox, temporal=(start, end))
    raise NotImplementedError


def open_granule(granule: Any) -> xr.DataTree:
    """Open one granule lazily as a DataTree (earthaccess + fsspec + h5netcdf)."""
    # TODO: xr.open_datatree(<fsspec file>, engine="h5netcdf")
    raise NotImplementedError


def extract_window(tree: xr.DataTree, bbox: BBox) -> xr.Dataset:
    """Subset HH and HV power to bbox. Reads only the window, not the whole ~5 GB file."""
    # TODO: HH layer path from CLAUDE.md (inspect the tree, do not guess)
    # TODO: HV layer path from CLAUDE.md
    # TODO: coordinate names, CRS, pixel spacing from CLAUDE.md
    raise NotImplementedError


def to_db(power: xr.DataArray) -> xr.DataArray:
    """Convert linear backscatter power to dB (float32)."""
    # TODO: 10*log10, handle zeros/nodata
    raise NotImplementedError


def multilook(da: xr.DataArray, looks_y: int, looks_x: int) -> xr.DataArray:
    """Spatially average (in linear power, before dB) to reduce speckle."""
    # TODO: da.coarsen(...).mean()
    raise NotImplementedError


def build_stack(bbox: BBox, start: str, end: str, tile: str, out_dir: str = "data") -> str:
    """Search, open, window, multilook, convert and stack all dates; write data/stack_<tile>.nc. Returns path."""
    # TODO: only combine granules from the same track/frame
    # TODO: write CRS into attrs, time as datetime64
    raise NotImplementedError


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--bbox", type=float, nargs=4, metavar=("W", "S", "E", "N"), required=True)
    p.add_argument("--start", required=True, help="YYYY-MM-DD")
    p.add_argument("--end", required=True, help="YYYY-MM-DD")
    p.add_argument("--tile", required=True, help="tile name used in the output filename")
    p.add_argument("--out-dir", default="data")
    a = p.parse_args()
    print(build_stack(tuple(a.bbox), a.start, a.end, a.tile, a.out_dir))


if __name__ == "__main__":
    main()
