"""Intersect frequencyB valid-data maps across all dates of one track/frame in a bbox; report the best common 1000x1000 freqA window."""
import sys, time
import numpy as np
from pyproj import Transformer
from scipy.ndimage import uniform_filter
from aoi_search import search, CANDIDATES
from inspect_granule import open_tree

def granules(name, track, frame):
    r = [x for x in search(CANDIDATES[name]) if x.properties["pathNumber"] == track
         and x.properties["frameNumber"] == frame and {"HH", "HV"} <= set(x.properties["mainBandPolarization"] or [])]
    return sorted(r, key=lambda x: x.properties["startTime"])

if __name__ == "__main__":
    name, track, frame = "Rondonia (Porto Velho-Ariquemes)", 60, 173
    W, S, E, N = CANDIDATES[name]
    common, per = None, []
    for g in granules(name, track, frame):
        d = g.properties["startTime"][:10]
        tree, _ = open_tree(g.properties["url"])
        ds = tree["/science/LSAR/GCOV/grids/frequencyB"].ds
        epsg = int(ds["projection"].attrs["epsg_code"])
        xs, ys = Transformer.from_crs(4326, epsg, always_xy=True).transform([W, E, W, E], [S, S, N, N])
        x, y = ds["xCoordinates"].values, ds["yCoordinates"].values
        xi = np.where((x >= min(xs)) & (x <= max(xs)))[0]; yi = np.where((y >= min(ys)) & (y <= max(ys)))[0]
        t = time.time()
        a = ds["HVHV"].isel(yCoordinates=slice(yi[0], yi[-1]+1), xCoordinates=slice(xi[0], xi[-1]+1)).values
        v = np.isfinite(a) & (a > 1e-4)
        print(f"{d}: read {a.shape} {time.time()-t:.0f}s valid {v.mean():.0%} grid x0 {x[0]:.0f} y0 {y[0]:.0f}", flush=True)
        common = v if common is None else (common & v)
    print(f"common valid fraction: {common.mean():.0%}")
    s = uniform_filter(common.astype(float), 250)
    iy, ix = np.unravel_index(np.argmax(s), s.shape)
    lon, lat = Transformer.from_crs(epsg, 4326, always_xy=True).transform(x[xi[0]+ix], y[yi[0]+iy])
    print(f"best common window centre: lon {lon:.4f} lat {lat:.4f} valid {s[iy, ix]:.0%}")
    blk = 40; H, Wd = (common.shape[0]//blk)*blk, (common.shape[1]//blk)*blk
    g = common[:H, :Wd].reshape(H//blk, blk, Wd//blk, blk).mean(axis=(1, 3))
    for row in g[::2]: print("".join("#" if f > .95 else "+" if f > .5 else "." for f in row))
