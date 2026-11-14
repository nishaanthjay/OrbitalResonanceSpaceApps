"""Unit tests for pipeline/load helpers. In-memory test arrays only; nothing is saved or downloaded."""
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import xarray as xr

sys.path.insert(0, str(Path(__file__).parent))
import load  # noqa: E402


def _gran(date, track=60, frame=173, direction="ASCENDING", bw=("20+5",), pols=("HH", "HV"), proc="2026-10-18"):
    return SimpleNamespace(properties={
        "startTime": f"{date}T09:52:58Z", "pathNumber": track, "frameNumber": frame, "flightDirection": direction,
        "rangeBandwidth": list(bw), "mainBandPolarization": list(pols), "processingDate": proc,
        "sceneName": f"G_{date}_{track}_{frame}_{proc}", "url": "u"})


KEY = load.GroupKey(60, 173, "ASCENDING", "20+5")


def test_select_granules_filters_group_and_pols():
    res = [_gran("2026-06-18"), _gran("2026-06-30", track=161), _gran("2026-07-12", frame=172),
           _gran("2026-07-24", pols=("HH",)), _gran("2026-08-17", bw=("40+5",)), _gran("2026-08-29", direction="DESCENDING")]
    out = load.select_granules(res, KEY)
    assert [g.properties["startTime"][:10] for g in out] == ["2026-06-18"]


def test_select_granules_one_per_date_latest_processing_sorted():
    res = [_gran("2026-07-12"), _gran("2026-06-18", proc="2026-06-20"), _gran("2026-06-18", proc="2026-09-01")]
    out = load.select_granules(res, KEY)
    assert [g.properties["startTime"][:10] for g in out] == ["2026-06-18", "2026-07-12"]
    assert out[0].properties["processingDate"] == "2026-09-01"


def test_to_db_values_and_nodata():
    p = np.array([1.0, 0.1, 0.0, 1e-13, np.nan], dtype=np.float32)
    d = load.to_db(p)
    assert d.dtype == np.float32
    np.testing.assert_allclose(d[:2], [0.0, -10.0], atol=1e-5)
    assert np.isnan(d[2:]).all()


def test_window_slices_utm():
    # 20 m grid in EPSG:32720 around lon -62.75, lat -9.23
    from pyproj import Transformer
    cx, cy = Transformer.from_crs(4326, 32720, always_xy=True).transform(-62.75, -9.23)
    x = cx + np.arange(-100, 100) * 20.0
    y = cy - np.arange(-100, 100) * 20.0  # descending northing, like the GCOV grid
    lon0, lat0 = Transformer.from_crs(32720, 4326, always_xy=True).transform(cx - 500, cy + 500)
    lon1, lat1 = Transformer.from_crs(32720, 4326, always_xy=True).transform(cx + 500, cy - 500)
    ys, xs = load.window_slices(x, y, 32720, (lon0, lat1, lon1, lat0))
    assert 45 <= xs.stop - xs.start <= 56 and 45 <= ys.stop - ys.start <= 56
    with pytest.raises(ValueError):
        load.window_slices(x, y, 32720, (10.0, 10.0, 11.0, 11.0))


def _win(x0=0.0):
    x = x0 + np.arange(4) * 20.0
    y = 100.0 - np.arange(3) * 20.0
    return xr.Dataset({"hh": (("y", "x"), np.full((3, 4), 0.1, np.float32)),
                       "hv": (("y", "x"), np.full((3, 4), 0.01, np.float32))}, coords={"y": y, "x": x})


def test_stack_windows_contract():
    ds = load.stack_windows([_win(), _win()], ["2026-06-18", "2026-06-30"], 32720, {"tile": "T"})
    assert ds["hh_db"].dims == ("time", "y", "x") and ds["hh_db"].dtype == np.float32
    assert set(ds.data_vars) == {"hh_db", "hv_db"}
    assert np.issubdtype(ds["time"].dtype, np.datetime64)
    import rioxarray  # noqa: F401
    assert ds.attrs["crs"] == "EPSG:32720" and ds.rio.crs.to_epsg() == 32720
    assert ds["hh_db"].rio.crs.to_epsg() == 32720
    np.testing.assert_allclose(ds["hv_db"].values, -20.0, atol=1e-4)


def test_stack_roundtrip_netcdf(tmp_path):
    import rioxarray  # noqa: F401
    ds = load.stack_windows([_win(), _win()], ["2026-06-18", "2026-06-30"], 32720, {"tile": "T"})
    p = tmp_path / "s.nc"
    ds.to_netcdf(p)
    r = xr.open_dataset(p)
    assert list(r.data_vars) == ["hh_db", "hv_db"]
    assert r.attrs["crs"] == "EPSG:32720" and r.rio.crs.to_epsg() == 32720 and r["hv_db"].rio.crs.to_epsg() == 32720


def test_stack_windows_rejects_grid_mismatch():
    with pytest.raises(ValueError):
        load.stack_windows([_win(), _win(x0=20.0)], ["2026-06-18", "2026-06-30"], 32720, {})
