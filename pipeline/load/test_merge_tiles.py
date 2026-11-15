import numpy as np
import pytest
import xarray as xr

from merge_tiles import merge


def tile(x0, y0, nx, ny, v):
    x = x0 + 100.0 * np.arange(nx)
    y = y0 - 100.0 * np.arange(ny)
    a = np.full((2, ny, nx), v, dtype="float32")
    return xr.Dataset({"hh_db": (("time", "y", "x"), a), "hv_db": (("time", "y", "x"), a)},
                      coords={"time": np.array(["2026-06-26", "2026-07-08"], dtype="datetime64[ns]"), "y": y, "x": x},
                      attrs={"crs": "EPSG:32722", "multilook": 5, "granules": "g", "pixel_spacing_m": 100.0,
                             "native_spacing_m": 20.0, "tile": "t"})


def grid():
    return [tile(410, 1000, 3, 2, 1), tile(710, 1000, 2, 2, 2), tile(410, 800, 3, 3, 3), tile(710, 800, 2, 3, 4)]


def test_merge():
    m = merge(grid(), "all")
    assert m.hv_db.shape == (2, 5, 5) and m.x[0] == 410 and m.y[0] == 1000 and m.y[-1] == 600
    assert m.hv_db[0, 0, 4] == 2 and m.hv_db[0, 4, 0] == 3 and m.hv_db[0, 4, 4] == 4
    assert m.attrs["window_first_pixel_xy"] == [370.0, 1040.0] and m.attrs["window_pixels_nx_ny"] == [25, 25]


def test_gap_refused():
    g = grid()
    g[1] = tile(810, 1000, 2, 2, 2)
    with pytest.raises(ValueError):
        merge(g, "all")
    g = grid()
    g[2] = tile(410, 700, 3, 3, 3)
    with pytest.raises(ValueError):
        merge(g, "all")
