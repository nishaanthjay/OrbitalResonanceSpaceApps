"""Measure, on the analysis window for every date: distribution of tiny HH/HV values (to pick a validity floor)
and rtcGammaToSigmaFactor variation across dates (does it cancel in dB differences?)."""
import time
import numpy as np
from common_valid import granules
from inspect_granule import open_tree
from load import GRID_GROUP, window_slices, X_COORD, Y_COORD

BBOX = (-62.8474, -9.3211, -62.6654, -9.1401)
EDGES = [0, 1e-13, 1e-12, 1e-10, 1e-8, 1e-6, 1e-5, 1e-4, 1e-3, np.inf]

if __name__ == "__main__":
    ref_f, maxdiff = None, 0.0
    tot = {p: np.zeros(len(EDGES) - 1, int) for p in ("HHHH", "HVHV")}
    for g in granules("Rondonia (Porto Velho-Ariquemes)", 60, 173):
        t = time.time()
        ds = tree = open_tree(g.properties["url"])[0][GRID_GROUP].ds
        ys, xs = window_slices(ds[X_COORD].values, ds[Y_COORD].values, int(ds["projection"].attrs["epsg_code"]), BBOX)
        sub = ds[["HHHH", "HVHV", "rtcGammaToSigmaFactor"]].isel({Y_COORD: ys, X_COORD: xs}).load()
        for p in tot:
            a = sub[p].values; a = a[np.isfinite(a)]
            tot[p] += np.histogram(a, EDGES)[0]
        f = sub["rtcGammaToSigmaFactor"].values
        if ref_f is None: ref_f = f
        else: maxdiff = max(maxdiff, float(np.nanmax(np.abs(f - ref_f))))
        print(f"{g.properties['startTime'][:10]} {time.time()-t:.0f}s factor min/median/max {np.nanmin(f):.4f}/{np.nanmedian(f):.4f}/{np.nanmax(f):.4f} nan {np.isnan(f).mean():.1%}", flush=True)
    print("value bins:", [f"{a:g}-{b:g}" for a, b in zip(EDGES, EDGES[1:])])
    for p, c in tot.items(): print(p, c.tolist())
    print("max |factor - factor(first date)| over window:", maxdiff,
          "| in dB:", float(np.nanmax(np.abs(10*np.log10(1+maxdiff/np.nanmin(ref_f))))) if maxdiff else 0.0)
