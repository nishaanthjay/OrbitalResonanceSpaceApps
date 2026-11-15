"""Forest map at scale: rules and scores fixed in validation/PREREG_scale.md. Run once.

  python validation/scale.py --stack data/stack_big_t2f174.nc --mask data/forest_mask_big_t2f174.tif \
    --out validation/scale_metrics.json

Stack: pipeline/load/load_big.py output (pixels are 5x5 linear block means = the fnf.py 100 m blocks).
Mask: pipeline/load/forest_mask.py --subdivide 5 (Hansen forest on the native 20 m grid behind the blocks).
Alerts: GLAD-L (alert26 / alertDate26) and GLAD-S2 read straight from UMD's public GeoTIFFs with fetch_alerts.py's
reader and encodings (no JSON rows: over 60 km the GLAD-S2 row file would be gigabytes).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import rioxarray
import xarray as xr
from pyproj import Transformer

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fetch_alerts  # noqa: E402
import fnf  # noqa: E402

DATES = ["2026-06-26", "2026-07-08", "2026-07-20", "2026-08-13", "2026-08-25",
         "2026-09-06", "2026-09-18", "2026-09-30", "2026-10-12"]
ORIGINAL_BBOX = (-54.7900, -8.2900, -54.6080, -8.1090)
REF_START, REF_END = dt.date(2026, 7, 20), dt.date(2026, 10, 12)
TOL_DAYS = 24
SEED = 20261114
BLOCK = 5


def frozen_T(path: Path = HERE / "fnf_metrics.json") -> float:
    return float(json.loads(path.read_text())["T_db"])


def lost_rule(forest: np.ndarray) -> np.ndarray:
    """forest: bool (9, ...) in DATES order. Lost = forest on >= 2 of passes 0-2 AND non-forest on passes 7 and 8."""
    if forest.shape[0] != 9:
        raise ValueError("lost_rule needs the 9 dates")
    return (forest[:3].sum(axis=0) >= 2) & ~forest[7] & ~forest[8]


def block_fraction(native: np.ndarray, n: int) -> np.ndarray:
    ny, nx = native.shape[0] // n, native.shape[1] // n
    return native[: ny * n, : nx * n].reshape(ny, n, nx, n).mean(axis=(1, 3))


def block_index(x: np.ndarray, y: np.ndarray, xc: np.ndarray, yc: np.ndarray):
    """Row / col of the block whose footprint holds each (x, y) (grid CRS); -1 if outside. xc ascending, yc descending."""
    dx, dy = xc[1] - xc[0], yc[1] - yc[0]
    col = np.floor((x - (xc[0] - dx / 2)) / dx).astype(int)
    row = np.floor((y - (yc[0] - dy / 2)) / dy).astype(int)
    out = (col < 0) | (col >= xc.size) | (row < 0) | (row >= yc.size)
    col[out], row[out] = -1, -1
    return row, col


def alert_blocks(dates: np.ndarray, rows: np.ndarray, cols: np.ndarray, shape, start: dt.date, end: dt.date) -> np.ndarray:
    """Bool block map: at least one alert pixel dated start..end (inclusive) inside the block."""
    m = np.zeros(shape, bool)
    keep = (rows >= 0) & (dates >= np.datetime64(start)) & (dates <= np.datetime64(end))
    m[rows[keep], cols[keep]] = True
    return m


def agreement(pred: np.ndarray, ref_prec: np.ndarray, ref_rec: np.ndarray, area: np.ndarray) -> dict:
    """precision_like = share of pred blocks with an alert in the tolerance window (ref_prec);
    recall_like = share of reference blocks (ref_rec) that are pred. All inside `area`."""
    p, rp, rr = pred & area, ref_prec & area, ref_rec & area
    n_pred, n_ref = int(p.sum()), int(rr.sum())
    hit_p, hit_r = int((p & rp).sum()), int((p & rr).sum())
    return {"n_blocks": n_pred, "n_with_alert": hit_p, "precision_like": hit_p / n_pred if n_pred else None,
            "n_reference": n_ref, "n_reference_hit": hit_r, "recall_like": hit_r / n_ref if n_ref else None}


def read_alerts(bbox, source: str):
    """(dates datetime64[D], lon, lat) of every nonzero alert pixel in bbox."""
    tile = fetch_alerts.glad_tile(bbox)
    if source == "GLAD-L":
        a, t = fetch_alerts.read_window(f"{fetch_alerts.BUCKET}/GLADalert/C2/current/alert26_{tile}.tif", bbox)
        d, _ = fetch_alerts.read_window(f"{fetch_alerts.BUCKET}/GLADalert/C2/current/alertDate26_{tile}.tif", bbox)
        nz = (a > 0) & (d > 0)
        dates = np.datetime64("2026-01-01") + (d[nz].astype(int) - 1).astype("timedelta64[D]")
    else:
        a, t = fetch_alerts.read_window(f"{fetch_alerts.BUCKET}/S2alert/alert/{tile}.tif", bbox)
        d, _ = fetch_alerts.read_window(f"{fetch_alerts.BUCKET}/S2alert/alertDate/{tile}.tif", bbox)
        nz = (a > 0) & (d > 0)
        dates = np.datetime64(fetch_alerts.S2_EPOCH.isoformat()) + d[nz].astype(int).astype("timedelta64[D]")
    r, c = np.nonzero(nz)
    lon, lat = t * (c + 0.5, r + 0.5)
    return dates, np.asarray(lon), np.asarray(lat), int((a > 0).sum()), int(((a > 0) & (d == 0)).sum())


def run(stack_path: str, mask_path: str) -> dict:
    T = frozen_T()
    ds = xr.open_dataset(stack_path)
    dates = [str(t)[:10] for t in ds.time.values]
    if dates != DATES:
        raise SystemExit(f"stack dates {dates} != pre-registered {DATES}")
    if int(ds.attrs["multilook"]) != BLOCK:
        raise SystemExit("stack pixels must be the 5x5 blocks (load_big.py --block 5)")
    hv = ds["hv_db"].values
    xc, yc = ds["x"].values, ds["y"].values
    crs = ds.attrs["crs"]
    valid = np.isfinite(hv).all(axis=0)

    mk = rioxarray.open_rasterio(mask_path).squeeze(drop=True)
    if mk.shape != (yc.size * BLOCK, xc.size * BLOCK) or not np.allclose(mk["x"].values[BLOCK // 2::BLOCK], xc):
        raise SystemExit("forest mask is not on the native grid behind the stack blocks (forest_mask.py --subdivide 5)")
    frac = block_fraction((mk.values == 1).astype(float), BLOCK)
    hansen = frac >= 0.5

    xx, yy = np.meshgrid(xc, yc)
    lon, lat = Transformer.from_crs(crs, 4326, always_xy=True).transform(xx, yy)
    w, s, e, n = ORIGINAL_BBOX
    in_orig = (lon >= w) & (lon <= e) & (lat >= s) & (lat <= n)
    area = valid & ~in_orig

    forest = hv >= T  # NaN compares False; only `area` blocks (finite on all dates) are scored
    feat = fnf.median_feature(hv)
    fmed = feat >= T
    pure = (frac <= 0.1) | (frac >= 0.9)
    out = {"prereg": "validation/PREREG_scale.md", "T_db": T, "dates": dates, "stack": stack_path,
           "grid": {"crs": crs, "block_m": float(abs(xc[1] - xc[0])), "shape": list(valid.shape),
                    "bounds_lonlat_wsen": [float(lon.min()), float(lat.min()), float(lon.max()), float(lat.max())]},
           "blocks": {"total": int(valid.size), "valid_all_9": int(valid.sum()),
                      "valid_fraction": float(valid.mean()), "in_original_window": int((valid & in_orig).sum()),
                      "scored": int(area.sum())}}
    out["a_forest_map"] = {
        "reference": "Hansen GFC v1.13 forest (forest_mask.py), block forest if >= 50 % of 25 px",
        "median": fnf.metrics(fmed[area], hansen[area]),
        "median_pure_blocks": fnf.metrics(fmed[area & pure], hansen[area & pure]),
        "per_date": {d: {k: v for k, v in fnf.metrics(forest[i][area], hansen[area]).items()
                         if k in ("oa", "kappa", "all_forest_baseline")} for i, d in enumerate(dates)},
    }

    lost = lost_rule(forest) & area
    stable = forest.all(axis=0) & hansen & ~lost & area
    rng = np.random.default_rng(SEED)
    idx = np.flatnonzero(stable)
    k = min(int(lost.sum()), idx.size)
    control = np.zeros_like(lost)
    control.flat[rng.choice(idx, size=k, replace=False)] = True
    out["loss_rule"] = {"rule": "forest on >= 2 of 06-26/07-08/07-20 AND non-forest on 09-30 and 10-12",
                        "lost_blocks": int(lost.sum()), "lost_ha": float(lost.sum() * (abs(xc[1] - xc[0]) ** 2) / 1e4),
                        "lost_on_hansen_forest": int((lost & hansen).sum()),
                        "stable_forest_blocks": int(stable.sum()), "control_size": k,
                        "control_is_whole_stable_set": k < int(lost.sum())}

    # alerts over the stack's lon/lat footprint (block edges), pixels mapped to blocks in the grid CRS
    half = abs(xc[1] - xc[0]) / 2
    ex, ey = [xc[0] - half, xc[-1] + half], [yc[0] + half, yc[-1] - half]
    elon, elat = Transformer.from_crs(crs, 4326, always_xy=True).transform([ex[0], ex[1], ex[0], ex[1]], [ey[0], ey[0], ey[1], ey[1]])
    abox = (min(elon), min(elat), max(elon), max(elat))
    to_grid = Transformer.from_crs(4326, crs, always_xy=True)
    tol = dt.timedelta(days=TOL_DAYS)
    out["b_alerts"] = {"tolerance_days": TOL_DAYS, "reference_dates": [REF_START.isoformat(), REF_END.isoformat()],
                       "precision_window": [(REF_START - tol).isoformat(), (REF_END + tol).isoformat()],
                       "alert_bbox_wsen": list(abox)}
    for src in ("GLAD-L", "GLAD-S2"):
        adates, alon, alat, n_px, n_undated = read_alerts(abox, src)
        ax, ay = to_grid.transform(alon, alat)
        r, c = block_index(np.asarray(ax), np.asarray(ay), xc, yc)
        ref_rec = alert_blocks(adates, r, c, valid.shape, REF_START, REF_END)
        ref_prec = alert_blocks(adates, r, c, valid.shape, REF_START - tol, REF_END + tol)
        out["b_alerts"][src] = {
            "alert_pixels_in_bbox": n_px, "alert_pixels_without_date": n_undated,
            "lost": agreement(lost, ref_prec, ref_rec, area),
            "control": agreement(control, ref_prec, ref_rec, area),
            "lost_recall_on_hansen_forest_reference": agreement(lost, ref_prec, ref_rec & hansen, area),
            "control_recall_on_hansen_forest_reference": agreement(control, ref_prec, ref_rec & hansen, area),
        }
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--stack", default="data/stack_big_t2f174.nc")
    p.add_argument("--mask", default="data/forest_mask_big_t2f174.tif")
    p.add_argument("--out", default="validation/scale_metrics.json")
    a = p.parse_args()
    res = run(a.stack, a.mask)
    Path(a.out).write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
