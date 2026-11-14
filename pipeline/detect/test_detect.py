"""Unit tests for detect.py.

All arrays here are tiny in-memory SYNTHETIC stacks that exist only to exercise the code. They are never saved as
project data or images, never used in demos, and say nothing about detection accuracy. (pytest's tmp_path holds
throw-away test output only.)
"""
import json

import numpy as np
import pytest
import rasterio
import xarray as xr
from rasterio.transform import from_origin

import detect as d

CRS_UTM = "EPSG:32722"  # metres, Brazil-ish zone; arbitrary for tests


def make_stack(res=30.0, crs=CRS_UTM, x0=500000.0, y0=9000000.0, n=20):
    """4 dates; on the last date: 10x10 block HV -5 / HH +2 (late), 2x2 block HV -5 (small), 4x4 block HH +3 only (early)."""
    times = np.array(["2025-01-01", "2025-02-01", "2025-03-01", "2025-04-01"], dtype="datetime64[ns]")
    x = x0 + res * np.arange(n)
    y = y0 - res * np.arange(n)  # descending, like real rasters
    hh = np.full((4, n, n), -10.0, np.float32)
    hv = np.full((4, n, n), -16.0, np.float32)
    hv[3, 2:12, 2:12] -= 5
    hh[3, 2:12, 2:12] += 2
    hv[3, 15:17, 15:17] -= 5
    hh[3, 15:19, 2:6] += 3
    return xr.Dataset(
        {"hh_db": (("time", "y", "x"), hh), "hv_db": (("time", "y", "x"), hv)},
        coords={"time": times, "y": y, "x": x},
        attrs={"crs": crs},
    )


def test_baseline_uses_only_earlier_dates():
    s = make_stack()
    s["hh_db"][1] += 3  # 2025-02-01 differs
    b = d.baseline(s, "2025-03-01", average="db")
    assert float(b["hh_db"][0, 0]) == pytest.approx(-8.5)  # mean(-10, -7); excludes 03-01 and 04-01
    with pytest.raises(ValueError):
        d.baseline(s, "2025-01-01")


def test_baseline_linear_vs_db():
    s = make_stack()
    s["hh_db"][0] = -10.0
    s["hh_db"][1] = 0.0
    lin = float(d.baseline(s, "2025-03-01", "linear")["hh_db"][0, 0])
    db = float(d.baseline(s, "2025-03-01", "db")["hh_db"][0, 0])
    assert lin == pytest.approx(10 * np.log10((0.1 + 1.0) / 2), abs=1e-4)
    assert db == pytest.approx(-5.0)
    assert lin > db  # arithmetic mean of power >= geometric mean


def test_change_maps():
    d_hh, d_hv = d.change_maps(make_stack(), "2025-04-01")
    assert d_hh.dtype == np.float32
    assert float(d_hv[5, 5]) == pytest.approx(-5.0, abs=1e-4)
    assert float(d_hh[5, 5]) == pytest.approx(2.0, abs=1e-4)
    assert float(d_hh[0, 19]) == pytest.approx(0.0, abs=1e-4)
    with pytest.raises(KeyError):
        d.change_maps(make_stack(), "2025-04-02")


def test_thresholds_and_stage():
    d_hh, d_hv = d.change_maps(make_stack(), "2025-04-01")
    mask, stage = d.apply_thresholds(d_hh, d_hv, hh_thresh=1.0, hv_thresh=3.0)
    assert int(stage[5, 5]) == d.STAGE_LATE  # both fire -> late (HV-led)
    assert int(stage[16, 16]) == d.STAGE_LATE  # HV only
    assert int(stage[16, 3]) == d.STAGE_EARLY  # HH only
    assert int(stage[0, 19]) == d.STAGE_NONE and not bool(mask[0, 19])
    assert int(mask.sum()) == 100 + 4 + 16


def test_thresholds_are_parameters():
    d_hh, d_hv = d.change_maps(make_stack(), "2025-04-01")
    m_lo, _ = d.apply_thresholds(d_hh, d_hv, 1.0, 3.0)
    m_hi, _ = d.apply_thresholds(d_hh, d_hv, 2.5, 6.0)  # stricter
    assert int(m_hi.sum()) == 16  # only the HH +3 block clears 2.5 dB
    assert int(m_hi.sum()) < int(m_lo.sum())
    m_off, _ = d.apply_thresholds(d_hh, d_hv, None, 3.0)  # HH disabled
    assert int(m_off.sum()) == 104


def test_mask_nonforest():
    d_hh, d_hv = d.change_maps(make_stack(), "2025-04-01")
    mask, _ = d.apply_thresholds(d_hh, d_hv, 1.0, 3.0)
    forest = np.ones(mask.shape, bool)
    forest[:, :8] = False  # cuts the HH-only block (cols 2:6) and part of the 10x10 block (cols 2:12)
    out = d.mask_nonforest(mask, xr.DataArray(forest, dims=mask.dims))
    assert int(out.sum()) == 10 * 4 + 4  # cols 8:12 of the big block + small block
    with pytest.raises(ValueError):
        d.mask_nonforest(mask, xr.DataArray(np.ones((3, 3), bool), dims=("y", "x")))


def test_cluster_filter_uses_real_pixel_area():
    s = make_stack(res=30.0)  # 0.09 ha / pixel: big=9 ha, small=0.36 ha, early=1.44 ha
    mask, _ = d.apply_thresholds(*d.change_maps(s, "2025-04-01"), 1.0, 3.0)
    assert d.pixel_area_ha(mask)[0, 0] == pytest.approx(0.09)
    lab = d.cluster_and_filter(mask, min_ha=1.0)
    assert sorted(np.unique(lab.values)) == [0, 1, 2]  # small block dropped
    lab = d.cluster_and_filter(mask, min_ha=0.1)
    assert lab.values.max() == 3
    # same pixels on a 4x coarser area grid (60 m) -> small block is 1.44 ha and now survives min_ha=1
    s2 = make_stack(res=60.0)
    mask2, _ = d.apply_thresholds(*d.change_maps(s2, "2025-04-01"), 1.0, 3.0)
    assert d.cluster_and_filter(mask2, min_ha=1.0).values.max() == 3


def test_pixel_area_geographic_is_latitude_dependent():
    s = make_stack(crs="EPSG:4326", res=0.001, x0=-55.0, y0=0.0)
    a = d.pixel_area_ha(s["hh_db"].isel(time=0).rio.write_crs("EPSG:4326"))
    assert a[0, 0] == pytest.approx(111.32 * 110.57 * 1e-6 * 100, rel=0.01)  # 0.001 deg cell: ~1.23 ha at the equator
    s_hi = make_stack(crs="EPSG:4326", res=0.001, x0=-55.0, y0=60.0)
    a_hi = d.pixel_area_ha(s_hi["hh_db"].isel(time=0).rio.write_crs("EPSG:4326"))
    assert a_hi[0, 0] < 0.6 * a[0, 0]


def _chain(s, date="2025-04-01", min_ha=1.0):
    d_hh, d_hv = d.change_maps(s, date)
    mask, stage = d.apply_thresholds(d_hh, d_hv, 1.0, 3.0)
    return d_hh, d_hv, stage, d.cluster_and_filter(mask, min_ha)


def test_export_geojson_contract_and_merge(tmp_path):
    d_hh, d_hv, stage, lab = _chain(make_stack())
    out = str(tmp_path / "detections.geojson")
    assert d.export_geojson(lab, d_hh, d_hv, stage, "2025-04-01", out) == 2
    fc = json.load(open(out))
    assert fc["type"] == "FeatureCollection" and len(fc["features"]) == 2
    for f in fc["features"]:
        assert f["geometry"]["type"] == "Polygon"
        lon, lat = f["geometry"]["coordinates"][0][0]
        assert -60 < lon < -48 and -90 < lat < 0  # EPSG:4326 degrees, not metres
        p = f["properties"]
        assert set(p) == {"id", "date", "area_ha", "d_hh", "d_hv", "stage"}
        assert isinstance(p["id"], int) and isinstance(p["area_ha"], float) and p["date"] == "2025-04-01"
    by_area = sorted(fc["features"], key=lambda f: f["properties"]["area_ha"])
    assert by_area[1]["properties"]["area_ha"] == pytest.approx(9.0)
    assert by_area[1]["properties"]["stage"] == "late"
    assert by_area[0]["properties"]["stage"] == "early"
    # another date: replaces same date, keeps other dates, ids stay unique
    d.export_geojson(lab, d_hh, d_hv, stage, "2025-05-01", out)
    d.export_geojson(lab, d_hh, d_hv, stage, "2025-05-01", out)
    ps = [f["properties"] for f in json.load(open(out))["features"]]
    assert sorted(p["date"] for p in ps) == ["2025-04-01"] * 2 + ["2025-05-01"] * 2
    assert len({p["id"] for p in ps}) == 4


def test_export_geojson_empty(tmp_path):
    s = make_stack()
    d_hh, d_hv, stage, lab = _chain(s, min_ha=1e6)
    out = str(tmp_path / "e.geojson")
    assert d.export_geojson(lab, d_hh, d_hv, stage, "2025-04-01", out) == 0
    assert json.load(open(out))["features"] == []


def test_export_cog(tmp_path):
    d_hh, _ = d.change_maps(make_stack(), "2025-04-01")
    out = str(tmp_path / "change_hh_2025-04-01.tif")
    d.export_cog(d_hh, out)
    with rasterio.open(out) as r:
        assert r.crs.to_epsg() == 4326
        assert r.dtypes[0] == "float32"
        assert r.profile["tiled"]
        assert np.nanmax(r.read(1)) == pytest.approx(3.0, abs=0.5)  # the +3 dB block survives reprojection
    assert (tmp_path / "change_hh_2025-04-01.tif").stat().st_size < d.MAX_COG_BYTES


def test_load_forest_mask(tmp_path):
    s = make_stack()
    tmpl = s["hh_db"].isel(time=0).rio.write_crs(CRS_UTM)
    p = str(tmp_path / "forest.tif")
    arr = np.zeros((20, 20), np.uint8)
    arr[:, 10:] = 1
    with rasterio.open(p, "w", driver="GTiff", height=20, width=20, count=1, dtype="uint8",
                       crs=CRS_UTM, transform=from_origin(500000 - 0, 9000000 + 15, 30, 30)) as r:
        r.write(arr, 1)
    fm = d.load_forest_mask(p, tmpl)
    assert fm.shape == (20, 20) and bool(fm[5, 15]) and not bool(fm[5, 2])


def test_run_end_to_end(tmp_path):
    out = str(tmp_path)
    n = d.run(make_stack(), "2025-04-01", 1.0, 3.0, 1.0, out)
    assert n == 2
    assert (tmp_path / "detections.geojson").exists()
    assert (tmp_path / "change_hh_2025-04-01.tif").exists() and (tmp_path / "change_hv_2025-04-01.tif").exists()
