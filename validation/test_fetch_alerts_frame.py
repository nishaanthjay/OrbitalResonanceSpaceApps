"""Synthetic read_saved check, plus (needs network) equality with scale.read_alerts on the 20 km window."""
import sys
import tempfile
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

sys.path.insert(0, str(Path(__file__).parent))
import fetch_alerts_frame as f  # noqa: E402


def _w(p, arr, tr):
    with rasterio.open(p, "w", driver="GTiff", height=arr.shape[0], width=arr.shape[1], count=1,
                       dtype=arr.dtype, crs="EPSG:4326", transform=tr) as ds:
        ds.write(arr, 1)


def test_synthetic():
    tr = from_origin(-55.0, -6.0, 0.01, 0.01)
    with tempfile.TemporaryDirectory() as d:
        _w(f"{d}/gladl_alert26.tif", np.array([[0, 2], [3, 3]], np.uint8), tr)
        _w(f"{d}/gladl_alertDate26.tif", np.array([[5, 1], [0, 32]], np.uint16), tr)
        _w(f"{d}/glads2_alert.tif", np.array([[1, 0], [4, 2]], np.uint8), tr)
        _w(f"{d}/glads2_alertDate.tif", np.array([[10, 7], [0, 1]], np.uint16), tr)
        dt, lon, lat = f.read_saved("GLAD-L", d)
        assert list(dt.astype(str)) == ["2026-01-01", "2026-02-01"]
        assert np.allclose(lon, [-54.985, -54.985]) and np.allclose(lat, [-6.005, -6.015])
        dt, lon, lat = f.read_saved("GLAD-S2", d)
        assert list(dt.astype(str)) == ["2019-01-10", "2019-01-01"]


def test_matches_scale():
    import scale
    bb = (-54.79, -8.29, -54.608, -8.109)
    with tempfile.TemporaryDirectory() as d:
        f.save(bb, d, names={"gladl_alert26", "gladl_alertDate26", "glads2_alert", "glads2_alertDate"})
        for s in ("GLAD-L", "GLAD-S2"):
            a, b = f.read_saved(s, d), scale.read_alerts(bb, s)[:3]
            assert all(np.array_equal(x, y) for x, y in zip(a, b)), s
            print(s, len(a[0]), "pixels identical")


if __name__ == "__main__":
    test_synthetic()
    test_matches_scale()
    print("ok")
