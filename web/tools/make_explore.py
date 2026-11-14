"""Build the files for web/explore.html from the per-date COGs that export_layers.py wrote.

Reads:  web/data/locations.json and web/data/<id>/{composite,hh,hv}_<date>.tif (uint8 EPSG:3857 COGs, 0 = no data).
Writes: web/data/explore/<id>/{composite,hh,hv}_<date>.webp        the same pixels as browser images (alpha = valid mask)
        web/data/explore/<id>/hvchg_<date>.webp, hhchg_<date>.webp   change preview: dB on this date minus the mean of the
                                                                    earlier dates (blue = drop, red = rise, +-3 dB scale)
        web/data/explore/<id>/series.bin                             uint8 [pol(hh,hv)][date][row][col] at 1/SERIES_STEP res
        web/data/explore/explore.json                                bounds (lon/lat), dates, stretch, series grid, notes

Honesty notes (also written into explore.json):
- dB values are recovered from the uint8 display stretch: dB = lo + (v - 1) / 254 * (hi - lo). Anything below lo or above
  hi was clipped by export_layers.py, so cleared ground (HV below lo) reads as lo. Drops are therefore UNDER-stated here.
- Change preview is a display product, not detect.py output. Final change layers / detections come from detect.py on the
  full-precision stack.
- "Stable radar forest" reference line = median of pixels whose HV is >= T_db (validation/fnf_metrics.json) on every date.
  It is a radar-defined class, not the Hansen forest mask.
"""
from __future__ import annotations

import json
import os

import numpy as np
import rasterio
from PIL import Image
from rasterio.warp import transform_bounds

WEB = os.path.join(os.path.dirname(__file__), "..")
SERIES_STEP = 4  # 20 m COG px (in 3857 ~19 m) -> ~80 m series cells
CHG_RANGE_DB = 3.0


def to_db(v: np.ndarray, lo: float, hi: float) -> np.ndarray:
    out = lo + (v.astype(np.float32) - 1.0) / 254.0 * (hi - lo)
    out[v == 0] = np.nan
    return out


def read(path: str):
    with rasterio.open(path) as d:
        return d.read(), d.read_masks(1), d.bounds, d.crs


def save_webp(rgb: np.ndarray, alpha: np.ndarray, path: str, lossless: bool = False) -> None:
    img = np.dstack([rgb[0], rgb[1], rgb[2], alpha]).astype(np.uint8)
    Image.fromarray(img, "RGBA").save(path, "WEBP", quality=82, lossless=lossless, method=6)


def change_rgb(d: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Diverging blue (drop) - white - red (rise); |d| < 1 dB transparent so the radar image shows through."""
    t = np.clip(np.nan_to_num(d) / CHG_RANGE_DB, -1, 1)
    r = np.where(t > 0, 255, 255 * (1 + t))
    g = 255 * (1 - np.abs(t))
    b = np.where(t < 0, 255, 255 * (1 - t))
    a = np.where(np.isfinite(d) & (np.abs(d) >= 1.0), np.clip(80 + 175 * np.abs(t), 0, 255), 0)
    return np.stack([r, g, b]).astype(np.uint8), a.astype(np.uint8)


def block_mean_db(db: np.ndarray, step: int) -> np.ndarray:
    """Mean in linear power over step x step blocks, back to dB."""
    h, w = (db.shape[0] // step) * step, (db.shape[1] // step) * step
    p = 10 ** (db[:h, :w] / 10)
    p = p.reshape(h // step, step, w // step, step)
    with np.errstate(invalid="ignore"):
        m = np.nanmean(p, axis=(1, 3))
    return 10 * np.log10(m)


def main() -> None:
    locs = json.load(open(os.path.join(WEB, "data", "locations.json")))["locations"]
    t_db = json.load(open(os.path.join(WEB, "..", "validation", "fnf_metrics.json")))["T_db"]
    out_root = os.path.join(WEB, "data", "explore")
    manifest = {"t_db_forest": t_db, "series_step": SERIES_STEP, "change_range_db": CHG_RANGE_DB, "locations": []}
    for loc in locs:
        lid, dates, st = loc["id"], loc["dates"], loc["stretch"]
        od = os.path.join(out_root, lid)
        os.makedirs(od, exist_ok=True)
        hh_all, hv_all = [], []
        bounds = None
        for date in dates:
            for kind in ("composite", "hh", "hv"):
                arr, mask, b, crs = read(os.path.join(WEB, loc["layers"][kind].replace("{date}", date)))
                if bounds is None:
                    bounds = transform_bounds(crs, "EPSG:4326", *b)
                    shape = arr.shape[1:]
                out = os.path.join(od, f"{kind}_{date}.webp")
                if not os.path.exists(out):
                    save_webp(arr, mask, out)
                if kind in ("hh", "hv"):
                    db = to_db(np.where(mask > 0, arr[0], 0), st[kind]["lo"], st[kind]["hi"])
                    (hh_all if kind == "hh" else hv_all).append(db)
        hh_all, hv_all = np.stack(hh_all), np.stack(hv_all)
        # series grid
        hh_s = np.stack([block_mean_db(x, SERIES_STEP) for x in hh_all])
        hv_s = np.stack([block_mean_db(x, SERIES_STEP) for x in hv_all])

        def q(x, lo, hi):
            v = np.round(1 + (x - lo) / (hi - lo) * 254)
            return np.where(np.isfinite(x), np.clip(v, 1, 255), 0).astype(np.uint8)

        # change preview on the ~80 m cells (noise ~0.4 dB per date at 20 m; averaging cuts speckle)
        for pol, stack in (("hh", hh_s), ("hv", hv_s)):
            lin = 10 ** (stack / 10)
            for i, date in enumerate(dates):
                if i == 0:
                    continue
                with np.errstate(invalid="ignore", divide="ignore"):
                    base = 10 * np.log10(np.nanmean(lin[:i], axis=0))
                rgb, a = change_rgb(stack[i] - base)
                save_webp(rgb, a, os.path.join(od, f"{pol}chg_{date}.webp"), lossless=True)
        ser = np.stack([q(hh_s, st["hh"]["lo"], st["hh"]["hi"]), q(hv_s, st["hv"]["lo"], st["hv"]["hi"])])
        ser.tofile(os.path.join(od, "series.bin"))
        # stable radar forest: HV >= T on every date (full-res), median per date
        stable = np.all(hv_all >= t_db, axis=0)
        ref = {
            "n_pixels": int(stable.sum()),
            "hh": [round(float(np.nanmedian(hh_all[i][stable])), 2) for i in range(len(dates))],
            "hv": [round(float(np.nanmedian(hv_all[i][stable])), 2) for i in range(len(dates))],
        }
        manifest["locations"].append({
            "id": lid, "name": loc["name"], "dates": dates, "center": loc["center"],
            "bounds_lonlat": [round(v, 6) for v in bounds],  # W S E N of the 3857 image
            "image_px": list(shape),
            "change_px": [int(ser.shape[2]), int(ser.shape[3])],  # change webps cover series_step*change_px image px
            "series_shape": [2, len(dates), int(ser.shape[2]), int(ser.shape[3])],
            "stretch": {k: {"lo": st[k]["lo"], "hi": st[k]["hi"]} for k in ("hh", "hv", "ratio")},
            "stable_forest_ref": ref,
            "notes": loc.get("notes", ""),
        })
        print(lid, "stable px", ref["n_pixels"], "series", ser.shape)
    json.dump(manifest, open(os.path.join(out_root, "explore.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
