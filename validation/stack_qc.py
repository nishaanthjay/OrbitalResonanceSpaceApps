"""Per-date quality check of a stack over stable forest: block medians and a picture of every date.

Reads:  a stack NetCDF and the stable-forest GeoTIFF.
Writes: a PNG (HH and HV of every date, fixed grey scales) and prints, per date, the stable-forest median and the
        largest deviation of an 8 x 8 block median from it, in both channels. A block that is >= 3 dB off in HH and
        HV (same sign) is listed: the rule in data/REPORT.md section 7 then needs a look at the picture (a
        straight-edged step is a processing artifact; an irregular patch is a landscape change).
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import xarray as xr

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pipeline", "detect"))
from detect import _with_crs, load_forest_mask  # noqa: E402


def block_grid(a: np.ndarray, s: np.ndarray, k: int = 8) -> np.ndarray:
    h, w = a.shape
    g = np.full((k, k), np.nan)
    for i in range(k):
        for j in range(k):
            sl = (slice(i * h // k, (i + 1) * h // k), slice(j * w // k, (j + 1) * w // k))
            v = a[sl][s[sl] & np.isfinite(a[sl])]
            if v.size:
                g[i, j] = np.median(v)
    return g


def multilook_mask(m: np.ndarray, n: int = 5) -> np.ndarray:
    h, w = m.shape[0] // n * n, m.shape[1] // n * n
    return m[:h, :w].reshape(h // n, n, w // n, n).mean(axis=(1, 3))


def multilook_db(a: np.ndarray, n: int = 5) -> np.ndarray:
    return 10 * np.log10(multilook_mask(10 ** (a / 10), n))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--stack", required=True)
    p.add_argument("--stable-mask", required=True)
    p.add_argument("--forest-mask", help="also print each date's 5x5-multilooked HV correlation with this mask at zero "
                                          "shift (a date showing the right ground scores like the others; REPORT rule: < 0.5 = drop)")
    p.add_argument("--png", required=True)
    a = p.parse_args()
    st = xr.open_dataset(a.stack)
    tmpl = _with_crs(st["hh_db"].isel(time=0), st.attrs["crs"])
    s = np.asarray(load_forest_mask(a.stable_mask, tmpl).values, bool)
    dates = [str(np.datetime64(t, "D")) for t in st["time"].values]
    if a.forest_mask:
        fm = multilook_mask(np.asarray(load_forest_mask(a.forest_mask, tmpl).values, float))
        for k, d in enumerate(dates):
            hv = multilook_db(st["hv_db"].isel(time=k).values)
            ok = np.isfinite(hv)
            print(f"{d}  corr(HV, forest mask) = {np.corrcoef(hv[ok], fm[ok])[0, 1]:+.3f}")
    print("date        HH med  HH block dev min/max   HV med  HV block dev min/max   NaN frac  flagged blocks (row,col)")
    for k, d in enumerate(dates):
        hh, hv = st["hh_db"].isel(time=k).values, st["hv_db"].isel(time=k).values
        mh, mv = np.nanmedian(hh[s]), np.nanmedian(hv[s])
        gh, gv = block_grid(hh, s) - mh, block_grid(hv, s) - mv
        flag = [(int(i), int(j)) for i, j in zip(*np.nonzero(((gh >= 3) & (gv >= 3)) | ((gh <= -3) & (gv <= -3))))]
        print(f"{d}  {mh:6.2f}  {np.nanmin(gh):+5.2f}/{np.nanmax(gh):+5.2f}          {mv:6.2f}  "
              f"{np.nanmin(gv):+5.2f}/{np.nanmax(gv):+5.2f}          {np.isnan(hh).mean():.4f}    {flag}")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(2, len(dates), figsize=(2.6 * len(dates), 5.6))
    for k, d in enumerate(dates):
        for r, (v, lim) in enumerate((("hh_db", (-12, 2)), ("hv_db", (-18, -2)))):
            ax[r, k].imshow(st[v].isel(time=k).values[::4, ::4], vmin=lim[0], vmax=lim[1], cmap="gray")
            ax[r, k].set_title(f"{v[:2].upper()} {d[5:]}", fontsize=9)
            ax[r, k].axis("off")
    plt.tight_layout()
    plt.savefig(a.png, dpi=70)
    print(f"-> {a.png}")


if __name__ == "__main__":
    main()
