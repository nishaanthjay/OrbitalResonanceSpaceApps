"""Web patches: merge the per-date final detections into one polygon per clearing patch, with dB time series.

Reads:  final detections (CONTRACTS.md section 2, one feature per detection date; as scored by validation/score.py)
        and the stack (CONTRACTS.md section 1; 5x5 multilook like detect.py, from the full-precision stack, never from
        the display images).
Writes: web/data/detections.geojson: one Polygon (EPSG:4326) per patch = 8-connected pixels covered by detections of any
        date. Properties: id, date (= first_date, kept for CONTRACTS.md), first_date, stage, area_ha, d_hh, d_hv,
        first_hh_date, first_hv_date, split ("tune" | "holdout" | "buffer", by the polygon's representative point),
        hh_series_db, hv_series_db (one value per stack date, in stack order; mean dB over the patch's pixels; null if NaN).
Rules:  first_date = earliest detection date of any pixel of the patch. stage = "late" if at least half of the patch's pixels
        detected on first_date are HV-led (same half rule as detect.py), else "early". d_hh / d_hv = patch means of the raw
        change (first_date minus baseline). area_ha = pixel count x real pixel area. first_hh_date / first_hv_date = the
        earliest non-null value among the merged detections.
The scored detections file is not changed: metrics.json counts per-date detections, this file merges them for display.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
import xarray as xr
from pyproj import Transformer
from rasterio.features import geometry_mask, shapes
from scipy import ndimage
from shapely.geometry import mapping, shape
from shapely.ops import transform as shp_transform

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from detect import STAGE_EARLY, STAGE_LATE, _with_crs, bbox_mask, change_maps, multilook, pixel_area_ha  # noqa: E402


def _num(v: float) -> float | None:
    return None if not np.isfinite(v) else round(float(v), 2)


def build_patches(stack: xr.Dataset, detections: dict, tune_bbox=None, holdout_bbox=None, n_looks: int = 5) -> dict:
    """GeoJSON FeatureCollection of merged patches (see module docstring)."""
    ml = multilook(stack, n_looks)
    crs = stack.attrs["crs"]
    tmpl = _with_crs(ml["hh_db"].isel(time=0), crs)
    ny, nx = tmpl.shape
    transform = tmpl.rio.transform()
    to_stack = Transformer.from_crs(4326, crs, always_xy=True).transform
    to_ll = Transformer.from_crs(crs, 4326, always_xy=True).transform
    dates = [str(t)[:10] for t in ml["time"].values]

    # per detection date: pixels covered, stage code, and the optional first_hh/first_hv dates
    covered, stage_code = {}, {}
    first_hh, first_hv = np.full((ny, nx), "", dtype="<U10"), np.full((ny, nx), "", dtype="<U10")
    for f in detections["features"]:
        d = f["properties"]["date"]
        poly = shp_transform(to_stack, shape(f["geometry"]))
        inside = ~geometry_mask([poly], out_shape=(ny, nx), transform=transform, all_touched=False)
        covered.setdefault(d, np.zeros((ny, nx), bool))
        stage_code.setdefault(d, np.zeros((ny, nx), np.int8))
        covered[d] |= inside
        stage_code[d][inside] = STAGE_LATE if f["properties"]["stage"] == "late" else STAGE_EARLY
        for arr, key in ((first_hh, "first_hh_date"), (first_hv, "first_hv_date")):
            v = f["properties"].get(key)
            if v:
                cur = arr[inside]
                arr[inside] = np.where((cur == "") | (cur > v), v, cur)

    union = np.zeros((ny, nx), bool)
    for m in covered.values():
        union |= m
    labels, n = ndimage.label(union, structure=np.ones((3, 3), dtype=int))
    area = pixel_area_ha(tmpl)
    hh_all, hv_all = ml["hh_db"].values, ml["hv_db"].values
    raw = {d: change_maps(ml, d) for d in sorted(covered)}  # raw change vs the mean of earlier dates, as detect.py
    tune = bbox_mask(tmpl, tuple(tune_bbox)) if tune_bbox else None
    hold = bbox_mask(tmpl, tuple(holdout_bbox)) if holdout_bbox else None

    feats = []
    for lab_id in range(1, n + 1):
        px = labels == lab_id
        first = min(d for d, m in covered.items() if (m & px).any())
        at_first = px & covered[first]
        late_share = float((stage_code[first][at_first] == STAGE_LATE).mean())
        hh_dates = first_hh[px][first_hh[px] != ""]
        hv_dates = first_hv[px][first_hv[px] != ""]
        d_hh, d_hv = raw[first]
        geom = shape(next(g for g, v in shapes(labels.astype(np.int32), mask=px, transform=transform, connectivity=8)))
        rp = shp_transform(to_ll, geom).representative_point()
        # split membership by the representative point, as validation/score.py does
        ix = int(np.argmin(np.abs(tmpl["x"].values - rp_xy(to_stack, rp)[0])))
        iy = int(np.argmin(np.abs(tmpl["y"].values - rp_xy(to_stack, rp)[1])))
        part = "tune" if tune is not None and bool(tune.values[iy, ix]) else \
               "holdout" if hold is not None and bool(hold.values[iy, ix]) else "buffer"
        feats.append({
            "geometry": mapping(shp_transform(to_ll, geom)), "first": first, "px_count": int(px.sum()),
            "props": {
                "date": first, "first_date": first, "stage": "late" if late_share >= 0.5 else "early",
                "area_ha": round(float(area[px].sum()), 2),
                "d_hh": round(float(d_hh.values[px].mean()), 3), "d_hv": round(float(d_hv.values[px].mean()), 3),
                "first_hh_date": min(hh_dates.tolist()) if hh_dates.size else None,
                "first_hv_date": min(hv_dates.tolist()) if hv_dates.size else None,
                "split": part,
                "hh_series_db": [_num(np.nanmean(hh_all[i][px])) for i in range(len(dates))],
                "hv_series_db": [_num(np.nanmean(hv_all[i][px])) for i in range(len(dates))],
            }})
    feats.sort(key=lambda f: (f["first"], f["geometry"]["coordinates"][0][0]))
    out = []
    for i, f in enumerate(feats, start=1):
        out.append({"type": "Feature", "geometry": f["geometry"], "properties": {"id": i, **f["props"]}})
    return {"type": "FeatureCollection", "series_dates": dates, "features": out}


def patch_summary(fc: dict, tuning: dict | None) -> dict:
    """summary.json (CONTRACTS.md section 6) computed from the merged patches, so the panel agrees with the map.

    One row per first_date (a patch counts once, on the date it first appeared): n_detections = patches, total_area_ha,
    early_ha / late_ha by the patch's stage. `dates` = the stack dates the series use. `tuning` is copied from detect's summary.
    """
    rows = {}
    for f in fc["features"]:
        p = f["properties"]
        r = rows.setdefault(p["first_date"], {"date": p["first_date"], "n_detections": 0, "total_area_ha": 0.0,
                                               "early_ha": 0.0, "late_ha": 0.0})
        r["n_detections"] += 1
        r["total_area_ha"] += p["area_ha"]
        r[f"{p['stage']}_ha"] += p["area_ha"]
    per_date = [{**r, **{k: round(r[k], 2) for k in ("total_area_ha", "early_ha", "late_ha")}} for _, r in sorted(rows.items())]
    return {"dates": fc["series_dates"], "per_date": per_date, "tuning": tuning}


def rp_xy(to_stack, pt) -> tuple[float, float]:
    """Stack-CRS (x, y) of a shapely point given in lon/lat."""
    return to_stack(pt.x, pt.y)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--stack", required=True)
    p.add_argument("--detections", required=True, help="final per-date detections.geojson (as scored)")
    p.add_argument("--tune-bbox", type=float, nargs=4, metavar=("W", "S", "E", "N"))
    p.add_argument("--holdout-bbox", type=float, nargs=4, metavar=("W", "S", "E", "N"))
    p.add_argument("--multilook", type=int, default=5)
    p.add_argument("--out", default="web/data/detections.geojson")
    p.add_argument("--summary-out", help="also write summary.json computed from the patches")
    p.add_argument("--tuning-from", help="detect's summary.json, whose `tuning` block is copied (required with --summary-out)")
    a = p.parse_args()
    if a.summary_out and not a.tuning_from:
        p.error("--summary-out needs --tuning-from")
    stack = xr.open_dataset(a.stack)
    with open(a.detections, encoding="utf-8") as f:
        det = json.load(f)
    fc = build_patches(stack, det, a.tune_bbox, a.holdout_bbox, a.multilook)
    stack.close()
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(fc, f)
    if a.summary_out:
        with open(a.tuning_from, encoding="utf-8") as f:
            tuning = json.load(f).get("tuning")
        with open(a.summary_out, "w", encoding="utf-8") as f:
            json.dump(patch_summary(fc, tuning), f, indent=1)
    n_by = {s: sum(1 for x in fc["features"] if x["properties"]["split"] == s) for s in ("tune", "holdout", "buffer")}
    print(f"{len(det['features'])} per-date detections -> {len(fc['features'])} patches {n_by} -> {a.out}")


if __name__ == "__main__":
    main()
