"""Stratified random sample for hand labeling: N detections + N non-detected forest points -> CSV.

Reads:  web/data/detections.geojson (CONTRACTS.md section 2) and the binary forest-mask GeoTIFF used by detect.
Writes: a CSV with columns id, stratum, lon, lat, date, detection_id, label, notes (label and notes empty, to be
        filled by a person following validation/README.md; then run compute_sample_precision.py).
        With --blind BEFORE AFTER: a labeling sheet id, lon, lat, before_date, after_date, label, notes that does
        not reveal which rows are detections, and a separate --key file (compute_sample_precision.py --key).
"""
from __future__ import annotations

import argparse
import csv
import json

import numpy as np
import rasterio
from pyproj import CRS, Transformer
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds
from shapely import STRtree, contains_xy
from shapely.geometry import Point, shape

from score import in_holdout, make_holdout

COLUMNS = ["id", "stratum", "lon", "lat", "date", "detection_id", "label", "notes"]
BLIND_COLUMNS = ["id", "lon", "lat", "before_date", "after_date", "label", "notes"]
KEY_COLUMNS = ["id", "sample_id", "stratum", "date", "detection_id"]


def _random_point_in(geom, rng: np.random.Generator, tries: int = 10000) -> tuple[float, float]:
    """Uniform point inside a lon/lat polygon by rejection sampling in its bounds."""
    w, s, e, n = geom.bounds
    for _ in range(tries):
        x, y = rng.uniform(w, e), rng.uniform(s, n)
        if contains_xy(geom, x, y):
            return float(x), float(y)
    raise RuntimeError("could not place a point inside a detection polygon")


def sample_points(
    det: dict,
    forest: np.ndarray,
    transform,
    crs,
    n: int = 15,
    seed: int = 0,
    holdout: dict | None = None,
) -> list[dict]:
    """N random detections (one uniform point inside each) and N random forest pixels outside every detection.

    det: detections FeatureCollection (EPSG:4326). forest: 2-D boolean array with its affine `transform` and
    `crs`. holdout (from score.make_holdout) limits both strata to the holdout split. Non-detected points are
    forest pixel centres inside the holdout bbox (if any) and outside all (holdout) detection polygons; their
    `date` is the last scored date. Fewer than N rows per stratum are returned if fewer exist.
    """
    rng = np.random.default_rng(seed)
    feats = [f for f in det["features"] if holdout is None or in_holdout(f, holdout)]
    rows = []
    for k, i in enumerate(sorted(rng.choice(len(feats), size=min(n, len(feats)), replace=False)), start=1):
        f = feats[i]
        lon, lat = _random_point_in(shape(f["geometry"]), rng)
        rows.append({"id": f"D{k:02d}", "stratum": "detection", "lon": round(lon, 6), "lat": round(lat, 6),
                     "date": f["properties"]["date"], "detection_id": f["properties"].get("id"), "label": "",
                     "notes": ""})

    dates = sorted({f["properties"]["date"] for f in feats} | set((holdout or {}).get("dates", [])))
    last = dates[-1] if dates else ""
    tree = STRtree([shape(f["geometry"]) for f in feats])
    to4326 = Transformer.from_crs(CRS.from_user_input(crs), 4326, always_xy=True).transform
    rr, cc = np.nonzero(np.asarray(forest, bool))
    order = rng.permutation(len(rr))
    k = 0
    for j in order:
        if k >= n:
            break
        x, y = transform * (cc[j] + 0.5, rr[j] + 0.5)  # pixel centre
        lon, lat = to4326(x, y)
        if holdout and "bbox" in holdout:
            w, s, e, nn = holdout["bbox"]
            if not (w <= lon <= e and s <= lat <= nn):
                continue
        if len(tree.query(Point(lon, lat), predicate="intersects")):
            continue  # inside (or on the edge of) a detection
        k += 1
        rows.append({"id": f"N{k:02d}", "stratum": "non_detection", "lon": round(lon, 6), "lat": round(lat, 6),
                     "date": last, "detection_id": "", "label": "", "notes": ""})
    return rows


def make_blind(rows: list[dict], before: str, after: str, seed: int) -> tuple[list[dict], list[dict]]:
    """Split sample rows into a blind labeling sheet and a separate key.

    The sheet has no column that tells the strata apart: rows are shuffled, renamed P01.. in the new order, and
    every row gets the same before / after dates (the whole stack period). The key maps each P id back to the
    original id, stratum, date and detection_id.
    """
    rng = np.random.default_rng(seed + 1)  # not the sampling stream, so the sample itself is unchanged
    order = rng.permutation(len(rows))
    sheet, key = [], []
    for k, i in enumerate(order, start=1):
        r, pid = rows[i], f"P{k:02d}"
        sheet.append({"id": pid, "lon": r["lon"], "lat": r["lat"], "before_date": before, "after_date": after,
                      "label": "", "notes": ""})
        key.append({"id": pid, "sample_id": r["id"], "stratum": r["stratum"], "date": r["date"],
                    "detection_id": r["detection_id"]})
    return sheet, key


def write_csv(rows: list[dict], path: str, columns: list[str] = COLUMNS) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        w.writerows(rows)


def read_forest(path: str, bbox=None) -> tuple[np.ndarray, object, object]:
    """Binary forest raster (non-zero = forest, nodata = not forest); only the bbox window if given."""
    with rasterio.open(path) as r:
        window = None
        if bbox is not None:
            window = from_bounds(*transform_bounds("EPSG:4326", r.crs, *bbox), transform=r.transform)
            window = window.round_offsets().round_lengths()
        v = r.read(1, window=window)
        t = r.window_transform(window) if window is not None else r.transform
        ok = v != 0
        if r.nodata is not None:
            ok &= v != r.nodata
        return ok, t, r.crs


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--detections", default="web/data/detections.geojson")
    p.add_argument("--forest-mask", required=True, help="the binary forest GeoTIFF used by pipeline/detect")
    p.add_argument("--n", type=int, default=15, help="points per stratum")
    p.add_argument("--seed", type=int, required=True, help="record it next to the CSV")
    p.add_argument("--holdout-bbox", type=float, nargs=4, metavar=("W", "S", "E", "N"))
    p.add_argument("--holdout-dates", nargs="+")
    p.add_argument("--out", default="validation/sample_points.csv")
    p.add_argument("--blind", nargs=2, metavar=("BEFORE", "AFTER"),
                   help="write a blind sheet to --out (same before/after dates on every row) and the key to --key")
    p.add_argument("--key", help="key CSV for --blind; keep it away from the labeler")
    a = p.parse_args()
    if a.blind and not a.key:
        p.error("--blind needs --key")
    holdout = None
    if a.holdout_bbox is not None or a.holdout_dates:
        holdout = make_holdout(a.holdout_bbox, a.holdout_dates)
    else:
        print("WARNING: no holdout given; sampling the whole file")
    with open(a.detections, encoding="utf-8") as f:
        det = json.load(f)
    forest, t, crs = read_forest(a.forest_mask, (holdout or {}).get("bbox"))
    rows = sample_points(det, forest, t, crs, a.n, a.seed, holdout)
    if a.blind:
        sheet, key = make_blind(rows, *a.blind, a.seed)
        write_csv(sheet, a.out, BLIND_COLUMNS)
        write_csv(key, a.key, KEY_COLUMNS)
    else:
        write_csv(rows, a.out)
    nd = sum(r["stratum"] == "detection" for r in rows)
    print(f"{nd} detection + {len(rows) - nd} non-detection points (seed {a.seed}) -> {a.out}"
          + (f" (blind; key -> {a.key})" if a.blind else ""))


if __name__ == "__main__":
    main()
