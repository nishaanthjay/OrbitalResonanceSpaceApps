"""Forest/non-forest from median-over-dates multilooked HV. Rules fixed in validation/PREREG_fnf.md.

Usage (run once, from the repo root):
  python validation/fnf.py --out data/fnf_metrics.json
Tunes T on the S Para north half (max Youden J), freezes it, scores the south half and Rondonia once each.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import xarray as xr
from pyproj import Transformer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline" / "detect"))
import detect  # noqa: E402  (multilook convention and bbox_mask are reused, not edited)

N = 5
SPARA = dict(stack="data/stack_spara_t2f174.nc", mask="data/forest_mask_spara_t2f174.tif",
             bbox=(-54.7900, -8.2900, -54.6080, -8.1090), dates=None)
RONDONIA = dict(stack="data/stack_rondonia_t60f173.nc", mask="data/forest_mask_rondonia_t60f173.tif",
                dates=["2026-08-17", "2026-08-29", "2026-09-10", "2026-10-04", "2026-10-16"])
HALF_BUFFER_DEG = 0.0045


def youden_threshold(x: np.ndarray, ref: np.ndarray, step: float = 0.05) -> tuple[float, float]:
    """T maximising J = TPR + TNR - 1 for 'forest if x >= T' on a `step` dB grid; ties -> lowest T."""
    lo, hi = np.floor(x.min() / step) * step, np.ceil(x.max() / step) * step + step
    edges = np.arange(lo, hi + step / 2, step)
    f, _ = np.histogram(x[ref], edges)
    n, _ = np.histogram(x[~ref], edges)
    # T = edges[k]: forest predicted for bins k.. ; TPR = sum f[k:]/F, TNR = sum n[:k]/N
    tpr = np.append(np.cumsum(f[::-1])[::-1], 0) / f.sum()
    tnr = np.concatenate([[0], np.cumsum(n)]) / n.sum()
    j = (tpr + tnr - 1)[: len(edges)]
    k = int(np.argmax(j))  # argmax returns the first (lowest) maximum
    return float(edges[k]), float(j[k])


def otsu_threshold(x: np.ndarray, bins: int = 256) -> float:
    h, e = np.histogram(x, bins)
    c = (e[:-1] + e[1:]) / 2
    w0 = np.cumsum(h)
    w1 = w0[-1] - w0
    m0 = np.cumsum(h * c) / np.maximum(w0, 1)
    m1 = (np.sum(h * c) - np.cumsum(h * c)) / np.maximum(w1, 1)
    return float(e[1:][np.argmax(w0 * w1 * (m0 - m1) ** 2)])


def metrics(pred: np.ndarray, ref: np.ndarray) -> dict:
    tp, fp = int((pred & ref).sum()), int((pred & ~ref).sum())
    fn, tn = int((~pred & ref).sum()), int((~pred & ~ref).sum())
    n = tp + fp + fn + tn
    oa = (tp + tn) / n
    pe = ((tp + fp) * (tp + fn) + (fn + tn) * (fp + tn)) / n**2
    return {"n": n, "tp": tp, "fp": fp, "fn": fn, "tn": tn, "oa": oa,
            "kappa": (oa - pe) / (1 - pe) if pe < 1 else None,
            "forest_precision": tp / (tp + fp) if tp + fp else None,
            "forest_recall": tp / (tp + fn) if tp + fn else None,
            "all_forest_baseline": (tp + fn) / n, "all_nonforest_baseline": (fp + tn) / n}


def blocks(cfg: dict):
    """Per-date multilooked HV (dB), block forest fraction, block-centre lon/lat."""
    ds = xr.open_dataset(cfg["stack"])
    if cfg["dates"]:
        ds = ds.sel(time=cfg["dates"])
    hv = detect.multilook(ds[["hh_db", "hv_db"]], N)["hv_db"]
    mk = detect.load_forest_mask(cfg["mask"], ds["hv_db"].isel(time=0)).astype(float)
    frac = mk.coarsen(y=N, x=N, boundary="trim").mean()
    xx, yy = np.meshgrid(hv["x"].values, hv["y"].values)
    lon, lat = Transformer.from_crs(ds.attrs["crs"], 4326, always_xy=True).transform(xx, yy)
    return hv.values, frac.values, lon, lat, [str(t)[:10] for t in ds.time.values]


def median_feature(hv: np.ndarray) -> np.ndarray:
    return np.nanmedian(hv, axis=0)


def score(feat, frac, T, region, pure_only=False):
    ok = region & np.isfinite(feat)
    if pure_only:
        ok &= (frac <= 0.1) | (frac >= 0.9)
    return metrics(feat[ok] >= T, frac[ok] >= 0.5)


def run() -> dict:
    hv, frac, lon, lat, dates = blocks(SPARA)
    w, s, e, n = SPARA["bbox"]
    c = (s + n) / 2
    tune = lat >= c + HALF_BUFFER_DEG
    hold = lat <= c - HALF_BUFFER_DEG
    feat = median_feature(hv)
    ok = tune & np.isfinite(feat)
    ref_t = frac[ok] >= 0.5
    T, J = youden_threshold(feat[ok], ref_t)
    out = {"prereg": "validation/PREREG_fnf.md", "multilook": N, "dates_spara": dates,
           "T_db": T, "tune": {"youden_J": J, "otsu_T_db_diagnostic": otsu_threshold(feat[ok]),
                               "n_blocks": int(ok.sum()), "forest_fraction": float(ref_t.mean()),
                               "at_T": score(feat, frac, T, tune)}}
    out["holdout"] = {"all": score(feat, frac, T, hold), "pure_blocks": score(feat, frac, T, hold, True),
                      "per_date": {d: {k: v for k, v in score(hv[i], frac, T, hold).items() if k in ("oa", "kappa")}
                                   for i, d in enumerate(dates)}}
    hv_r, frac_r, _, _, dates_r = blocks(RONDONIA)
    fr = median_feature(hv_r)
    allr = np.ones_like(fr, bool)
    out["transfer_rondonia"] = {"dates": dates_r, "all": score(fr, frac_r, T, allr),
                                "pure_blocks": score(fr, frac_r, T, allr, True)}
    return out


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="data/fnf_metrics.json")
    a = p.parse_args()
    res = run()
    Path(a.out).write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=2))
