"""Forest masks on the stack grid: Hansen GFC and ESA WorldCover candidates, their comparison, the stable-forest mask.

Reads:  a stack NetCDF (only its x/y grid and CRS), public Hansen GFC v1.13 and ESA WorldCover 2021 v200 tiles
        (HTTPS, no account), and the alert rows from fetch_alerts.py.
Writes: GeoTIFFs (uint8 0/1, on the stack grid) in --out-dir:
        forest_hansen.tif     treecover2000 >= 30 % and no Hansen loss 2001-2025
        forest_worldcover.tif WorldCover 2021 class 10 (tree cover)
        forest_mask.tif       forest in both, minus pixels alerted before the first stack date (for detect --forest-mask)
        stable_forest.tif     forest_mask minus every alert pixel of any date, grown by --alert-buffer pixels
                              (for detect --stable-mask)
Each candidate is made binary at its native resolution and averaged onto the 20 m grid; a pixel is forest when at
least half of it is.
"""
from __future__ import annotations

import argparse
import json

import numpy as np
import rasterio
import rasterio.errors
import xarray as xr
from rasterio.features import rasterize
from rasterio.warp import Resampling, reproject, transform_bounds
from rasterio.windows import from_bounds
from scipy.ndimage import binary_dilation
from shapely.geometry import box

HANSEN = "/vsicurl/https://storage.googleapis.com/earthenginepartners-hansen/GFC-2025-v1.13/Hansen_GFC-2025-v1.13_{layer}_00N_070W.tif"
WORLDCOVER = "/vsicurl/https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_{tile}_Map.tif"
WC_TILES = ("S09W063", "S12W063")  # 3x3 deg tiles named by their SW corner; both tried, empty ones skipped
ALERT_FILES = {"umd_glad_landsat_alerts": ("alerts_glad_l.json", 0.00025),
               "umd_glad_sentinel2_alerts": ("alerts_glad_s2.json", 0.0001)}


def stack_grid(path: str) -> tuple[rasterio.Affine, tuple[int, int], str]:
    """Affine transform, (rows, cols) and CRS of the stack's pixel-centre x/y coordinates."""
    ds = xr.open_dataset(path)
    x, y = ds.x.values, ds.y.values
    dx, dy = float(x[1] - x[0]), float(y[1] - y[0])
    t = rasterio.Affine(dx, 0, float(x[0]) - dx / 2, 0, dy, float(y[0]) - dy / 2)
    return t, (len(y), len(x)), ds.attrs["crs"]


def to_grid(src_url: str, binarize, transform, shape, crs) -> np.ndarray:
    """Fraction (0..1) of each grid pixel covered by binarize(source pixels); NaN where the source has no data."""
    out = np.full(shape, np.nan, dtype=np.float32)
    h, w = shape
    bounds = transform_bounds(crs, "EPSG:4326", transform.c, transform.f + h * transform.e,
                              transform.c + w * transform.a, transform.f)
    with rasterio.open(src_url) as src:
        win = from_bounds(*bounds, src.transform).round_offsets().round_lengths()
        try:
            win = win.intersection(rasterio.windows.Window(0, 0, src.width, src.height))
        except rasterio.errors.WindowError:  # this source tile does not reach the grid
            return out
        data = binarize(src.read(1, window=win, boundless=False)).astype(np.float32)
        reproject(data, out, src_transform=src.window_transform(win), src_crs=src.crs, src_nodata=None,
                  dst_transform=transform, dst_crs=crs, dst_nodata=np.nan, resampling=Resampling.average,
                  init_dest_nodata=False)
    return out


def alert_raster(alert_dir: str, transform, shape, crs, before: str | None = None) -> np.ndarray:
    """Grid pixels touched by any alert pixel (optionally only alerts dated before `before`)."""
    from pyproj import Transformer
    to = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    geoms = []
    for field, (fname, deg) in ALERT_FILES.items():
        with open(f"{alert_dir}/{fname}", encoding="utf-8") as f:
            rows = json.load(f)
        for r in rows:
            d = r[f"{field}__date"]
            if d is None or (before and d >= before):
                continue
            lon, lat = r["longitude"], r["latitude"]
            xs, ys = to.transform([lon - deg / 2, lon + deg / 2], [lat - deg / 2, lat + deg / 2])
            geoms.append(box(min(xs), min(ys), max(xs), max(ys)))
    if not geoms:
        return np.zeros(shape, bool)
    return rasterize(((g, 1) for g in geoms), out_shape=shape, transform=transform, all_touched=True,
                     dtype="uint8").astype(bool)


def write_mask(path: str, m: np.ndarray, transform, crs) -> None:
    with rasterio.open(path, "w", driver="GTiff", height=m.shape[0], width=m.shape[1], count=1, dtype="uint8",
                       crs=crs, transform=transform, compress="deflate") as dst:
        dst.write(m.astype(np.uint8), 1)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--stack", required=True, help="any stack on the analysis grid (only x/y/crs are read)")
    p.add_argument("--first-date", required=True, help="first stack date: alerts before it are not forest at start")
    p.add_argument("--alert-dir", default="data")
    p.add_argument("--alert-buffer", type=int, default=1, help="grid pixels to grow alerts by for the stable mask")
    p.add_argument("--out-dir", default="data")
    a = p.parse_args()
    t, shape, crs = stack_grid(a.stack)

    tc = to_grid(HANSEN.format(layer="treecover2000"), lambda v: v >= 30, t, shape, crs)
    loss = to_grid(HANSEN.format(layer="lossyear"), lambda v: v > 0, t, shape, crs)
    hansen = (tc >= 0.5) & (loss < 0.5)
    wc = np.full(shape, np.nan, dtype=np.float32)
    for tile in WC_TILES:
        part = to_grid(WORLDCOVER.format(tile=tile), lambda v: v == 10, t, shape, crs)
        wc = np.where(np.isnan(wc), part, wc)
    worldcover = wc >= 0.5
    if np.isnan(tc).any() or np.isnan(wc).any():
        raise RuntimeError("a candidate does not cover the whole grid")

    alerted_before = alert_raster(a.alert_dir, t, shape, crs, before=a.first_date)
    alerted_any = binary_dilation(alert_raster(a.alert_dir, t, shape, crs), iterations=a.alert_buffer) \
        if a.alert_buffer else alert_raster(a.alert_dir, t, shape, crs)
    forest = hansen & worldcover & ~alerted_before
    stable = forest & ~alerted_any

    n = hansen.size
    both, h_only, w_only = (hansen & worldcover).sum(), (hansen & ~worldcover).sum(), (~hansen & worldcover).sum()
    agree = (hansen == worldcover).mean()
    pe = hansen.mean() * worldcover.mean() + (1 - hansen.mean()) * (1 - worldcover.mean())
    print(f"grid {shape} px, {abs(t.a)} m, {crs}")
    print(f"hansen forest {hansen.mean():.4f}  worldcover tree {worldcover.mean():.4f}  of {n} px")
    print(f"both {both / n:.4f}  hansen-only {h_only / n:.4f}  worldcover-only {w_only / n:.4f}  "
          f"agreement {agree:.4f}  kappa {(agree - pe) / (1 - pe):.4f}")
    print(f"alerted before {a.first_date}: {alerted_before.sum()} px; alerted any date (+{a.alert_buffer} px): "
          f"{alerted_any.sum()} px")
    print(f"forest_mask {forest.mean():.4f} ({forest.sum()} px)  stable_forest {stable.mean():.4f} ({stable.sum()} px)")
    for name, m in (("forest_hansen", hansen), ("forest_worldcover", worldcover), ("forest_mask", forest),
                    ("stable_forest", stable)):
        write_mask(f"{a.out_dir}/{name}.tif", m, t, crs)


if __name__ == "__main__":
    main()
