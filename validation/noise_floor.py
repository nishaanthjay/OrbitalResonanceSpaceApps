"""Noise floor: distribution of detect's normalized change maps over stable forest, per date and channel.

Reads:  a stack NetCDF and the stable-forest GeoTIFF (validation/build_masks.py); uses pipeline/detect's own
        multilook / change_maps / normalize_stable, so the numbers describe exactly what detect thresholds.
Writes: a JSON file (and a printed table) with, per date that has a baseline: n, median, robust sd
        (1.4826 * MAD), percentiles 0.1/1/5/95/99/99.9, the stable-forest fraction past a set of cut-offs
        (HH rise >= c, HV drop >= c) and the spread of the median over 4 x 4 sub-blocks (spatial structure).
Stable forest has no alert of any date, so any firing there is treated as a false alarm.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
import xarray as xr

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pipeline", "detect"))
from detect import _with_crs, bbox_mask, change_maps, load_forest_mask, multilook, normalize_stable  # noqa: E402

CUTS = (1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0)  # the threshold grid of the written rule (data/REPORT.md)
PCTS = (0.1, 1, 5, 95, 99, 99.9)


def describe(v: np.ndarray, sign: int) -> dict:
    """sign +1: HH (rise fires), -1: HV (drop fires); fire_frac uses the same rule as detect."""
    med = float(np.median(v))
    return {"n": int(v.size), "median": med, "robust_sd": float(1.4826 * np.median(np.abs(v - med))),
            "pct": {str(p): float(x) for p, x in zip(PCTS, np.percentile(v, PCTS))},
            "fire_frac": {str(c): float(np.mean(sign * v >= c)) for c in CUTS}}


def block_medians(d: np.ndarray, s: np.ndarray, k: int = 4) -> list[float]:
    h, w = d.shape
    out = []
    for i in range(k):
        for j in range(k):
            sl = (slice(i * h // k, (i + 1) * h // k), slice(j * w // k, (j + 1) * w // k))
            v = d[sl][s[sl] & np.isfinite(d[sl])]
            if v.size:
                out.append(float(np.median(v)))
    return out


def noise_floor(stack: xr.Dataset, stable: xr.DataArray, average: str = "linear", region=None,
                dates: list[str] | None = None) -> dict:
    """Per date (default: every date after the first) and channel. The normalization offset is detect's (median
    over ALL stable forest); the statistics use stable forest inside `region` (boolean, same grid) if given.
    "pooled" holds the firing fractions over all those dates together (what the threshold rule uses)."""
    res, pooled = {}, {"hh": [], "hv": []}
    s = np.asarray(stable.values, bool)
    sr = s & (np.asarray(region.values, bool) if region is not None else True)
    for d in dates or [str(np.datetime64(t, "D")) for t in stack["time"].values[1:]]:
        d_hh, d_hv = change_maps(stack, d, average)
        rec = {}
        for name, ch, sign in (("hh", d_hh, 1), ("hv", d_hv, -1)):
            n, off, _ = normalize_stable(ch, stable)
            arr = n.values
            v = arr[sr & np.isfinite(arr)]
            pooled[name].append(v)
            bm = block_medians(arr, sr)
            rec[name] = {**describe(v, sign), "offset_db": off,
                         "block_median_range": [min(bm), max(bm)] if bm else None}
        res[d] = rec
    res["pooled"] = {name: describe(np.concatenate(v), sign)
                     for (name, v), sign in zip(pooled.items(), (1, -1)) if v}
    return res


def pick_threshold(rec: dict, max_frac: float) -> float | None:
    """Smallest cut in CUTS whose firing fraction is <= max_frac (the written CFAR rule); None if none is."""
    ok = [c for c in CUTS if rec["fire_frac"][str(c)] <= max_frac]
    return min(ok) if ok else None


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--stack", required=True)
    p.add_argument("--stable-mask", required=True)
    p.add_argument("--multilook", type=int, default=5)
    p.add_argument("--average", default="linear", choices=["linear", "db"])
    p.add_argument("--region-bbox", type=float, nargs=4, metavar=("W", "S", "E", "N"),
                   help="statistics only for stable forest with pixel centres in this box (e.g. the tune half)")
    p.add_argument("--date", nargs="+", help="dates to describe (default: all but the first)")
    p.add_argument("--max-frac", type=float, default=0.01,
                   help="CFAR rule: pick the smallest grid threshold whose pooled firing fraction is <= this")
    p.add_argument("--out", required=True)
    a = p.parse_args()
    stack = multilook(xr.open_dataset(a.stack), a.multilook)
    tmpl = _with_crs(stack["hh_db"].isel(time=0), stack.attrs["crs"])
    region = bbox_mask(tmpl, tuple(a.region_bbox)) if a.region_bbox else None
    res = noise_floor(stack, load_forest_mask(a.stable_mask, tmpl), a.average, region, a.date)
    pick = {ch: pick_threshold(res["pooled"][ch], a.max_frac) for ch in ("hh", "hv")}
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump({"stack": a.stack, "multilook": a.multilook, "average": a.average, "region_bbox": a.region_bbox,
                   "dates": res, "cfar": {"max_frac": a.max_frac, "grid": CUTS, "hh_thresh": pick["hh"],
                                          "hv_thresh": pick["hv"]}}, f, indent=1)
    print(f"CFAR (pooled firing <= {a.max_frac}): hh_thresh {pick['hh']}  hv_thresh {pick['hv']}")
    print("date        ch  n      offset  rsd    p1     p99    fire>=2  fire>=3  block-median range")
    for d, rec in res.items():
        for ch in ("hh", "hv"):
            r = rec[ch]
            extra = (f"{r['offset_db']:+.2f}  " if "offset_db" in r else "  -    ")
            bm = (f"{r['block_median_range'][0]:+.2f}..{r['block_median_range'][1]:+.2f}"
                  if r.get("block_median_range") else "")
            print(f"{d:10s}  {ch}  {r['n']:<6d} {extra}{r['robust_sd']:.2f}  {r['pct']['1']:+.2f}  "
                  f"{r['pct']['99']:+.2f}  {r['fire_frac']['2.0']:.4f}   {r['fire_frac']['3.0']:.4f}   {bm}")
    print(f"-> {a.out}")


if __name__ == "__main__":
    main()
