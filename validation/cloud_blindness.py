"""Cloud-blindness counter: how often Sentinel-2 actually sees the 60 km AOI, vs NISAR's 9 usable passes.

Source: Earth Search STAC v1, collection sentinel-2-l2a (the same source and search as s2_chips.py), every item
intersecting the AOI box with a date in 2026-06-26..2026-10-12. Items are grouped by acquisition date (one pass = the
MGRS tiles of that day, mosaicked); a duplicated tile/date keeps the item with the latest `updated` time.

Per pass, the scene classification (SCL, 20 m) of each tile is resampled by mode onto the big stack's 100 m block grid
(EPSG:32722, 600 x 600) and mosaicked (first non-zero tile wins). Clear = SCL 4, 5, 6 (vegetation, bare soil, water).
Not clear = everything else: 3 cloud shadow, 8 / 9 cloud medium / high probability, 10 thin cirrus, and also
0 no data, 1 saturated, 2 dark, 7 unclassified, 11 snow (counted separately so the cloud share is visible).
clear_fraction = clear blocks / all blocks of the area, reported for
  - aoi: the whole 60 x 60 km block grid (the requested AOI), and
  - nisar_footprint: the 199,204 blocks NISAR saw on all 9 passes (same ground as the forest map).
SCL alone is used, as specified; s2_chips.py documents that SCL misses haze/smoke and some small cumulus
(S Para 2026-10-12, 2026-11-11), so these clear fractions are upper bounds on usable optical views.

  python validation/cloud_blindness.py --stack data/stack_big_t2f174.nc --out validation/cloud_blindness.json \
    --web-out web/data/explore/big/cloud.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import rasterio
import xarray as xr
from pyproj import Transformer
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject

sys.path.insert(0, str(Path(__file__).resolve().parent))
import s2_chips  # noqa: E402  (STAC search reused unchanged)

START, END = "2026-06-26", "2026-10-12"
CLEAR_SCL = (4, 5, 6)
CLOUDY_SCL = (3, 8, 9, 10)
GOOD = 0.80
NISAR_PASSES = ["2026-06-26", "2026-07-08", "2026-07-20", "2026-08-13", "2026-08-25",
                "2026-09-06", "2026-09-18", "2026-09-30", "2026-10-12"]
os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
os.environ.setdefault("CPL_VSIL_CURL_ALLOWED_EXTENSIONS", ".tif")


def dedupe(items: list[dict]) -> dict[str, list[dict]]:
    """{date: [items]}, one item per MGRS tile and date (latest `updated` wins)."""
    best: dict[tuple[str, str], dict] = {}
    for it in items:
        p = it["properties"]
        k = (p["datetime"][:10], p.get("grid:code") or it["id"].split("_")[1])
        if k not in best or p.get("updated", "") > best[k]["properties"].get("updated", ""):
            best[k] = it
    out: dict[str, list[dict]] = {}
    for (d, _), it in sorted(best.items()):
        out.setdefault(d, []).append(it)
    return out


def scl_on_grid(href: str, dst_transform, shape, dst_crs: str) -> np.ndarray:
    out = np.zeros(shape, np.uint8)
    with rasterio.open(href) as src:
        reproject(rasterio.band(src, 1), out, dst_transform=dst_transform, dst_crs=dst_crs,
                  resampling=Resampling.mode, src_nodata=0, dst_nodata=0)
    return out


def mosaic(layers: list[np.ndarray]) -> np.ndarray:
    m = np.zeros_like(layers[0])
    for a in layers:
        m = np.where(m == 0, a, m)
    return m


def fractions(scl: np.ndarray, area: np.ndarray) -> dict:
    n = int(area.sum())
    v = scl[area]
    return {"clear_fraction": float(np.isin(v, CLEAR_SCL).sum() / n),
            "cloud_shadow_cirrus_fraction": float(np.isin(v, CLOUDY_SCL).sum() / n),
            "nodata_fraction": float((v == 0).sum() / n),
            "other_fraction": float((~np.isin(v, CLEAR_SCL + CLOUDY_SCL + (0,))).sum() / n)}


def longest_gap(good_dates: list[str], start: str = START, end: str = END) -> dict:
    """Longest run of days without a good view, counting the window ends as boundaries."""
    pts = [dt.date.fromisoformat(start)] + [dt.date.fromisoformat(d) for d in good_dates] + [dt.date.fromisoformat(end)]
    gaps = [((b - a).days, a.isoformat(), b.isoformat()) for a, b in zip(pts, pts[1:])]
    between = [g for g in gaps[1:-1]] if len(good_dates) >= 2 else []
    g_all = max(gaps)
    g_between = max(between) if between else None
    return {"longest_gap_days_between_good_views": g_between[0] if g_between else None,
            "between": g_between[1:] if g_between else None,
            "longest_gap_days_incl_window_ends": g_all[0], "incl_window_ends_between": list(g_all[1:])}


def summarise(rows: list[dict], key: str) -> dict:
    cf = [r[key]["clear_fraction"] for r in rows]
    good = [r["date"] for r in rows if r[key]["clear_fraction"] >= GOOD]
    return {"n_scenes": len(rows), "n_ge_80pct_clear": len(good), "good_dates": good,
            "median_clear_fraction": float(np.median(cf)) if cf else None, **longest_gap(good)}


def run(stack: str) -> tuple[dict, dict]:
    ds = xr.open_dataset(stack)
    xc, yc, crs = ds["x"].values, ds["y"].values, ds.attrs["crs"]
    d = float(xc[1] - xc[0])
    tf = from_origin(xc[0] - d / 2, yc[0] + d / 2, d, d)
    shape = (yc.size, xc.size)
    footprint = np.isfinite(ds["hv_db"].values).all(axis=0)
    aoi = np.ones(shape, bool)
    xx, yy = np.meshgrid([xc[0] - d / 2, xc[-1] + d / 2], [yc[0] + d / 2, yc[-1] - d / 2])
    lon, lat = Transformer.from_crs(crs, 4326, always_xy=True).transform(xx, yy)
    bbox = [float(lon.min()), float(lat.min()), float(lon.max()), float(lat.max())]
    items = s2_chips.search(bbox, START, END)
    by_date = dedupe(items)

    def one(date: str) -> dict:
        its = by_date[date]
        scl = mosaic([scl_on_grid(it["assets"]["scl"]["href"], tf, shape, crs) for it in its])
        return {"date": date, "items": [it["id"] for it in its], "aoi": fractions(scl, aoi),
                "nisar_footprint": fractions(scl, footprint)}

    with ThreadPoolExecutor(8) as ex:
        rows = list(ex.map(one, sorted(by_date)))
    out = {
        "source": {"stac": s2_chips.STAC, "collection": s2_chips.COLLECTION, "search_bbox_wsen": bbox,
                   "dates": [START, END], "items_returned": len(items),
                   "items_after_dedupe": sum(len(v) for v in by_date.values())},
        "rule": {"clear_scl": list(CLEAR_SCL), "not_clear": "all other SCL classes (cloudy = 3, 8, 9, 10)",
                 "grid": f"stack block grid {crs}, {d:.0f} m, SCL resampled by mode, tiles mosaicked per date",
                 "good_view": f"clear_fraction >= {GOOD}",
                 "caveat": "SCL only; s2_chips.py found SCL misses haze/smoke and small cumulus, so these are upper bounds"},
        "areas": {"aoi_blocks": int(aoi.sum()), "nisar_footprint_blocks": int(footprint.sum())},
        "sentinel2": {"aoi": summarise(rows, "aoi"), "nisar_footprint": summarise(rows, "nisar_footprint")},
        "nisar": {"passes": len(NISAR_PASSES), "usable": len(NISAR_PASSES), "dates": NISAR_PASSES,
                  "note": "9 of 9 passes usable over the NISAR footprint (all 9 dates in the stack; L-band is not blocked by cloud). "
                          "NISAR covers the footprint only (55.3 % of the 60 km box; the swath edge cuts the west).",
                  "longest_gap_days": max((dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days
                                          for a, b in zip(NISAR_PASSES, NISAR_PASSES[1:]))},
        "per_scene": rows,
        "command": "python validation/cloud_blindness.py --stack data/stack_big_t2f174.nc --out validation/cloud_blindness.json "
                   "--web-out web/data/explore/big/cloud.json",
    }
    web = {"source": "Sentinel-2 L2A SCL via Earth Search STAC (validation/cloud_blindness.json)",
           "good_threshold": GOOD, "nisar_passes": NISAR_PASSES,
           "scenes": [{"date": r["date"], "clear_fraction_aoi": round(r["aoi"]["clear_fraction"], 4),
                       "clear_fraction_nisar_footprint": round(r["nisar_footprint"]["clear_fraction"], 4)} for r in rows],
           "summary": {k: {kk: v[kk] for kk in ("n_scenes", "n_ge_80pct_clear", "median_clear_fraction",
                                                  "longest_gap_days_between_good_views")}
                       for k, v in out["sentinel2"].items()}}
    return out, web


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--stack", default="data/stack_big_t2f174.nc")
    p.add_argument("--out", default="validation/cloud_blindness.json")
    p.add_argument("--web-out", default="web/data/explore/big/cloud.json")
    a = p.parse_args()
    out, web = run(a.stack)
    Path(a.out).write_text(json.dumps(out, indent=1))
    Path(a.web_out).write_text(json.dumps(web, indent=1))
    print(json.dumps({"sentinel2": out["sentinel2"], "nisar": out["nisar"], "areas": out["areas"]}, indent=1))
    for r in out["per_scene"]:
        print(r["date"], f"aoi clear {r['aoi']['clear_fraction']:.3f} cloud {r['aoi']['cloud_shadow_cirrus_fraction']:.3f} "
              f"nodata {r['aoi']['nodata_fraction']:.3f} | footprint clear {r['nisar_footprint']['clear_fraction']:.3f}")


if __name__ == "__main__":
    main()
