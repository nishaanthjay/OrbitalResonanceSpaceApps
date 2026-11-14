"""Diagnostics after the one final run (explains a result; never used to pick thresholds).

Reads:  the stack, forest / stable masks, alert rows, the final detections and the thresholds used.
Prints: (1) how much alert-event area lies inside the forest mask (detect cannot fire outside it);
        (2) detect's normalized HH / HV change at alert pixels on the first stack date after each alert, by
            channel, vs stable forest on the same dates, and the share that would pass the thresholds;
        (3) where the detections sit: overlap with alerts of any date and with Hansen loss before the stack.
Each block is printed per split half so the tune and holdout halves can be compared.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
import xarray as xr
from pyproj import Transformer
from shapely.geometry import shape

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pipeline", "detect"))
from detect import _with_crs, bbox_mask, change_maps, load_forest_mask, multilook, normalize_stable  # noqa: E402

from clearing_check import SOURCES, halves  # noqa: E402


def alert_grid(rows, field, deg, tmpl, after, until):
    """Earliest alert date (as int days, -1 = none) per multilooked pixel, for alerts in (after, until]."""
    to = Transformer.from_crs("EPSG:4326", tmpl.rio.crs, always_xy=True)
    x, y = tmpl["x"].values, tmpl["y"].values
    dx, dy = x[1] - x[0], y[1] - y[0]
    out = np.full(tmpl.shape, np.iinfo(np.int32).max, dtype=np.int64)
    for r in rows:
        d = r[field]
        if not d or not (after < d <= until):
            continue
        px, py = to.transform(r["longitude"], r["latitude"])
        i, j = int(round((py - y[0]) / dy)), int(round((px - x[0]) / dx))
        if 0 <= i < out.shape[0] and 0 <= j < out.shape[1]:
            out[i, j] = min(out[i, j], int(np.datetime64(d, "D").astype(int)))
    return np.where(out == np.iinfo(np.int32).max, -1, out)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--stack", required=True)
    p.add_argument("--dir", required=True, help="folder with alerts_*.json, forest_mask.tif, stable_forest.tif, final/")
    p.add_argument("--bbox", type=float, nargs=4, required=True)
    p.add_argument("--dates", nargs="+", required=True, help="scored dates")
    p.add_argument("--hh-thresh", type=float, required=True)
    p.add_argument("--hv-thresh", type=float, required=True)
    a = p.parse_args()
    st = multilook(xr.open_dataset(a.stack), 5)
    tmpl = _with_crs(st["hh_db"].isel(time=0), st.attrs["crs"])
    fm = np.asarray(load_forest_mask(f"{a.dir}/forest_mask.tif", tmpl).values, bool)
    sm_da = load_forest_mask(f"{a.dir}/stable_forest.tif", tmpl)
    sm = np.asarray(sm_da.values, bool)
    all_dates = [str(np.datetime64(t, "D")) for t in st["time"].values]
    after = all_dates[all_dates.index(a.dates[0]) - 1]
    regions = {h: np.asarray(bbox_mask(tmpl, b).values, bool) for h, b in halves(a.bbox).items()}
    ch = {d: [normalize_stable(c, sm_da)[0].values for c in change_maps(st, d)] for d in a.dates}
    dnum = np.array([np.datetime64(d, "D").astype(int) for d in a.dates])

    print(f"(1)+(2) alert pixels (100 m cells) dated ({after}, {a.dates[-1]}]; change on the first scored date on or "
          f"after the alert; fire = HH >= {a.hh_thresh} or HV <= -{a.hv_thresh}")
    for src, (fname, ds, deg) in SOURCES.items():
        with open(f"{a.dir}/{fname}", encoding="utf-8") as f:
            ag = alert_grid(json.load(f), f"{ds}__date", deg, tmpl, after, a.dates[-1])
        for h, reg in regions.items():
            al = (ag >= 0) & reg
            k = np.searchsorted(dnum, ag[al])  # first scored date on or after the alert date
            ok = k < len(dnum)
            ii, jj = np.nonzero(al)
            hh = np.array([ch[a.dates[kk]][0][i, j] for kk, i, j in zip(k[ok], ii[ok], jj[ok])])
            hv = np.array([ch[a.dates[kk]][1][i, j] for kk, i, j in zip(k[ok], ii[ok], jj[ok])])
            inf = fm[ii[ok], jj[ok]]
            fire = (hh >= a.hh_thresh) | (hv <= -a.hv_thresh)
            q = lambda v: np.round(np.nanpercentile(v, [10, 50, 90]), 2).tolist() if v.size else None  # noqa: E731
            print(f"  {src:8s} {h:16s} cells {al.sum():5d}  in forest mask {inf.mean() if inf.size else 0:.3f}  "
                  f"HH p10/50/90 {q(hh)}  HV p10/50/90 {q(hv)}  fire {fire.mean() if fire.size else 0:.3f}  "
                  f"fire|in-forest {fire[inf].mean() if inf.any() else 0:.3f}")
    for h, reg in regions.items():
        s = sm & reg
        hh = np.concatenate([ch[d][0][s] for d in a.dates])
        hv = np.concatenate([ch[d][1][s] for d in a.dates])
        print(f"  stable forest   {h:16s} HH p10/50/90 {np.round(np.nanpercentile(hh, [10, 50, 90]), 2).tolist()}  "
              f"HV p10/50/90 {np.round(np.nanpercentile(hv, [10, 50, 90]), 2).tolist()}")

    with open(f"{a.dir}/final/detections.geojson", encoding="utf-8") as f:
        det = json.load(f)["features"]
    print("(3) detections")
    for h, (w, s, e, n) in halves(a.bbox).items():
        sel = [f for f in det if w <= shape(f["geometry"]).representative_point().x <= e
               and s <= shape(f["geometry"]).representative_point().y <= n]
        by = {}
        for f in sel:
            pr = f["properties"]
            k = (pr["date"], pr.get("stage"))
            by[k] = by.get(k, 0) + 1
        area = sum(f["properties"].get("area_ha", 0) for f in sel)
        print(f"  {h:16s} n {len(sel)}  area {area:.0f} ha  by (date, stage) {dict(sorted(by.items()))}")


if __name__ == "__main__":
    main()
