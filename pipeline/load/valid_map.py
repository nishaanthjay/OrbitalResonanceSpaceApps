"""Map where frequencyB HVHV has real backscatter (> -40 dB) inside a lon/lat bbox, to place the analysis window."""
import sys, time
import numpy as np
from pyproj import Transformer
from inspect_granule import open_tree

if __name__ == "__main__":
    url = sys.argv[1]; W, S, E, N = map(float, sys.argv[2:6])
    tree, _ = open_tree(url)
    ds = tree["/science/LSAR/GCOV/grids/frequencyB"].ds
    epsg = int(ds["projection"].attrs["epsg_code"])
    tf = Transformer.from_crs(4326, epsg, always_xy=True)
    xs, ys = tf.transform([W, E, W, E], [S, S, N, N])
    x, y = ds["xCoordinates"].values, ds["yCoordinates"].values
    xi = np.where((x >= min(xs)) & (x <= max(xs)))[0]; yi = np.where((y >= min(ys)) & (y <= max(ys)))[0]
    t = time.time()
    a = ds["HVHV"].isel(yCoordinates=slice(yi[0], yi[-1]+1), xCoordinates=slice(xi[0], xi[-1]+1)).values
    print(f"read {a.shape} in {time.time()-t:.1f}s")
    v = np.isfinite(a) & (a > 1e-4)
    print(f"valid fraction in bbox: {v.mean():.0%}")
    blk = 40
    H, Wd = (a.shape[0]//blk)*blk, (a.shape[1]//blk)*blk
    g = v[:H, :Wd].reshape(H//blk, blk, Wd//blk, blk).mean(axis=(1, 3))
    for row in g: print("".join("#" if f > .95 else "+" if f > .5 else "." for f in row))
    # best fully valid 250x250 freqB block (= 1000x1000 freqA)
    from scipy.ndimage import uniform_filter
    s = uniform_filter(v.astype(float), 250)
    iy, ix = np.unravel_index(np.argmax(s), s.shape)
    cx, cy = x[xi[0]+ix], y[yi[0]+iy]
    lon, lat = Transformer.from_crs(epsg, 4326, always_xy=True).transform(cx, cy)
    print(f"best window centre: lon {lon:.4f} lat {lat:.4f} valid {s[iy, ix]:.0%}")
    print(f"median HV dB there: {10*np.log10(np.nanmedian(a[max(iy-125,0):iy+125, max(ix-125,0):ix+125])):.1f}")
