"""Full-frame GLAD-L / GLAD-S2 alerts as cropped GeoTIFF windows (row-JSON would be gigabytes).

Writes data/final_frame/{gladl_alert26,gladl_alertDate26,gladl_alert25,gladl_alertDate25,glads2_alert,glads2_alertDate}.tif
and README.txt. read_saved(source, dir) mirrors scale.read_alerts (GLAD-L: 2026 layers only).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import rasterio

sys.path.insert(0, str(Path(__file__).parent))
import fetch_alerts as fa  # noqa: E402

BBOX = (-55.30, -8.45, -52.43, -5.78)
OUT = Path(__file__).resolve().parent.parent / "data" / "final_frame"
L = f"{fa.BUCKET}/GLADalert/C2/current"
S2 = f"{fa.BUCKET}/S2alert"


def sources(bbox):
    t = fa.glad_tile(bbox)
    return {
        "gladl_alert26": f"{L}/alert26_{t}.tif", "gladl_alertDate26": f"{L}/alertDate26_{t}.tif",
        "gladl_alert25": f"{L}/alert25_{t}.tif", "gladl_alertDate25": f"{L}/alertDate25_{t}.tif",
        "glads2_alert": f"{S2}/alert/{t}.tif", "glads2_alertDate": f"{S2}/alertDate/{t}.tif",
    }


def retry(fn, log, tries=5, pause=60):
    for i in range(tries):
        try:
            return fn()
        except Exception as e:  # transient network errors surface as RasterioIOError/others
            log.append(f"attempt {i + 1}/{tries} failed: {type(e).__name__}: {e}")
            if i == tries - 1:
                raise
            time.sleep(pause)


def save(bbox, out, names=None, log=None, pause=60):
    """Fetch windows and write compressed GeoTIFFs; returns {name: (url, array, transform)}."""
    log = [] if log is None else log
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    res = {}
    for name, url in sources(bbox).items():
        if names and name not in names:
            continue
        arr, tr = retry(lambda: fa.read_window(url, bbox), log, pause=pause)
        with rasterio.open(out / f"{name}.tif", "w", driver="GTiff", height=arr.shape[0], width=arr.shape[1],
                           count=1, dtype=arr.dtype, crs="EPSG:4326", transform=tr, compress="deflate") as ds:
            ds.write(arr, 1)
        res[name] = (url, arr, tr)
    return res


def _load(path):
    with rasterio.open(path) as ds:
        return ds.read(1), ds.transform


def read_saved(source: str, dir):
    """(dates datetime64[D], lon, lat) of nonzero dated pixels, same semantics as scale.read_alerts."""
    dir = Path(dir)
    if source == "GLAD-L":
        a, t = _load(dir / "gladl_alert26.tif")
        d, _ = _load(dir / "gladl_alertDate26.tif")
        nz = (a > 0) & (d > 0)
        dates = np.datetime64("2026-01-01") + (d[nz].astype(int) - 1).astype("timedelta64[D]")
    else:
        a, t = _load(dir / "glads2_alert.tif")
        d, _ = _load(dir / "glads2_alertDate.tif")
        nz = (a > 0) & (d > 0)
        dates = np.datetime64(fa.S2_EPOCH.isoformat()) + d[nz].astype(int).astype("timedelta64[D]")
    r, c = np.nonzero(nz)
    lon, lat = t * (c + 0.5, r + 0.5)
    return dates, np.asarray(lon), np.asarray(lat)


def readme(bbox, res, log, secs):
    lo, hi = np.datetime64("2026-07-20"), np.datetime64("2026-10-12")
    L_ = [f"GLAD alerts, full-frame windows. bbox W S E N = {bbox}, tile {fa.glad_tile(bbox)}, EPSG:4326.",
          f"Fetched in {secs:.0f} s. Window = pixels with centre inside bbox. Files are deflate GeoTIFFs, source dtype.", ""]
    for n, (url, arr, tr) in res.items():
        L_.append(f"{n}.tif  shape {arr.shape} dtype {arr.dtype}  pixel {tr.a} deg  source {url}")
    L_ += ["", "Encodings: GLAD-L alert 0 none, 2 probable, 3 confirmed; alertDate = day of year of that file's year (date = Jan 1 + d-1).",
           "GLAD-S2 alert 1..4 (meaning undocumented); alertDate = days since 2018-12-31 (date = S2_EPOCH + d).",
           "read_saved counts a>0 and d>0 (GLAD-L 2026 layers only), as scale.read_alerts.", ""]
    for key, (an, dn, ep) in {"GLAD-L 2026": ("gladl_alert26", "gladl_alertDate26", "L26"),
                              "GLAD-L 2025": ("gladl_alert25", "gladl_alertDate25", "L25"),
                              "GLAD-S2": ("glads2_alert", "glads2_alertDate", "S2")}.items():
        if an not in res:
            continue
        a, d = res[an][1], res[dn][1]
        nz = a > 0
        dd = d[nz & (d > 0)].astype(int)
        base = {"L26": np.datetime64("2026-01-01") - np.timedelta64(1, "D"), "L25": np.datetime64("2025-01-01") - np.timedelta64(1, "D"),
                "S2": np.datetime64(fa.S2_EPOCH.isoformat())}[ep]
        dates = base + dd.astype("timedelta64[D]")
        win = int(((dates >= lo) & (dates <= hi)).sum())
        rng = f"{dates.min()} .. {dates.max()}" if dates.size else "none"
        L_.append(f"{key}: nonzero alert pixels {int(nz.sum())}, without date {int((nz & (d == 0)).sum())}, "
                  f"date range {rng}, dated 2026-07-20..2026-10-12: {win}")
    L_ += ["", "Transient failures:"] + (log or ["none"])
    return "\n".join(L_) + "\n"


def main():
    t0, log = time.time(), []
    res = save(BBOX, OUT, log=log)
    (OUT / "README.txt").write_text(readme(BBOX, res, log, time.time() - t0), encoding="utf-8")
    print((OUT / "README.txt").read_text())


if __name__ == "__main__":
    main()
