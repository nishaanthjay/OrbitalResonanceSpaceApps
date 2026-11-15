"""Band check (validation/PREREG_scale.md): frequencyB HV (80 m) vs frequencyA HV block-averaged onto the same 80 m pixels.

For each date: read the window of both bands, average frequencyA HVHV in linear power over the 4 x 4 pixels that make
up each frequencyB pixel (NaN / below-floor skipped), convert both to dB, and report median / mean of |B - A| and of
(B - A) over pixels finite in both. Prints one JSON object (per date + pooled).

  python pipeline/load/freq_compare.py --bbox -54.7900 -8.2900 -54.6080 -8.1090 --start 2026-06-20 --end 2026-10-20 \
    --track 2 --frame 174 --direction ASCENDING --mode 20+5 --out data/freq_compare_spara.json
"""
from __future__ import annotations

import argparse
import json
import time

import numpy as np

import load
from load_big import block_mean_linear

GRIDS = "/science/LSAR/GCOV/grids"




def compare_date(tree, bbox, n: int = 4) -> dict:
    a = tree[f"{GRIDS}/frequencyA"].ds
    b = tree[f"{GRIDS}/frequencyB"].ds
    epsg = int(a["projection"].attrs["epsg_code"])
    if int(b["projection"].attrs["epsg_code"]) != epsg:
        raise ValueError("frequencyA and frequencyB EPSG differ")
    xa, ya = a["xCoordinates"].values, a["yCoordinates"].values
    xb, yb = b["xCoordinates"].values, b["yCoordinates"].values
    ysb, xsb = load.window_slices(xb, yb, epsg, bbox)
    xbw, ybw = xb[xsb], yb[ysb]
    dxa, dya = xa[1] - xa[0], ya[1] - ya[0]
    # first A pixel of each B pixel: centre_B - (n-1)/2 * spacing_A
    ix0 = np.rint((xbw[0] - (n - 1) * dxa / 2 - xa[0]) / dxa).astype(int)
    iy0 = np.rint((ybw[0] - (n - 1) * dya / 2 - ya[0]) / dya).astype(int)
    if not (np.isclose(xa[ix0] + (n - 1) * dxa / 2, xbw[0], rtol=0.0, atol=1e-3) and np.isclose(ya[iy0] + (n - 1) * dya / 2, ybw[0], rtol=0.0, atol=1e-3)):
        raise ValueError("frequencyB pixels are not aligned with n x n frequencyA blocks")
    pa = a["HVHV"].isel(yCoordinates=slice(iy0, iy0 + n * len(ybw)), xCoordinates=slice(ix0, ix0 + n * len(xbw))).values
    pb = b["HVHV"].isel(yCoordinates=ysb, xCoordinates=xsb).values
    da_db = load.to_db(block_mean_linear(pa, n))
    db_db = load.to_db(pb)
    ok = np.isfinite(da_db) & np.isfinite(db_db)
    d = (db_db - da_db)[ok]
    return {"n_pixels": int(ok.sum()), "median_abs_diff_db": float(np.median(np.abs(d))),
            "mean_abs_diff_db": float(np.mean(np.abs(d))), "median_diff_db": float(np.median(d)),
            "mean_diff_db": float(np.mean(d)), "_d": d}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--bbox", type=float, nargs=4, required=True)
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--track", type=int, required=True)
    p.add_argument("--frame", type=int, required=True)
    p.add_argument("--direction", required=True)
    p.add_argument("--mode", required=True)
    p.add_argument("--out", default=None)
    a = p.parse_args()
    key = load.GroupKey(a.track, a.frame, a.direction, a.mode)
    grans = load.search_granules(tuple(a.bbox), a.start, a.end, key)
    per, pooled = {}, []
    for g in grans:
        t = time.time()
        r = compare_date(load.open_granule(g.properties["url"]), tuple(a.bbox))
        pooled.append(r.pop("_d"))
        per[g.properties["startTime"][:10]] = r
        print(g.properties["startTime"][:10], {k: round(v, 3) for k, v in r.items()}, f"{time.time() - t:.0f}s", flush=True)
    d = np.concatenate(pooled)
    out = {"bbox": a.bbox, "per_date": per,
           "pooled": {"n_pixels": int(d.size), "median_abs_diff_db": float(np.median(np.abs(d))),
                      "mean_abs_diff_db": float(np.mean(np.abs(d))), "median_diff_db": float(np.median(d))},
           "rule": "use frequencyB if pooled median_abs_diff_db <= 0.3 (validation/PREREG_scale.md)"}
    out["decision"] = "frequencyB" if out["pooled"]["median_abs_diff_db"] <= 0.3 else "frequencyA"
    print(json.dumps(out["pooled"]), out["decision"])
    if a.out:
        with open(a.out, "w") as f:
            json.dump(out, f, indent=2)


if __name__ == "__main__":
    main()
