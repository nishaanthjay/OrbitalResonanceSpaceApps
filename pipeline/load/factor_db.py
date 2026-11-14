"""Per-pixel variation of rtcGammaToSigmaFactor across dates, in dB: |10*log10(f_date / f_first)| percentiles."""
import numpy as np
from common_valid import granules
from inspect_granule import open_tree
from load import GRID_GROUP, window_slices, X_COORD, Y_COORD

BBOX = (-62.8474, -9.3211, -62.6654, -9.1401)
if __name__ == "__main__":
    ref = None
    for g in granules("Rondonia (Porto Velho-Ariquemes)", 60, 173):
        ds = open_tree(g.properties["url"])[0][GRID_GROUP].ds
        ys, xs = window_slices(ds[X_COORD].values, ds[Y_COORD].values, 32720, BBOX)
        f = ds["rtcGammaToSigmaFactor"].isel({Y_COORD: ys, X_COORD: xs}).values.astype(np.float64)
        if ref is None:
            ref = f; continue
        d = np.abs(10 * np.log10(f / ref)); d = d[np.isfinite(d)]
        # same after 5x5 multilook (what detect thresholds on)
        H, W = (f.shape[0] // 5) * 5, (f.shape[1] // 5) * 5
        m = lambda a: a[:H, :W].reshape(H // 5, 5, W // 5, 5).mean(axis=(1, 3))
        d5 = np.abs(10 * np.log10(m(f) / m(ref)))
        print(f"{g.properties['startTime'][:10]} vs first: |dB| p50 {np.percentile(d,50):.3f} p99 {np.percentile(d,99):.3f} max {d.max():.2f}"
              f" | 5x5: p99 {np.percentile(d5,99):.3f} max {d5.max():.2f} | >0.5 dB {np.mean(d5>0.5):.3%}", flush=True)
