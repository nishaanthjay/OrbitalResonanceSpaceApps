"""Web layers for the full NISAR frame (validation/PREREG_frame.md): median forest map, lost blocks, first-switch map, lost patches.

Derives everything from data/stack_frame_t2f174.nc with the frozen rules (scale.lost_rule, frame.first_switch_index);
never calls frame.run() and never writes frame_metrics.json: its content is copied verbatim into frame.json 'scores'.
Reuses make_big's class codes, rgba and save_webp.

  python web/tools/make_frame.py --stack data/stack_frame_t2f174.nc --alerts-dir data/final_frame \
    --metrics validation/frame_metrics.json --out-dir web/data/explore/frame
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

import numpy as np
import xarray as xr
from pyproj import Transformer
from rasterio.features import shapes
from rasterio.transform import from_origin
from rasterio.warp import Resampling, calculate_default_transform, reproject, transform_bounds
from scipy import ndimage
from shapely.geometry import mapping, shape
from shapely.ops import transform as shp_transform

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "validation"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_alerts_frame  # noqa: E402
import fnf  # noqa: E402
import frame  # noqa: E402
import make_big  # noqa: E402
import scale  # noqa: E402

LOST_COLOUR = (0xFF, 0x2B, 0xD6)
# viridis, 9 samples: one per pass (index = pass the block first stays non-forest from)
SWITCH_COLOURS = ["#440154", "#472d7b", "#3b528b", "#2c728e", "#21908d", "#27ad81", "#5cc863", "#aadc32", "#fde725"]
CATEGORIES = {"alert_supported": "at least one block of the patch has a GLAD-L or GLAD-S2 alert dated 2026-06-26..2026-11-05",
              "radar_only_unconfirmed": "no GLAD-L / GLAD-S2 alert in that window; radar class switch only, not confirmed by optical alerts"}
LIMIT = 15_000_000


def hex_rgb(h: str) -> tuple:
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def downsample(arr: np.ndarray, f: int) -> np.ndarray:
    """Nearest-neighbour: the pixel at the centre of each f x f cell."""
    return arr if f == 1 else arr[f // 2::f, f // 2::f]


def switch_rgba(cls: np.ndarray, colours: list[str]) -> np.ndarray:
    """cls 0 = transparent, k = colour k-1."""
    img = np.zeros(cls.shape + (4,), np.uint8)
    for k, c in enumerate(colours, 1):
        img[cls == k] = (*hex_rgb(c), 255)
    return img


def patch_table(lost: np.ndarray, hv: np.ndarray, first: np.ndarray, alert: np.ndarray, dates: list[str], block_ha: float):
    """8-connected patches of `lost`: (label image, property dicts with id = label). hv_series_db = mean of block dB."""
    lab, n = ndimage.label(lost, structure=np.ones((3, 3), int))
    idx = np.arange(1, n + 1)
    area = ndimage.sum(np.ones(lab.shape), lab, idx) * block_ha
    fs = np.atleast_1d(ndimage.minimum(np.where(lost, first, 99), lab, idx)).astype(int)
    al = np.atleast_1d(ndimage.maximum(alert.astype(np.uint8), lab, idx)) > 0
    ser = np.stack([np.atleast_1d(ndimage.mean(np.where(lost, hv[i], 0.0), lab, idx)) for i in range(hv.shape[0])], axis=1)
    props = [{"id": int(i), "area_ha": round(float(a), 2), "first_switch_date": dates[f] if 0 <= f < len(dates) else None,
              "category": "alert_supported" if s else "radar_only_unconfirmed",
              "hv_series_db": [round(float(v), 2) for v in r]}
             for i, a, f, s, r in zip(idx, np.atleast_1d(area), fs, al, ser)]
    return lab, props


def geojson(lab: np.ndarray, props: list[dict], transform, crs: str, keep_min_ha: float = 0.0) -> dict:
    """Block-outline polygons (one per label, 8-connected, holes kept) in WGS84, 5 decimals."""
    to_ll = Transformer.from_crs(crs, 4326, always_xy=True).transform

    def rnd(x, y):
        a, b = to_ll(x, y)
        return np.round(a, 5), np.round(b, 5)

    by_id = {p["id"]: p for p in props if p["area_ha"] >= keep_min_ha}
    feats = []
    for g, v in shapes(lab.astype(np.int32), mask=lab > 0, transform=transform, connectivity=8):
        if int(v) in by_id:
            feats.append({"type": "Feature", "geometry": mapping(shp_transform(rnd, shape(g))), "properties": by_id[int(v)]})
    return {"type": "FeatureCollection", "features": feats}


def outline_ll(x0, x1, y0, y1, crs: str, n: int = 25) -> list:
    """Closed lon/lat ring of a projected rectangle, edges densified."""
    t = np.linspace(0, 1, n)
    xs = np.concatenate([x0 + (x1 - x0) * t, np.full(n, x1), x1 - (x1 - x0) * t, np.full(n, x0)])
    ys = np.concatenate([np.full(n, y0), y0 + (y1 - y0) * t, np.full(n, y1), y1 - (y1 - y0) * t])
    lo, la = Transformer.from_crs(crs, 4326, always_xy=True).transform(xs, ys)
    ring = [[round(float(a), 5), round(float(b), 5)] for a, b in zip(lo, la)]
    return ring + [ring[0]]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--stack", default="data/stack_frame_t2f174.nc")
    p.add_argument("--alerts-dir", default="data/final_frame")
    p.add_argument("--metrics", default="validation/frame_metrics.json")
    p.add_argument("--out-dir", default="web/data/explore/frame")
    a = p.parse_args()
    os.makedirs(a.out_dir, exist_ok=True)
    T = scale.frozen_T()
    met = json.loads(Path(a.metrics).read_text())  # read only
    if met["T_db"] != T:
        raise SystemExit("frame_metrics.json T_db differs from fnf_metrics.json")
    ds = xr.open_dataset(a.stack)
    dates = [str(t)[:10] for t in ds.time.values]
    if dates != scale.DATES:
        raise SystemExit("stack dates differ from pre-registered")
    hv = ds["hv_db"].values
    xc, yc, crs = ds["x"].values, ds["y"].values, ds.attrs["crs"]
    d = float(xc[1] - xc[0])
    ny, nx = hv.shape[1:]
    valid = np.isfinite(hv).all(axis=0)
    hv = np.where(valid, hv, np.nan)

    xx, yy = np.meshgrid(xc, yc)
    lon, lat = Transformer.from_crs(crs, 4326, always_xy=True).transform(xx, yy)
    del xx, yy
    W, S, E, N = scale.ORIGINAL_BBOX
    in_orig = (lon >= W) & (lon <= E) & (lat >= S) & (lat <= N)
    scored = valid & ~in_orig & ~frame.box60_mask(xc, yc)
    forest = hv >= T
    lost_all = scale.lost_rule(forest) & valid
    n_scored = int((lost_all & scored).sum())
    expect = met["loss_rule"]["lost_blocks"]
    assert n_scored == expect, f"derived lost {n_scored} != frame_metrics {expect}"
    print(f"lost over scored area = {n_scored} == frame_metrics ({expect}); all valid lost = {int(lost_all.sum())}")

    first = np.where(lost_all, frame.first_switch_index(forest), -1)
    to_grid = Transformer.from_crs(4326, crs, always_xy=True)
    tol = dt.timedelta(days=scale.TOL_DAYS)
    win = (scale.REF_START - tol, scale.REF_END + tol)
    alert = np.zeros(valid.shape, bool)
    for src in ("GLAD-L", "GLAD-S2"):
        ad, alo, ala = fetch_alerts_frame.read_saved(src, a.alerts_dir)
        ax, ay = to_grid.transform(alo, ala)
        r, c = scale.block_index(np.asarray(ax), np.asarray(ay), xc, yc)
        alert |= scale.alert_blocks(ad, r, c, valid.shape, *win)

    src_tf = from_origin(xc[0] - d / 2, yc[0] + d / 2, d, d)
    lab, props = patch_table(lost_all, hv, first, alert, dates, d * d / 1e4)
    cnt = lambda ps: {k: sum(q["category"] == k for q in ps) for k in CATEGORIES}  # noqa: E731
    before = {"patches": len(props), **cnt(props)}
    gj_path = f"{a.out_dir}/lost.geojson"
    min_ha = 0.0
    gj = geojson(lab, props, src_tf, crs)

    left, top = xc[0] - d / 2, yc[0] + d / 2
    dst_tf, w, h = calculate_default_transform(crs, "EPSG:3857", nx, ny, left, top - ny * d, left + nx * d, top)

    def warp(arr: np.ndarray) -> np.ndarray:
        out = np.zeros((h, w), np.uint8)
        reproject(arr, out, src_transform=src_tf, src_crs=crs, dst_transform=dst_tf, dst_crs="EPSG:3857",
                  resampling=Resampling.nearest, src_nodata=0, dst_nodata=0)
        return out

    med = warp(make_big.classes(fnf.median_feature(hv), T))
    lost_c = warp(lost_all.astype(np.uint8))
    sw_c = warp(np.where(lost_all, first + 1, 0).astype(np.uint8))

    def write_all(f: int) -> dict:
        s = {"forest_median.webp": make_big.save_webp(make_big.rgba(downsample(med, f)), f"{a.out_dir}/forest_median.webp")}
        lc = downsample(lost_c, f)
        li = np.zeros(lc.shape + (4,), np.uint8)
        li[lc == 1] = (*LOST_COLOUR, 255)
        s["lost.webp"] = make_big.save_webp(li, f"{a.out_dir}/lost.webp")
        s["first_switch.webp"] = make_big.save_webp(switch_rgba(downsample(sw_c, f), SWITCH_COLOURS), f"{a.out_dir}/first_switch.webp")
        return s

    def write_gj(g: dict) -> int:
        with open(gj_path, "w") as fh:
            json.dump(g, fh, separators=(",", ":"))
        return os.path.getsize(gj_path)

    gj_size = write_gj(gj)
    f = 1
    sizes = write_all(f)
    while sum(sizes.values()) > LIMIT // 3 and f < 4:  # images alone too big: coarsen them (web copy only)
        f += 1
        sizes = write_all(f)
    if gj_size + sum(sizes.values()) + 30_000 > LIMIT:  # then drop small patches
        min_ha = 3.0
        gj = geojson(lab, props, src_tf, crs, min_ha)
        gj_size = write_gj(gj)
    after = {"patches": len(gj["features"]), **cnt([q["properties"] for q in gj["features"]])}

    hh, hw = downsample(lost_c, f).shape
    b3857 = (dst_tf.c, dst_tf.f + h * dst_tf.e, dst_tf.c + w * dst_tf.a, dst_tf.f)
    meta = {
        "source": "NISAR L2 GCOV provisional, track 2 frame 174 ascending, frequencyA HV, 5x5 (100 m) linear block mean",
        "prereg": "validation/PREREG_frame.md", "metrics_file": "validation/frame_metrics.json",
        "bounds_lonlat_wsen": list(transform_bounds("EPSG:3857", "EPSG:4326", *b3857)),
        "grid": {"crs": "EPSG:3857", "width": int(hw), "height": int(hh), "bounds": list(b3857),
                 "full_resolution_size": [int(w), int(h)], "downsample_factor": f},
        "resampling": "nearest", "dates": dates, "T_db": T,
        "outlines": {"window_20km": {"type": "Polygon", "coordinates": [[[W, S], [E, S], [E, N], [W, N], [W, S]]]},
                     "box_60km": {"type": "Polygon", "coordinates": [outline_ll(*frame.BOX60_X, *frame.BOX60_Y, crs)]}},
        "layers": {"median": "forest_median.webp", "lost": "lost.webp", "first_switch": "first_switch.webp", "lost_patches": "lost.geojson"},
        "colors": {"forest": "#2f6b4f", "non_forest": "#b4401c", "lost": "#%02x%02x%02x" % LOST_COLOUR,
                   "transparent": "not valid on all 9 dates / not lost"},
        "first_switch_legend": [{"index": i, "date": dd, "colour": c} for i, (dd, c) in enumerate(zip(dates, SWITCH_COLOURS))],
        "first_switch_definition": "per block: the first pass from which the block is non-forest on that and every later pass (frame.first_switch_index); patch value = earliest over its blocks",
        "categories": CATEGORIES,
        "counts": {"blocks_valid_all_9": int(valid.sum()), "lost_blocks_all_valid": int(lost_all.sum()),
                   "lost_blocks_scored_area": n_scored, "patches_before_reduction": before, "patches_in_geojson": after,
                   "geojson_min_area_ha_applied": min_ha, "alert_window": [x.isoformat() for x in win],
                   "note": "maps and patches include the original 20 km window and the 60 km box; the scores do not"},
        "downsampled": (f"web images are nearest-neighbour downsampled by factor {f} from the full 100 m-block 3857 grid" if f > 1
                        else "web images are at full block resolution (factor 1, not downsampled)")
                       + ("; patches < 3 ha dropped to fit 15 MB" if min_ha else "; no patches dropped")
                       + ". lost.geojson hv_series_db = patch mean of block HV in dB.",
        "scores": json.loads(json.dumps(met)),
    }
    with open(f"{a.out_dir}/frame.json", "w") as fh:
        json.dump(meta, fh, indent=1)
    sizes["lost.geojson"], sizes["frame.json"] = gj_size, os.path.getsize(f"{a.out_dir}/frame.json")
    for k, v in sizes.items():
        print(f"{v:>10,d}  {k}")
    print(f"{sum(sizes.values()):>10,d}  total  ({hw} x {hh} px, factor {f}); patches {before} -> {after}")


if __name__ == "__main__":
    main()
