"""Full-frame forest map: rules and scores fixed in validation/PREREG_frame.md. Run once.

  python validation/frame.py --stack data/stack_frame_t2f174.nc --mask data/forest_mask_frame_t2f174.tif \
    --alerts-dir data/final_frame --out validation/frame_metrics.json

Same rules as scale.py (imported, not copied). Differences fixed in the pre-registration: the scoring area excludes the
original 20 km window AND the 60 km box; forest-map metrics add the non-forest class; alerts are read from the saved
rasters in --alerts-dir (fetch_alerts_frame.py).
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
import fetch_alerts_frame  # noqa: E402
import fnf  # noqa: E402
import scale  # noqa: E402

BOX60_X = (62360.0, 122360.0)  # block edges of the 60 km box (EPSG:32722)
BOX60_Y = (9061780.0, 9121780.0)
BLOCK = scale.BLOCK


def block_fraction_u8(native_bool: np.ndarray, n: int) -> np.ndarray:
    """Mean of n x n native pixels per block without a float copy of the native grid."""
    ny, nx = native_bool.shape[0] // n, native_bool.shape[1] // n
    return native_bool[: ny * n, : nx * n].reshape(ny, n, nx, n).sum(axis=(1, 3), dtype=np.int32) / (n * n)


def with_nonforest(m: dict) -> dict:
    """fnf.metrics plus the non-forest class (tn / fn / fp are in m already) and the confusion matrix."""
    tn, fn, fp, tp = m["tn"], m["fn"], m["fp"], m["tp"]
    m = dict(m)
    m["nonforest_precision"] = tn / (tn + fn) if tn + fn else None
    m["nonforest_recall"] = tn / (tn + fp) if tn + fp else None
    m["confusion_rows_ref_cols_pred"] = {"labels": ["forest", "non-forest"],
                                         "ref_forest": [tp, fn], "ref_nonforest": [fp, tn]}
    return m


def first_switch_index(forest: np.ndarray) -> np.ndarray:
    """Index of the first pass from which the block is non-forest on that and every later pass; -1 if the last pass is forest."""
    nf_suffix = np.flip(np.cumprod(np.flip(~forest, axis=0), axis=0), axis=0).astype(bool)  # non-forest from i to the end
    return np.where(nf_suffix.any(axis=0), nf_suffix.argmax(axis=0), -1)


def box60_mask(xc: np.ndarray, yc: np.ndarray) -> np.ndarray:
    xx, yy = np.meshgrid(xc, yc)
    return (xx >= BOX60_X[0]) & (xx <= BOX60_X[1]) & (yy >= BOX60_Y[0]) & (yy <= BOX60_Y[1])


def run(stack_path: str, mask_path: str, alerts_dir: str) -> dict:
    T = scale.frozen_T()
    ds = xr.open_dataset(stack_path)
    dates = [str(t)[:10] for t in ds.time.values]
    if dates != scale.DATES:
        raise SystemExit(f"stack dates {dates} != pre-registered {scale.DATES}")
    if int(ds.attrs["multilook"]) != BLOCK:
        raise SystemExit("stack pixels must be the 5x5 blocks")
    hv = ds["hv_db"].values
    xc, yc = ds["x"].values, ds["y"].values
    crs = ds.attrs["crs"]
    valid = np.isfinite(hv).all(axis=0)

    mk = rioxarray.open_rasterio(mask_path).squeeze(drop=True)
    if mk.shape != (yc.size * BLOCK, xc.size * BLOCK) or not np.allclose(mk["x"].values[BLOCK // 2::BLOCK], xc):
        raise SystemExit("forest mask is not on the native grid behind the stack blocks")
    frac = block_fraction_u8(mk.values == 1, BLOCK)
    del mk
    hansen = frac >= 0.5

    xx, yy = np.meshgrid(xc, yc)
    lon, lat = Transformer.from_crs(crs, 4326, always_xy=True).transform(xx, yy)
    del xx, yy
    w, s, e, n = scale.ORIGINAL_BBOX
    in_orig = (lon >= w) & (lon <= e) & (lat >= s) & (lat <= n)
    in_box = box60_mask(xc, yc)
    area = valid & ~in_orig & ~in_box

    forest = hv >= T
    fmed = fnf.median_feature(hv) >= T
    pure = (frac <= 0.1) | (frac >= 0.9)
    out = {"prereg": "validation/PREREG_frame.md", "T_db": T, "dates": dates, "stack": stack_path,
           "grid": {"crs": crs, "block_m": float(abs(xc[1] - xc[0])), "shape": list(valid.shape),
                    "bounds_lonlat_wsen": [float(lon.min()), float(lat.min()), float(lon.max()), float(lat.max())]},
           "blocks": {"total": int(valid.size), "valid_all_9": int(valid.sum()), "valid_fraction": float(valid.mean()),
                      "in_original_window": int((valid & in_orig).sum()), "in_60km_box": int((valid & in_box).sum()),
                      "scored": int(area.sum()), "scored_km2": float(area.sum() * 0.01)}}
    out["a_forest_map"] = {
        "reference": "Hansen GFC v1.13 forest (forest_mask.py), block forest if >= 50 % of 25 px",
        "hansen_forest_share_of_scored": float(hansen[area].mean()),
        "median": with_nonforest(fnf.metrics(fmed[area], hansen[area])),
        "median_pure_blocks": with_nonforest(fnf.metrics(fmed[area & pure], hansen[area & pure])),
        "per_date": {d: {k: v for k, v in fnf.metrics(forest[i][area], hansen[area]).items()
                         if k in ("oa", "kappa", "all_forest_baseline")} for i, d in enumerate(dates)}}

    lost = scale.lost_rule(forest) & area
    stable = forest.all(axis=0) & hansen & ~lost & area
    rng = np.random.default_rng(scale.SEED)
    idx = np.flatnonzero(stable)
    k = min(int(lost.sum()), idx.size)
    control = np.zeros_like(lost)
    control.flat[rng.choice(idx, size=k, replace=False)] = True
    out["loss_rule"] = {"rule": "forest on >= 2 of 06-26/07-08/07-20 AND non-forest on 09-30 and 10-12",
                        "lost_blocks": int(lost.sum()), "lost_ha": float(lost.sum() * 1.0),
                        "lost_on_hansen_forest": int((lost & hansen).sum()),
                        "stable_forest_blocks": int(stable.sum()), "control_size": k,
                        "control_is_whole_stable_set": k < int(lost.sum())}

    to_grid = Transformer.from_crs(4326, crs, always_xy=True)
    tol = dt.timedelta(days=scale.TOL_DAYS)
    out["b_alerts"] = {"tolerance_days": scale.TOL_DAYS,
                       "reference_dates": [scale.REF_START.isoformat(), scale.REF_END.isoformat()],
                       "precision_window": [(scale.REF_START - tol).isoformat(), (scale.REF_END + tol).isoformat()]}
    alerts = {}
    for src in ("GLAD-L", "GLAD-S2"):
        adates, alon, alat = fetch_alerts_frame.read_saved(src, alerts_dir)
        ax, ay = to_grid.transform(alon, alat)
        r, c = scale.block_index(np.asarray(ax), np.asarray(ay), xc, yc)
        ref_rec = scale.alert_blocks(adates, r, c, valid.shape, scale.REF_START, scale.REF_END)
        ref_prec = scale.alert_blocks(adates, r, c, valid.shape, scale.REF_START - tol, scale.REF_END + tol)
        alerts[src] = ref_prec
        out["b_alerts"][src] = {
            "alert_pixels_read": int(adates.size),
            "lost": scale.agreement(lost, ref_prec, ref_rec, area),
            "control": scale.agreement(control, ref_prec, ref_rec, area),
            "lost_recall_on_hansen_forest_reference": scale.agreement(lost, ref_prec, ref_rec & hansen, area),
            "control_recall_on_hansen_forest_reference": scale.agreement(control, ref_prec, ref_rec & hansen, area)}
    out["_arrays"] = {"lost": lost, "forest": forest, "fmed": fmed, "valid": valid, "area": area, "hansen": hansen,
                      "alert_any": alerts["GLAD-L"] | alerts["GLAD-S2"], "xc": xc, "yc": yc}
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--stack", default="data/stack_frame_t2f174.nc")
    p.add_argument("--mask", default="data/forest_mask_frame_t2f174.tif")
    p.add_argument("--alerts-dir", default="data/final_frame")
    p.add_argument("--out", default="validation/frame_metrics.json")
    a = p.parse_args()
    res = run(a.stack, a.mask, a.alerts_dir)
    res.pop("_arrays")
    Path(a.out).write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
