"""Sentinel-2 true-colour images for the "optical vs radar" section, one per NISAR date, on the radar map's grid.

For each of the 9 NISAR dates: the Sentinel-2 L2A acquisition date nearest in time within +/- 6 days over the 60 km box
(Earth Search STAC, the same search as s2_chips.py / cloud_blindness.py; one date = the MGRS tiles of that day,
mosaicked, first non-zero tile wins). True colour = B04/B03/B02 surface reflectance (DN * scale + offset from the
item's raster:bands), ONE fixed stretch for every date, no cloud masking (clouds are shown as they were). Pixels are
averaged (not sampled) from the 10 m bands onto EXACTLY the EPSG:3857 grid of web/data/explore/big/big.json
(forest_median.webp); pixels outside the 60 km box (UTM 22S, edges x 62360..122360, y 9061780..9121780) or without
data are transparent. clear_fraction = SCL 4, 5, 6 over the 600 x 600 block grid of the box, as cloud_blindness.py.

  python validation/optical_layers.py --big-json web/data/explore/big/big.json --out-dir web/data/explore/optical
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from pyproj import Transformer
from rasterio.transform import Affine, from_origin
from rasterio.warp import Resampling, reproject

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cloud_blindness  # noqa: E402
import s2_chips  # noqa: E402

os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
os.environ.setdefault("CPL_VSIL_CURL_ALLOWED_EXTENSIONS", ".tif")

TOL_DAYS = 6
BOX_X = (62360.0, 122360.0)  # the 60 km box, block edges, EPSG:32722
BOX_Y = (9061780.0, 9121780.0)
BLOCK_TF = from_origin(BOX_X[0], BOX_Y[1], 100.0, 100.0)
BLOCK_SHAPE = (600, 600)
REFL_MAX, GAMMA = 0.30, 0.5  # fixed stretch: reflectance 0..0.30, gamma 0.5, same for all dates
QUALITY = 75


def nearest_date(target: str, available: list[str], tol: int = TOL_DAYS):
    """(date, signed days = scene - target) of the available date nearest to target within tol days; earlier wins a tie."""
    t = dt.date.fromisoformat(target)
    best = None
    for a in sorted(available):
        d = (dt.date.fromisoformat(a) - t).days
        if abs(d) <= tol and (best is None or abs(d) < abs(best[1])):
            best = (a, d)
    return best


def stretch(refl: np.ndarray) -> np.ndarray:
    """Reflectance (float) -> uint8 with the fixed stretch."""
    return np.round(255 * np.clip(refl / REFL_MAX, 0, 1) ** GAMMA).astype(np.uint8)


def box_mask(transform: Affine, shape, crs_src: str = "EPSG:3857", crs_box: str = "EPSG:32722") -> np.ndarray:
    """True where a pixel centre of the (transform, shape) grid lies inside the 60 km box."""
    rows, cols = np.mgrid[0:shape[0], 0:shape[1]]
    x, y = transform * (cols + 0.5, rows + 0.5)
    bx, by = Transformer.from_crs(crs_src, crs_box, always_xy=True).transform(x, y)
    return (bx >= BOX_X[0]) & (bx <= BOX_X[1]) & (by >= BOX_Y[0]) & (by <= BOX_Y[1])


def band_refl(href: str, scale: float, offset: float, dst_tf: Affine, shape) -> np.ndarray:
    """Average a 10 m band onto the target grid; returns reflectance (NaN where there is no data)."""
    out = np.zeros(shape, np.float32)
    with rasterio.open(href) as src:
        reproject(rasterio.band(src, 1), out, dst_transform=dst_tf, dst_crs="EPSG:3857",
                  resampling=Resampling.average, src_nodata=0, dst_nodata=0)
    r = out * scale + offset
    return np.where(out > 0, r, np.nan).astype(np.float32)


def scale_offset(item: dict, asset: str) -> tuple[float, float]:
    """Reflectance = DN * scale. The item's raster:bands also says offset -0.1, but on these files dense-forest DN is
    ~180-740 (median 272 for B04, 2026-08-13 tile 21LYL; measured), i.e. 0.02-0.07 with scale alone and NEGATIVE with the
    offset, so the offset is not applied (recorded in optical.json)."""
    rb = item["assets"][asset]["raster:bands"][0]
    return float(rb["scale"]), 0.0


def true_colour(items: list[dict], dst_tf: Affine, shape) -> np.ndarray:
    """(h, w, 4) uint8 RGBA mosaic of the day's tiles; alpha 0 where no tile has data in all three bands."""
    rgb = np.full(shape + (3,), np.nan, np.float32)
    for it in items:
        bands = []
        for a in ("red", "green", "blue"):
            s, o = scale_offset(it, a)
            bands.append(band_refl(it["assets"][a]["href"], s, o, dst_tf, shape))
        arr = np.stack(bands, axis=-1)
        take = np.isnan(rgb).any(axis=-1) & np.isfinite(arr).all(axis=-1)
        rgb[take] = arr[take]
    ok = np.isfinite(rgb).all(axis=-1)
    out = np.zeros(shape + (4,), np.uint8)
    out[..., :3] = stretch(np.nan_to_num(rgb, nan=0.0))
    out[..., 3] = np.where(ok, 255, 0)
    return out


def clear_from_cloud_json(path: str, scene_date: str):
    """clear_fraction_aoi of that Sentinel-2 date from cloud.json (same rule, same box, same scenes), or None."""
    p = Path(path)
    if not p.exists():
        return None
    for s in json.loads(p.read_text()).get("scenes", []):
        if s["date"] == scene_date:
            return s["clear_fraction_aoi"]
    return None


def clear_fraction(items: list[dict]) -> tuple[float, float]:
    """(clear share SCL 4/5/6, share with no SCL data) over the 600 x 600 block grid of the box."""
    scl = cloud_blindness.mosaic([cloud_blindness.scl_on_grid(it["assets"]["scl"]["href"], BLOCK_TF, BLOCK_SHAPE, "EPSG:32722")
                                  for it in items])
    f = cloud_blindness.fractions(scl, np.ones(BLOCK_SHAPE, bool))
    return f["clear_fraction"], f["nodata_fraction"]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--big-json", default="web/data/explore/big/big.json")
    p.add_argument("--out-dir", default="web/data/explore/optical")
    p.add_argument("--cloud-json", default="web/data/explore/big/cloud.json",
                   help="reuse clear_fraction_aoi from cloud_blindness.py output (same rule and box); recompute from SCL if the date is missing")
    p.add_argument("--skip-existing", action="store_true", help="keep an existing optical_<date>.webp instead of rebuilding it")
    a = p.parse_args()
    big = json.loads(Path(a.big_json).read_text())
    g = big["grid"]
    if g["crs"] != "EPSG:3857":
        raise SystemExit("big.json grid is not EPSG:3857")
    w, h = g["width"], g["height"]
    dst_tf = Affine(*g["transform"][:3], *g["transform"][3:6]) if len(g["transform"]) >= 6 else None
    shape = (h, w)
    nisar = big["dates"]
    bbox = big["bounds_lonlat"]
    lo = (dt.date.fromisoformat(nisar[0]) - dt.timedelta(days=TOL_DAYS)).isoformat()
    hi = (dt.date.fromisoformat(nisar[-1]) + dt.timedelta(days=TOL_DAYS)).isoformat()
    by_date = cloud_blindness.dedupe(s2_chips.search(bbox, lo, hi))
    inside = box_mask(dst_tf, shape)
    Path(a.out_dir).mkdir(parents=True, exist_ok=True)

    def one(d: str) -> dict:
        n = nearest_date(d, list(by_date))
        if n is None:
            return {"nisar_date": d, "file": None, "scene_id": None, "note": f"no Sentinel-2 scene within {TOL_DAYS} days"}
        sd, gap = n
        items = by_date[sd]
        fn = f"optical_{d}.webp"
        if a.skip_existing and (Path(a.out_dir) / fn).exists():
            img = np.array(Image.open(Path(a.out_dir) / fn).convert("RGBA"))
        else:
            img = true_colour(items, dst_tf, shape)
            img[..., 3] = np.where(inside, img[..., 3], 0)
            Image.fromarray(img, "RGBA").save(Path(a.out_dir) / fn, "WEBP", quality=QUALITY)
        clear = clear_from_cloud_json(a.cloud_json, sd)
        src = "cloud.json (cloud_blindness.py)"
        nodata = None
        if clear is None:
            clear, nodata = clear_fraction(items)
            src = "SCL recomputed here"
        return {"nisar_date": d, "file": fn, "scene_id": "+".join(it["id"] for it in items), "date": sd,
                "days_apart": gap, "clear_fraction": round(clear, 4), "clear_fraction_source": src,
                "tiles": [it["id"].split("_")[1] for it in items],
                "has_data_share_of_box": round(float((img[..., 3][inside] > 0).mean()), 4)}

    passes = [one(d) for d in nisar]  # sequential: a thread pool hung at shutdown on this machine
    out = {"source": "Copernicus Sentinel-2 L2A (Earth Search STAC v1, sentinel-2-l2a), modified Copernicus Sentinel data 2026",
           "grid": g, "bounds_lonlat": bbox, "tolerance_days": TOL_DAYS,
           "rule": "nearest Sentinel-2 acquisition date within +/- 6 days of each NISAR date; the day's MGRS tiles mosaicked",
           "true_colour": f"B04/B03/B02 surface reflectance, fixed stretch 0..{REFL_MAX} gamma {GAMMA}, same for all dates; "
                          "10 m averaged onto the grid; NO cloud masking. reflectance = DN * 0.0001 with the catalogue offset (-0.1) NOT applied: "
                          "forest DN is ~180-740 (B04 median 272), which the offset would make negative",
           "clear_fraction": "share of the 60 km box with SCL 4, 5, 6 (cloud_blindness.py rule)",
           "webp_quality": QUALITY, "passes": passes,
           "command": f"python validation/optical_layers.py --big-json {a.big_json} --out-dir {a.out_dir} --cloud-json {a.cloud_json}"}
    (Path(a.out_dir) / "optical.json").write_text(json.dumps(out, indent=1))
    for r in passes:
        print(r["nisar_date"], r.get("date"), r.get("days_apart"), r.get("clear_fraction"), r.get("tiles"), r.get("has_data_share_of_box"))


if __name__ == "__main__":
    main()
