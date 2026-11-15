"""Build a binary forest mask on the stack grid from Hansen/UMD Global Forest Change v1.13 (streamed window only).

forest = treecover2000 >= --treecover-min (%)  AND  lossyear == 0 (no loss 2001-2025)  AND  datamask == 1 (land)

Source: Hansen et al. 2013, Science 342:850-853; GFC-2025-v1.13 tiles
  https://storage.googleapis.com/earthenginepartners-hansen/GFC-2025-v1.13/download.html
Band encodings from the Earth Engine catalog entry UMD/hansen/global_forest_change_2025_v1_13:
  treecover2000 = % canopy cover (0-100); lossyear = 0 no loss, else year index (max 25);
  datamask = 0 no data, 1 mapped land, 2 permanent water.
Writes a uint8 GeoTIFF (1 = forest, 0 = not forest) on exactly the stack's x/y grid and CRS; pipeline/detect
reads it with --forest-mask (and --stable-mask defaults to it).
"""
from __future__ import annotations

import argparse

import numpy as np
import rioxarray
import xarray as xr
from rasterio.enums import Resampling

BASE = "https://storage.googleapis.com/earthenginepartners-hansen/GFC-2025-v1.13/Hansen_GFC-2025-v1.13_{layer}_{tile}.tif"


def hansen_tile(lon: float, lat: float) -> str:
    """Tile name by its top-left corner on the 10-degree grid, e.g. (-62.8, -9.2) -> '00N_070W'."""
    top = int(np.ceil(lat / 10.0) * 10)
    left = int(np.floor(lon / 10.0) * 10)
    ns = f"{abs(top):02d}{'N' if top >= 0 else 'S'}"
    ew = f"{abs(left):03d}{'E' if left >= 0 else 'W'}"
    return f"{ns}_{ew}"


def forest_from_layers(treecover: np.ndarray, lossyear: np.ndarray, datamask: np.ndarray, tc_min: float) -> np.ndarray:
    return ((treecover >= tc_min) & (lossyear == 0) & (datamask == 1)).astype(np.uint8)


def native_grid(c: np.ndarray, n: int) -> np.ndarray:
    """Pixel centres of the n x n native pixels behind block centres c (block = mean of n native centres)."""
    d = (c[1] - c[0]) / n
    return (c[:, None] + (np.arange(n) - (n - 1) / 2) * d).ravel()


def build(stack_path: str, out_path: str, tc_min: float = 30.0, subdivide: int = 1) -> dict:
    """subdivide > 1: the stack pixels are n x n blocks (load_big.py); write the mask on the native grid behind them."""
    ds = xr.open_dataset(stack_path)
    template = ds["hh_db"].isel(time=0)
    if subdivide > 1:
        template = xr.DataArray(np.zeros((ds.sizes["y"] * subdivide, ds.sizes["x"] * subdivide), np.float32),
                                coords={"y": native_grid(ds["y"].values, subdivide),
                                        "x": native_grid(ds["x"].values, subdivide)}, dims=("y", "x"))
    template = template.rio.write_crs(ds.attrs["crs"])
    w, s, e, n = template.rio.transform_bounds("EPSG:4326")
    corners = {hansen_tile(x, y) for x in (w, e) for y in (s, n)}
    if len(corners) != 1:
        raise SystemExit(f"window spans several Hansen tiles {corners}; mosaic not implemented")
    tile = corners.pop()
    pad = 0.01
    layers = {}
    for layer in ("treecover2000", "lossyear", "datamask"):
        r = rioxarray.open_rasterio(f"/vsicurl/{BASE.format(layer=layer, tile=tile)}").squeeze(drop=True)
        r = r.rio.clip_box(w - pad, s - pad, e + pad, n + pad)
        layers[layer] = r.rio.reproject_match(template, resampling=Resampling.nearest).values
    m = forest_from_layers(layers["treecover2000"], layers["lossyear"], layers["datamask"], tc_min)
    out = xr.DataArray(m, coords=template.coords, dims=template.dims).rio.write_crs(ds.attrs["crs"])
    out.rio.write_nodata(255, inplace=True)
    out.rio.to_raster(out_path, dtype="uint8", compress="deflate")
    return {"tile": tile, "forest_fraction": float(m.mean()), "shape": m.shape,
            "loss_2001_2025_fraction": float((layers["lossyear"] > 0).mean())}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--stack", required=True, help="data/stack_<tile>.nc (grid template)")
    p.add_argument("--out", required=True, help="output GeoTIFF, e.g. data/forest_mask_<tile>.tif")
    p.add_argument("--treecover-min", type=float, default=30.0, help="minimum treecover2000 %% to count as forest")
    p.add_argument("--subdivide", type=int, default=1,
                   help="stack pixels are N x N blocks (load_big.py --block N): write the mask on the native grid")
    a = p.parse_args()
    print(build(a.stack, a.out, a.treecover_min, a.subdivide))


if __name__ == "__main__":
    main()
