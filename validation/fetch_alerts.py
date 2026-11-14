"""Keyless alert download: GLAD-L and GLAD-S2 pixels from UMD's public GeoTIFFs, saved as score.py rows.

Reads:  the public bucket gs://earthenginepartners-hansen (HTTPS, no account), windowed reads with rasterio /vsicurl/.
Writes: one JSON list of rows per source, every alert pixel whose centre is inside --bbox, all dates, unfiltered:
        {longitude, latitude, area__ha, <dataset>__date, <dataset>__confidence, raw_alert, raw_date, layer}
        The field names match the GFW Data API query in score.py, so the file works with score.py --reference-file.

Encodings (see validation/README.md "Keyless alert files"):
- GLAD-L  GLADalert/C2/current/alert<YY>_<tile>.tif (0 none, 2 probable, 3 confirmed) and alertDate<YY>_<tile>.tif
  (day of year 20YY). 0.00025 deg. Confidence mapped 2 -> "nominal", 3 -> "high" (GFW's GLAD-L value table).
- GLAD-S2 S2alert/alert/<tile>.tif (values 1..4; meaning NOT documented in any source read, so __confidence is null
  and raw_alert is kept) and S2alert/alertDate/<tile>.tif (days since 2018-12-31; checked: all 111 distinct dates
  since 2025 in the Rondonia window fall on Sentinel-2 acquisition days with this epoch, 0 with 2019-01-01). 1e-4 deg.
RADD and GFW integrated alerts have no keyless source (GFW Data API key or Earth Engine needed).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json

import numpy as np
import rasterio
from pyproj import Geod
from rasterio.windows import Window, from_bounds

BUCKET = "/vsicurl/https://storage.googleapis.com/earthenginepartners-hansen"
TILE = "070W_10S_060W_00N"  # UMD 10x10 deg tile name: left-bottom / right-top corners; covers the Rondonia AOI
GLAD_L_CONF = {2: "nominal", 3: "high"}
S2_EPOCH = dt.date(2018, 12, 31)
GEOD = Geod(ellps="WGS84")


def read_window(url: str, bbox) -> tuple[np.ndarray, rasterio.Affine]:
    """Pixels of url whose centres lie inside bbox (W, S, E, N); returns (array, window transform)."""
    w, s, e, n = bbox
    with rasterio.open(url) as ds:
        win = from_bounds(w, s, e, n, ds.transform)
        c0, r0 = int(np.ceil(win.col_off - 0.5)), int(np.ceil(win.row_off - 0.5))
        c1 = int(np.floor(win.col_off + win.width - 0.5))
        r1 = int(np.floor(win.row_off + win.height - 0.5))
        win = Window(c0, r0, c1 - c0 + 1, r1 - r0 + 1)
        return ds.read(1, window=win), ds.window_transform(win)


def pixel_ha(lat: float, deg: float) -> float:
    """Geodesic area of a deg x deg pixel centred at latitude lat, in hectares."""
    lats = [lat - deg / 2, lat - deg / 2, lat + deg / 2, lat + deg / 2]
    return abs(GEOD.polygon_area_perimeter([0, deg, deg, 0], lats)[0]) / 1e4


def to_rows(alert, date, transform, dataset: str, layer: str, to_date, conf) -> list[dict]:
    """One row per nonzero pixel of `alert` (rows with a date of 0 are kept, date null, and counted by the caller)."""
    deg = transform.a
    rows = []
    for r, c in zip(*np.nonzero(alert)):
        lon, lat = transform * (c + 0.5, r + 0.5)
        raw_d = int(date[r, c])
        rows.append({
            "longitude": round(lon, 7), "latitude": round(lat, 7), "area__ha": round(pixel_ha(lat, deg), 6),
            f"{dataset}__date": to_date(raw_d).isoformat() if raw_d else None,
            f"{dataset}__confidence": conf(int(alert[r, c])),
            "raw_alert": int(alert[r, c]), "raw_date": raw_d, "layer": layer,
        })
    return rows


def glad_l(bbox, years=(25, 26)) -> list[dict]:
    rows = []
    for yy in years:
        a, t = read_window(f"{BUCKET}/GLADalert/C2/current/alert{yy}_{TILE}.tif", bbox)
        d, _ = read_window(f"{BUCKET}/GLADalert/C2/current/alertDate{yy}_{TILE}.tif", bbox)
        jan1 = dt.date(2000 + yy, 1, 1)
        rows += to_rows(a, d, t, "umd_glad_landsat_alerts", f"alert{yy}",
                        lambda doy, j=jan1: j + dt.timedelta(doy - 1), GLAD_L_CONF.get)
    return rows


def glad_s2(bbox) -> list[dict]:
    a, t = read_window(f"{BUCKET}/S2alert/alert/{TILE}.tif", bbox)
    d, _ = read_window(f"{BUCKET}/S2alert/alertDate/{TILE}.tif", bbox)
    return to_rows(a, d, t, "umd_glad_sentinel2_alerts", "S2alert",
                   lambda n: S2_EPOCH + dt.timedelta(n), lambda v: None)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--bbox", type=float, nargs=4, metavar=("W", "S", "E", "N"), required=True)
    p.add_argument("--out-dir", default="data")
    a = p.parse_args()
    for name, fn in (("glad_l", glad_l), ("glad_s2", glad_s2)):
        rows = fn(tuple(a.bbox))
        out = f"{a.out_dir}/alerts_{name}.json"
        with open(out, "w", encoding="utf-8") as f:
            json.dump(rows, f)
        undated = sum(1 for r in rows if r["raw_date"] == 0)
        print(f"{name}: {len(rows)} alert pixels ({undated} without a date) -> {out}")


if __name__ == "__main__":
    main()
