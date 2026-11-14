"""Blind Sentinel-2 before / after chips for the hand-label sheet (reads the blind sheet only, never the key).

Source: Earth Search STAC v1 (https://earth-search.aws.element84.com/v1), collection sentinel-2-l2a, no login.
For each sheet point and side:
  candidates = scenes in [before_date - 30 d, before_date] ("before") or [after_date, after_date + 30 d] ("after");
  chip = 1 km x 1 km on the scene's UTM grid at 10 m (100 x 100 px; origin snapped to the 20 m SCL grid),
         centred on the point;
  cloud  = SCL 8, 9, 10 OR (blue reflectance > 0.07 AND blue / red > 0.8), grown by 3 px (clear forest and rivers
           here have blue <= 0.06; bright bare soil reaches 0.19 but is red, blue / red 0.44-0.77, while the
           cumulus SCL missed is white, 0.85-1.38, and as dim as blue 0.096 at its edge);
  shadow = SCL 3 OR (NIR < 0.15 AND NDWI(green, NIR) < 0 AND SCL != water), counted only when >= 0.1 % of the
           3 x 3 km around the chip is cloud (clear forest NIR here >= 0.15; shadows fall near clouds; clear
           scenes have <= 0.04 % stray bright-white pixels);
  These cloud / shadow thresholds were set by looking at these chips (a QC mask, not a science threshold);
  clean = no nodata in the chip, cloud + shadow < 10 % of the chip, no cloud or shadow in the 5 x 5 pixels
          (50 m) at the point, and median L2A aerosol optical thickness (AOT asset, 550 nm) over the chip <= 0.10.
  Why not SCL alone: on S Para, SCL said 0 % cloud on 2026-10-12 while AOT was 0.17-0.25 (smoke / haze: forest
  looked pale pink, readable as cleared land), and on 2026-11-11 it missed small cumulus and their shadows,
  one of them on a point (P22);
  pick = the clean candidate closest in time to the NISAR date (latest before, earliest after).
Reflectance = DN x scale. The items' raster:bands offset (-0.1) is not applied: it gives negative reflectance
(forest blue DN ~200), so these COGs evidently carry no +1000 DN offset.
A point without a clean scene on either side goes to missing.txt (next to --log, outside the labelers' folder) and
gets no chips (no other place substituted).
Before and after are rendered on the same grid with the same per-band 2-98 % stretch (computed over both chips),
upscaled x4 (nearest, 10 m pixels kept), with a small cross on the point. The scene date is only in the file name.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import rasterio
from PIL import Image
from pyproj import Transformer
from rasterio.windows import from_bounds
from scipy.ndimage import binary_dilation

STAC = "https://earth-search.aws.element84.com/v1/search"
COLLECTION = "sentinel-2-l2a"
CLOUD_SCL, SHADOW_SCL, WATER_SCL = (8, 9, 10), (3,), 6  # cloud medium / high, thin cirrus; cloud shadow; water
CHIP_M, CONTEXT_M, RES, SCALE_UP = 1000, 1000, 10, 4  # chip side; extra margin each side for the cloud context
MAX_CLOUD = 0.10
MAX_AOT = 0.10
CLOUD_BLUE, CLOUD_WHITE, SHADOW_NIR, GROW, CENTRE = 0.07, 0.8, 0.15, 3, 2
SHADOW_IF_CLOUD = 0.001  # context cloud fraction above which the dark-pixel shadow test applies
os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
os.environ.setdefault("CPL_VSIL_CURL_ALLOWED_EXTENSIONS", ".tif")


def search(bbox, start: str, end: str) -> list[dict]:
    body = {"collections": [COLLECTION], "bbox": bbox, "datetime": f"{start}T00:00:00Z/{end}T23:59:59Z", "limit": 100}
    items = []
    url, data = STAC, body
    while url:
        req = urllib.request.Request(url, data=json.dumps(data).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            fc = json.load(r)
        items += fc["features"]
        nxt = [lk for lk in fc.get("links", []) if lk["rel"] == "next"]
        url, data = (nxt[0]["href"], nxt[0].get("body", data)) if nxt else (None, None)
    return items


def chip_bounds(lon: float, lat: float, epsg: int) -> tuple[float, float, float, float]:
    x, y = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True).transform(lon, lat)
    x0, y0 = round((x - CHIP_M / 2) / 20) * 20, round((y - CHIP_M / 2) / 20) * 20
    return x0, y0, x0 + CHIP_M, y0 + CHIP_M


def read(href: str, bounds, shape=None) -> np.ndarray:
    with rasterio.open(href) as src:
        a = src.read(1, window=from_bounds(*bounds, src.transform), boundless=True, fill_value=0)
    if shape is not None and a.shape != shape:
        raise ValueError(f"{href}: window {a.shape} != {shape}")
    return a


def item_epsg(item: dict) -> int:
    p = item["properties"]
    return int(p.get("proj:epsg") or str(p["proj:code"]).split(":")[1])


def load_chip(item: dict, lon: float, lat: float) -> dict:
    epsg = item_epsg(item)
    b = chip_bounds(lon, lat, epsg)
    ctx = (b[0] - CONTEXT_M, b[1] - CONTEXT_M, b[2] + CONTEXT_M, b[3] + CONTEXT_M)
    n, m = CHIP_M // RES, CONTEXT_M // RES  # chip size and context margin in 10 m pixels
    N = n + 2 * m
    scl = np.repeat(np.repeat(read(item["assets"]["scl"]["href"], ctx, (N // 2, N // 2)), 2, 0), 2, 1)
    refl = {}
    for band in ("red", "green", "blue", "nir"):
        dn = read(item["assets"][band]["href"], ctx, (N, N)).astype(float)
        refl[band] = np.where(dn == 0, np.nan, dn * item["assets"][band]["raster:bands"][0].get("scale", 1))
    with np.errstate(invalid="ignore"):
        bright = (refl["blue"] > CLOUD_BLUE) & (refl["blue"] > CLOUD_WHITE * refl["red"])
        cloud = binary_dilation(np.isin(scl, CLOUD_SCL) | bright, iterations=GROW)
        ndwi = (refl["green"] - refl["nir"]) / (refl["green"] + refl["nir"])
        dark = (refl["nir"] < SHADOW_NIR) & (ndwi < 0) & (scl != WATER_SCL)
    shadow = np.isin(scl, SHADOW_SCL) | (dark if cloud.mean() >= SHADOW_IF_CLOUD else False)
    bad = (cloud | shadow)[m:m + n, m:m + n]
    nodata = ((scl == 0) | np.isnan(refl["red"]))[m:m + n, m:m + n]
    c = n // 2
    ra = item["assets"]["aot"]["raster:bands"][0]
    aot = read(item["assets"]["aot"]["href"], b).astype(float)
    aot = float(np.median(aot[aot > 0]) * ra.get("scale", 1) + ra.get("offset", 0)) if (aot > 0).any() else np.nan
    return {"item": item["id"], "date": item["properties"]["datetime"][:10], "epsg": epsg, "bounds": b,
            "scene_cloud": item["properties"].get("eo:cloud_cover"), "aot": aot,
            "rgb": np.stack([refl[k][m:m + n, m:m + n] for k in ("red", "green", "blue")], -1),
            "nodata_frac": float(nodata.mean()), "cloud_frac": float(bad.mean()),
            "cloud_only_frac": float(cloud[m:m + n, m:m + n].mean()),
            "centre_clear": bool(not (bad | nodata)[c - CENTRE:c + CENTRE + 1, c - CENTRE:c + CENTRE + 1].any()),
            "scl_counts": {int(k): int(v) for k, v in zip(*np.unique(scl[m:m + n, m:m + n], return_counts=True))}}


def clean(ch: dict) -> bool:
    return ch["nodata_frac"] == 0 and ch["cloud_frac"] < MAX_CLOUD and ch["centre_clear"] and ch["aot"] <= MAX_AOT


def render(rgb: np.ndarray, lo: np.ndarray, hi: np.ndarray, path: str) -> None:
    img = np.clip((rgb - lo) / (hi - lo), 0, 1)
    img = (np.nan_to_num(img) * 255).astype(np.uint8)
    img = np.repeat(np.repeat(img, SCALE_UP, 0), SCALE_UP, 1)
    c, arm, gap = img.shape[0] // 2, 14, 4
    for d in range(gap, arm):
        for s in (-1, 1):
            img[c + s * d, c - 1:c + 1] = img[c - 1:c + 1, c + s * d] = (255, 0, 255)
    Image.fromarray(img).save(path)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--sheet", required=True, help="blind label sheet (id, lon, lat, before_date, after_date, ...)")
    p.add_argument("--out-dir", required=True, help="new folder: PNGs and labels.csv only")
    p.add_argument("--log", required=True, help="JSON log of every candidate (written OUTSIDE --out-dir)")
    p.add_argument("--days", type=int, default=30)
    a = p.parse_args()
    if os.path.exists(a.out_dir):
        raise SystemExit(f"{a.out_dir} exists; it must be a new folder")
    with open(a.sheet, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    lons, lats = [float(r["lon"]) for r in rows], [float(r["lat"]) for r in rows]
    bbox = [min(lons) - 0.01, min(lats) - 0.01, max(lons) + 0.01, max(lats) + 0.01]
    day = lambda s, k: (dt.date.fromisoformat(s) + dt.timedelta(days=k)).isoformat()  # noqa: E731
    windows = {"before": {}, "after": {}}
    for r in rows:
        for side, key, k0, k1 in (("before", "before_date", -a.days, 0), ("after", "after_date", 0, a.days)):
            w = (day(r[key], k0), day(r[key], k1))
            if w not in windows[side]:
                windows[side][w] = search(bbox, *w)
                print(f"{side} {w}: {len(windows[side][w])} scenes")
    os.makedirs(a.out_dir)

    def pick_point(r: dict) -> tuple[dict, list[dict]]:
        pick, tried = {}, []
        for side, key, k0, k1 in (("before", "before_date", -a.days, 0), ("after", "after_date", 0, a.days)):
            items = windows[side][(day(r[key], k0), day(r[key], k1))]
            items = sorted(items, key=lambda it: it["properties"]["datetime"], reverse=(side == "before"))
            for it in items:
                ch = load_chip(it, float(r["lon"]), float(r["lat"]))
                tried.append({"id": r["id"], "side": side, **{k: v for k, v in ch.items() if k != "rgb"},
                              "clean": clean(ch)})
                if clean(ch):
                    pick[side] = ch
                    break
        return pick, tried

    with ThreadPoolExecutor(8) as ex:
        picks = list(ex.map(pick_point, rows))
    log, built, missing = [t for _, tried in picks for t in tried], [], []
    for r, (pick, _) in zip(rows, picks):
        lon, lat = float(r["lon"]), float(r["lat"])
        if len(pick) < 2 or pick["before"]["bounds"] != pick["after"]["bounds"]:
            why = ", ".join(f"no clean {s} scene in the window" for s in ("before", "after") if s not in pick) or \
                "before / after scenes on different grids"
            missing.append(f"{r['id']},{lon},{lat},{why}")
            continue
        both = np.concatenate([pick["before"]["rgb"].reshape(-1, 3), pick["after"]["rgb"].reshape(-1, 3)])
        lo, hi = np.nanpercentile(both, 2, axis=0), np.nanpercentile(both, 98, axis=0)
        for side in ("before", "after"):
            render(pick[side]["rgb"], lo, hi, os.path.join(a.out_dir, f"{r['id']}_{side}_{pick[side]['date']}.png"))
        built.append({"id": r["id"], "lon": r["lon"], "lat": r["lat"],
                      **{f"{s}_{k}": pick[s][k] for s in ("before", "after")
                         for k in ("item", "date", "scene_cloud", "cloud_frac", "aot")}})
        print(f"{r['id']}: " + " | ".join(f"{s} {pick[s]['date']} chip cloud {pick[s]['cloud_frac']:.1%} "
                                         f"AOT {pick[s]['aot']:.2f}" for s in ("before", "after")))
    with open(os.path.join(a.out_dir, "labels.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "lon", "lat", "label", "notes"])
        w.writerows([b["id"], b["lon"], b["lat"], "", ""] for b in built)
    if missing:
        with open(os.path.join(os.path.dirname(os.path.abspath(a.log)), "missing.txt"), "w", encoding="utf-8") as f:
            f.write("id,lon,lat,reason\n" + "\n".join(missing) + "\n")
    with open(a.log, "w", encoding="utf-8") as f:
        json.dump({"stac": STAC, "collection": COLLECTION, "built": built, "missing": missing, "candidates": log},
                  f, indent=1)
    print(f"pairs built {len(built)}, missing {len(missing)}")


if __name__ == "__main__":
    main()
