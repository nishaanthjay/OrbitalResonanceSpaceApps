"""Web layers for the 60 x 60 km forest map (validation/PREREG_scale.md): per-date and median forest maps, lost blocks.

Reads:  the big stack (pipeline/load/load_big.py, pixels = 100 m blocks), validation/scale_metrics.json (scores are
        copied, never recomputed here), T_db from validation/fnf_metrics.json.
Writes: <out-dir>/forest_<date>.webp (9), forest_median.webp, lost.webp: lossless RGBA WebP on ONE EPSG:3857 grid
        (canopy green #2f6b4f = forest, laterite #b4401c = non-forest, transparent = no data / not lost);
        <out-dir>/big.json (bounds, grid, dates, T_db, original window, scores); <out-dir>/lost.geojson (lost blocks
        merged into 8-connected patches: id, area_ha, hv_series_db = patch mean of block HV in linear power, in dB).

  python web/tools/make_big.py --stack data/stack_big_t2f174.nc --metrics validation/scale_metrics.json \
    --out-dir web/data/explore/big
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import xarray as xr
from PIL import Image
from pyproj import Transformer
from rasterio.features import shapes
from rasterio.transform import from_origin
from rasterio.warp import Resampling, calculate_default_transform, reproject, transform_bounds
from scipy import ndimage
from shapely.geometry import mapping, shape
from shapely.ops import transform as shp_transform

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "validation"))
import fnf  # noqa: E402
import scale  # noqa: E402

FOREST, NONFOREST = (0x2F, 0x6B, 0x4F), (0xB4, 0x40, 0x1C)
NODATA, CLS_FOREST, CLS_NONFOREST = 0, 1, 2


def classes(hv_db: np.ndarray, T: float) -> np.ndarray:
    """uint8: 0 no data (NaN), 1 forest (>= T), 2 non-forest."""
    out = np.full(hv_db.shape, NODATA, np.uint8)
    ok = np.isfinite(hv_db)
    out[ok & (hv_db >= T)] = CLS_FOREST
    out[ok & (hv_db < T)] = CLS_NONFOREST
    return out


def rgba(cls: np.ndarray) -> np.ndarray:
    img = np.zeros(cls.shape + (4,), np.uint8)
    for v, col in ((CLS_FOREST, FOREST), (CLS_NONFOREST, NONFOREST)):
        img[cls == v] = (*col, 255)
    return img


def save_webp(img: np.ndarray, path: str) -> int:
    Image.fromarray(img, "RGBA").save(path, format="WEBP", lossless=True, exact=True)
    return os.path.getsize(path)


def first_flagged(forest: np.ndarray, first: int = 3) -> np.ndarray:
    """Per block, index of the earliest pass k >= `first` (08-13 onward) from which it is non-forest on every pass
    k..last; -1 if none. For a lost block this is at most 7 (09-30), because the rule needs 09-30 and 10-12 non-forest."""
    stay = np.flip(np.logical_and.accumulate(np.flip(~forest, axis=0), axis=0), axis=0)  # non-forest from k to the end
    out = np.full(forest.shape[1:], -1, int)
    for k in range(forest.shape[0] - 1, first - 1, -1):
        out[stay[k]] = k
    return out


def patches(lost: np.ndarray, hv: np.ndarray, transform, crs: str, block_ha: float, in_orig: np.ndarray,
            dates: list[str] | None = None, T: float | None = None) -> dict:
    lab, n = ndimage.label(lost, structure=np.ones((3, 3), int))
    ff = first_flagged(hv >= T) if T is not None else None
    to_ll = Transformer.from_crs(crs, 4326, always_xy=True).transform
    lin = 10.0 ** (hv / 10.0)
    feats = []
    for i in range(1, n + 1):
        m = lab == i
        geom = None
        for g, v in shapes(m.astype(np.uint8), mask=m, transform=transform, connectivity=8):
            p = shape(g)
            geom = p if geom is None else geom.union(p)
        series = 10.0 * np.log10(lin[:, m].mean(axis=1))
        g_ll = shp_transform(to_ll, geom)
        c = g_ll.centroid
        props = {"id": i, "area_ha": round(float(m.sum() * block_ha), 2), "n_blocks": int(m.sum()),
                 "centroid_lon": round(c.x, 5), "centroid_lat": round(c.y, 5),
                 "hv_series_db": [round(float(v), 2) for v in series],
                 "in_original_window": bool(in_orig[m].any())}
        if ff is not None and dates is not None:
            k = int(ff[m][ff[m] >= 0].min()) if (ff[m] >= 0).any() else -1
            props["first_flagged"] = dates[k] if k >= 0 else None
        feats.append({"type": "Feature", "geometry": mapping(g_ll), "properties": props})
    return {"type": "FeatureCollection", "features": feats}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--stack", default="data/stack_big_t2f174.nc")
    p.add_argument("--metrics", default="validation/scale_metrics.json")
    p.add_argument("--out-dir", default="web/data/explore/big")
    a = p.parse_args()
    os.makedirs(a.out_dir, exist_ok=True)
    T = scale.frozen_T()
    met = json.loads(Path(a.metrics).read_text())
    if met["T_db"] != T:
        raise SystemExit("scale_metrics.json T_db differs from fnf_metrics.json")
    ds = xr.open_dataset(a.stack)
    dates = [str(t)[:10] for t in ds.time.values]
    hv = ds["hv_db"].values
    xc, yc, crs = ds["x"].values, ds["y"].values, ds.attrs["crs"]
    d = float(xc[1] - xc[0])
    src_tf = from_origin(xc[0] - d / 2, yc[0] + d / 2, d, d)
    ny, nx = hv.shape[1:]
    valid = np.isfinite(hv).all(axis=0)
    hv_v = np.where(valid, hv, np.nan)  # maps show only blocks valid on all 9 dates (the pre-registered clip)

    left, top = xc[0] - d / 2, yc[0] + d / 2
    dst_tf, w, h = calculate_default_transform(crs, "EPSG:3857", nx, ny, left, top - ny * d, left + nx * d, top)
    bounds3857 = (dst_tf.c, dst_tf.f + h * dst_tf.e, dst_tf.c + w * dst_tf.a, dst_tf.f)

    def warp(arr: np.ndarray) -> np.ndarray:
        out = np.zeros((h, w), np.uint8)
        reproject(arr, out, src_transform=src_tf, src_crs=crs, dst_transform=dst_tf, dst_crs="EPSG:3857",
                  resampling=Resampling.nearest, src_nodata=0, dst_nodata=0)
        return out

    sizes = {}
    for i, dte in enumerate(dates):
        sizes[f"forest_{dte}.webp"] = save_webp(rgba(warp(classes(hv_v[i], T))), f"{a.out_dir}/forest_{dte}.webp")
    sizes["forest_median.webp"] = save_webp(rgba(warp(classes(fnf.median_feature(hv_v), T))), f"{a.out_dir}/forest_median.webp")
    forest = hv_v >= T
    lost = scale.lost_rule(forest) & valid
    lost_img = np.zeros((h, w, 4), np.uint8)
    lost_img[warp(lost.astype(np.uint8)) == 1] = (*NONFOREST, 255)
    sizes["lost.webp"] = save_webp(lost_img, f"{a.out_dir}/lost.webp")

    xx, yy = np.meshgrid(xc, yc)
    lon, lat = Transformer.from_crs(crs, 4326, always_xy=True).transform(xx, yy)
    W, S, E, N = scale.ORIGINAL_BBOX
    in_orig = (lon >= W) & (lon <= E) & (lat >= S) & (lat <= N)
    gj = patches(lost, hv, src_tf, crs, d * d / 1e4, in_orig, dates, T)
    with open(f"{a.out_dir}/lost.geojson", "w") as f:
        json.dump(gj, f, separators=(",", ":"))
    sizes["lost.geojson"] = os.path.getsize(f"{a.out_dir}/lost.geojson")

    b = met["b_alerts"]
    meta = {
        "source": "NISAR L2 GCOV provisional, track 2 frame 174 ascending, frequencyA HV, 5x5 (100 m) linear block mean",
        "prereg": "validation/PREREG_scale.md", "metrics_file": "validation/scale_metrics.json",
        "bounds_lonlat": list(transform_bounds("EPSG:3857", "EPSG:4326", *bounds3857)),
        "grid": {"crs": "EPSG:3857", "width": w, "height": h, "bounds": list(bounds3857), "transform": list(dst_tf)[:6]},
        "resampling": "nearest", "dates": dates, "T_db": T,
        "original_window_bbox": list(scale.ORIGINAL_BBOX),
        "colors": {"forest": "#2f6b4f", "non_forest": "#b4401c", "lost": "#b4401c", "transparent": "no data / not lost"},
        "layers": {"forest": [f"forest_{x}.webp" for x in dates], "median": "forest_median.webp",
                   "lost": "lost.webp", "lost_patches": "lost.geojson"},
        "n_lost_patches": len(gj["features"]),
        "first_flagged_definition": "per block: the earliest pass from 08-13 on from which the block is non-forest on every pass through 10-12; patch value = the earliest over its blocks",
        "scores": {"scope": "big AOI, valid on all 9 dates, original window excluded",
                   "blocks": met["blocks"], "forest_map_vs_hansen": met["a_forest_map"]["median"],
                   "forest_map_per_date": met["a_forest_map"]["per_date"], "loss_rule": met["loss_rule"],
                   "alerts": {s: {"lost": b[s]["lost"], "control": b[s]["control"]} for s in ("GLAD-L", "GLAD-S2")},
                   "alert_windows": {"reference": b["reference_dates"], "precision": b["precision_window"]}},
    }
    with open(f"{a.out_dir}/big.json", "w") as f:
        json.dump(meta, f, indent=1)
    sizes["big.json"] = os.path.getsize(f"{a.out_dir}/big.json")
    for k, v in sizes.items():
        print(f"{v:>9,d}  {k}")
    print(f"{sum(sizes.values()):>9,d}  total  ({w} x {h} px, {len(gj['features'])} lost patches)")


if __name__ == "__main__":
    main()
