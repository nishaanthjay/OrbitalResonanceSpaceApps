"""Read CRS/spacing from a GCOV granule and time a ~1000x1000 HH/HV window read near a lon/lat."""
import sys, time
import numpy as np
from pyproj import Transformer
from inspect_granule import open_tree

G = "/science/LSAR/GCOV/grids/frequencyA"

if __name__ == "__main__":
    url, lon, lat = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
    tree, f = open_tree(url)
    ds = tree[G].ds
    proj = ds["projection"]
    epsg = int(proj.attrs.get("epsg_code", proj.values))
    print("projection attrs:", {k: str(v)[:60] for k, v in proj.attrs.items() if k in ("epsg_code", "grid_mapping_name", "spatial_ref")})
    x, y = ds["xCoordinates"].values, ds["yCoordinates"].values
    print("EPSG", epsg, "| x spacing", float(x[1]-x[0]), "| y spacing", float(y[1]-y[0]))
    for k in ("xCoordinateSpacing", "yCoordinateSpacing"):
        if k in ds: print(k, float(ds[k].values))
    print("HHHH attrs:", {k: str(v)[:50] for k, v in ds["HHHH"].attrs.items()})
    print("HDF5 chunks:", ds["HHHH"].encoding.get("chunksizes"))
    px, py = Transformer.from_crs(4326, epsg, always_xy=True).transform(lon, lat)
    ix, iy = int(np.abs(x - px).argmin()), int(np.abs(y - py).argmin())
    print("frame x/y range", x.min(), x.max(), y.min(), y.max(), "| centre idx", iy, ix)
    sl = dict(yCoordinates=slice(max(iy-500,0), iy+500), xCoordinates=slice(max(ix-500,0), ix+500))
    for pol in ("HHHH", "HVHV"):
        t = time.time()
        a = ds[pol].isel(**sl).values
        fin = a[np.isfinite(a) & (a > 0)]
        print(f"{pol}: {time.time()-t:.1f}s shape {a.shape} {a.dtype} min {np.nanmin(a):.4g} max {np.nanmax(a):.4g} "
              f"valid {fin.size/a.size:.0%} median dB {10*np.log10(np.median(fin)):.1f}" if fin.size else f"{pol}: no valid pixels")
