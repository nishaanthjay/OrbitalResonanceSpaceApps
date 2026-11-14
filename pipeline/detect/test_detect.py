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
    info = d.run(make_stack(), "2025-04-01", 1.0, 3.0, 1.0, out)
    assert info["n_detections"] == 2
    assert info["total_area_ha"] == pytest.approx(9.0 + 1.44)
    assert info["late_ha"] == pytest.approx(9.0) and info["early_ha"] == pytest.approx(1.44)
    assert info["baseline_dates"] == ["2025-01-01", "2025-02-01", "2025-03-01"]
    assert info["normalization"]["hh_offset_db"] is None  # no forest mask -> default stable mask is absent
    assert (tmp_path / "detections.geojson").exists()
    assert (tmp_path / "change_hh_2025-04-01.tif").exists() and (tmp_path / "change_hv_2025-04-01.tif").exists()
    props = [f["properties"] for f in json.load(open(tmp_path / "detections.geojson"))["features"]]
    assert all("first_hh_date" in p and "first_hv_date" in p for p in props)


# ---- multilook ---------------------------------------------------------------------------------------------

def test_multilook_averages_linear_power_and_keeps_real_spacing():
    s = make_stack(res=30.0, n=20)
    s["hh_db"][0, 0:5, 0:5] = -10.0
    s["hh_db"][0, 0, 0] = 0.0  # one bright pixel in the first 5x5 block
    m = d.multilook(s, 5)
    assert m.sizes["y"] == 4 and m.sizes["x"] == 4
    expected = 10 * np.log10((24 * 0.1 + 1.0) / 25)  # mean of power, not of dB
    assert float(m["hh_db"][0, 0, 0]) == pytest.approx(expected, abs=1e-4)
    da = m["hh_db"].isel(time=0).rio.write_crs(CRS_UTM)
    assert d.pixel_area_ha(da)[0, 0] == pytest.approx(150 * 150 / 1e4)  # 5 * 30 m -> 2.25 ha per pixel
    assert d.pixel_spacing(da) == {"x": 150.0, "y": 150.0, "unit": "metre"}
    assert d.multilook(s, 1) is s
    with pytest.raises(ValueError):
        d.multilook(s, 0)


def test_multilook_sets_minimum_detectable_size():
    # a 10x10-pixel (30 m) clearing survives n=5 looks; a 2x2 one is diluted below threshold
    s = d.multilook(make_stack(res=30.0, n=20), 5)
    mask, _ = d.apply_thresholds(*d.change_maps(s, "2025-04-01"), None, 3.0)
    lab = d.cluster_and_filter(mask, min_ha=0.0)
    assert lab.values.max() >= 1
    small = make_stack(res=30.0, n=20)
    small["hv_db"][3] = -16.0
    small["hv_db"][3, 15:17, 15:17] -= 5  # only the 2x2 block (0.36 ha)
    m2, _ = d.apply_thresholds(*d.change_maps(d.multilook(small, 5), "2025-04-01"), None, 3.0)
    assert int(m2.sum()) == 0


# ---- stable-forest normalization ---------------------------------------------------------------------------

def test_normalize_stable_formula():
    d_hh, _ = d.change_maps(make_stack(), "2025-04-01")
    shifted = (d_hh + 0.7).rename("d_hh")  # scene-wide +0.7 dB (e.g. wet canopy)
    stable = xr.DataArray(np.ones(shifted.shape, bool), dims=shifted.dims)
    out, off, k = d.normalize_stable(shifted, stable)
    # median over all 400 px: 116 changed HH px (+2 / +3) do not move it, 284 px sit at +0.7
    assert off == pytest.approx(0.7, abs=1e-5) and k == 400
    assert float(out[0, 19]) == pytest.approx(0.0, abs=1e-5)
    assert float(out[5, 5]) == pytest.approx(2.0, abs=1e-4)
    assert out.dtype == np.float32


def test_normalize_stable_uses_only_mask_pixels_and_skips_nan():
    d_hh, _ = d.change_maps(make_stack(), "2025-04-01")
    stable = np.zeros(d_hh.shape, bool)
    stable[15:19, 2:6] = True  # only the +3 dB block
    vals = d_hh.values.copy()
    vals[15, 2] = np.nan
    _, off, k = d.normalize_stable(d_hh.copy(data=vals), xr.DataArray(stable, dims=d_hh.dims))
    assert off == pytest.approx(3.0, abs=1e-4) and k == 15
    with pytest.raises(ValueError):
        d.normalize_stable(d_hh, xr.DataArray(np.zeros(d_hh.shape, bool), dims=d_hh.dims))
    with pytest.raises(ValueError):
        d.normalize_stable(d_hh, xr.DataArray(np.ones((3, 3), bool), dims=("y", "x")))


def test_run_normalization_removes_scene_wide_shift(tmp_path):
    s = make_stack()
    s["hh_db"][3] += 1.5  # whole scene brighter on the last date: not clearing
    forest = xr.DataArray(np.ones((20, 20), bool), dims=("y", "x"))
    raw = d.run(s, "2025-04-01", 1.0, 3.0, 1.0, str(tmp_path / "a"), stable_mask=None)
    assert raw["n_detections"] == 1  # everything fires HH and merges into one scene-sized cluster
    norm = d.run(s, "2025-04-01", 1.0, 3.0, 1.0, str(tmp_path / "b"), forest_mask=forest)  # stable = forest
    assert norm["normalization"]["hh_offset_db"] == pytest.approx(1.5, abs=1e-4)
    assert norm["n_detections"] == 2 and norm["total_area_ha"] == pytest.approx(9.0 + 1.44)


# ---- split + tuning sweep ----------------------------------------------------------------------------------

def test_make_split_rules():
    assert d.make_split() is None
    sp = d.make_split(tune_dates=["2025-03-01"], holdout_dates=["2025-04-01"])
    assert sp.by == "dates" and sp.to_dict() == {"by": "dates", "tune": ["2025-03-01"], "holdout": ["2025-04-01"]}
    sb = d.make_split(tune_bbox=(0, 0, 1, 1), holdout_bbox=(1, 0, 2, 1))  # shared edge is fine
    assert sb.by == "bbox"
    for bad in [dict(tune_dates=["2025-03-01"], holdout_dates=["2025-03-01"]),
                dict(tune_bbox=(0, 0, 1, 1), holdout_bbox=(0.5, 0, 2, 1)),
                dict(tune_bbox=(1, 0, 0, 1), holdout_bbox=(2, 0, 3, 1)),
                dict(tune_bbox=(0, 0, 1, 1)),
                dict(tune_dates=["2025-03-01"]),
                dict(tune_bbox=(0, 0, 1, 1), holdout_bbox=(1, 0, 2, 1), tune_dates=["2025-03-01"])]:
        with pytest.raises(ValueError):
            d.make_split(**bad)


def test_bbox_mask_uses_real_crs():
    s = make_stack()
    tmpl = s["hh_db"].isel(time=0).rio.write_crs(CRS_UTM)
    from pyproj import Transformer
    lon, lat = Transformer.from_crs(CRS_UTM, 4326, always_xy=True).transform(
        float(s["x"][9]) + 1, float(s["y"][19]) - 1)  # just right of column 9, below the last row
    lon0, lat0 = Transformer.from_crs(CRS_UTM, 4326, always_xy=True).transform(
        float(s["x"][0]) - 1, float(s["y"][0]) + 1)
    m = d.bbox_mask(tmpl, (lon0, lat, lon, lat0))
    assert bool(m[0, 0]) and bool(m[19, 9]) and not bool(m[0, 10])


def test_sweep_uses_tune_dates_only():
    s = make_stack()  # all changes are on 2025-04-01
    sp = d.make_split(tune_dates=["2025-03-01"], holdout_dates=["2025-04-01"])
    rows = d.sweep_thresholds(s, sp, [1.0, 2.5], [3.0], min_ha=0.1)
    assert [r["n_detections"] for r in rows] == [0, 0]  # the holdout-date changes are never seen
    assert all(list(r["per_date"]) == ["2025-03-01"] for r in rows)
    with pytest.raises(ValueError):
        d.sweep_thresholds(s, sp, [1.0], [3.0], 0.1, dates=["2025-04-01"])  # holdout date refused
    sp2 = d.make_split(tune_dates=["2025-04-01"], holdout_dates=["2025-03-01"])
    rows = d.sweep_thresholds(s, sp2, [1.0, 2.5], [3.0, 6.0], min_ha=0.1)
    got = {(r["hh_thresh"], r["hv_thresh"]): r["n_detections"] for r in rows}
    assert got == {(1.0, 3.0): 3, (1.0, 6.0): 2, (2.5, 3.0): 3, (2.5, 6.0): 1}
    assert rows[0]["area_ha"] == pytest.approx(9.0 + 0.36 + 1.44)


def test_sweep_bbox_split_counts_only_tune_area():
    s = make_stack()
    from pyproj import Transformer
    tr = Transformer.from_crs(CRS_UTM, 4326, always_xy=True).transform
    w, n_ = tr(float(s["x"][0]) - 15, float(s["y"][0]) + 15)
    mid, south = tr(float(s["x"][13]) + 15, float(s["y"][19]) - 15)
    east, _ = tr(float(s["x"][19]) + 15, float(s["y"][0]))
    sp = d.make_split(tune_bbox=(w, south, mid, n_), holdout_bbox=(mid, south, east, n_))
    rows = d.sweep_thresholds(s, sp, [1.0], [3.0], 0.1, dates=["2025-04-01"])
    assert rows[0]["n_detections"] == 2  # big + HH-only blocks (cols <= 13); the small block at cols 15-16 is holdout
    with pytest.raises(ValueError):
        d.sweep_thresholds(s, sp, [1.0], [3.0], 0.1)  # bbox split needs dates
    with pytest.raises(ValueError):
        d.sweep_thresholds(s, None, [1.0], [3.0], 0.1, dates=["2025-04-01"])


# ---- first_hh_date / first_hv_date -------------------------------------------------------------------------

def test_first_fire_dates(tmp_path):
    s = make_stack()
    s["hh_db"][2, 2:12, 2:12] += 3  # big block: HH rises on 03-01 (early) ...
    s["hh_db"][3, 2:12, 2:12] = -7.0  # ... stays up on 04-01, when HV drops (late)
    out = str(tmp_path)
    d.run(s, "2025-04-01", 1.0, 3.0, 1.0, out)
    ps = {round(p["area_ha"], 2): p for p in
          (f["properties"] for f in json.load(open(tmp_path / "detections.geojson"))["features"])}
    assert ps[9.0]["first_hh_date"] == "2025-03-01" and ps[9.0]["first_hv_date"] == "2025-04-01"
    assert ps[1.44]["first_hh_date"] == "2025-04-01" and ps[1.44]["first_hv_date"] is None


def test_first_fire_dates_majority_rule():
    lab = xr.DataArray(np.array([[1, 1], [1, 1]], np.int32), dims=("y", "x"))
    one = np.array([[True, False], [False, False]])
    half = np.array([[True, True], [False, False]])
    none = np.zeros((2, 2), bool)
    got = d.first_fire_dates(lab, {"2025-02-01": (one, none), "2025-03-01": (half, none)})
    assert got == [("2025-03-01", None)]
    assert d.first_fire_dates(xr.DataArray(np.zeros((2, 2), np.int32), dims=("y", "x")), {}) == []


# ---- summary.json ------------------------------------------------------------------------------------------

def _row(date, n):
    return {"date": date, "n_detections": n, "total_area_ha": 1.0 * n, "early_ha": 0.5 * n, "late_ha": 0.5 * n,
            "baseline_dates": [], "normalization": {}}  # extra keys must not reach summary.json


def test_merge_summary_matches_contract_section_6():
    t = {"split": "tune: dates 2025-03-01; holdout: dates 2025-04-01", "hh_thresh": 1.0, "hv_thresh": 3.0}
    s = d.merge_summary(None, ["2025-01-01", "2025-04-01", "2025-05-01"],
                        [_row("2025-05-01", 1), _row("2025-04-01", 2)], t)
    assert set(s) == {"dates", "per_date", "tuning"}
    assert s["dates"] == ["2025-01-01", "2025-04-01", "2025-05-01"]
    assert [r["date"] for r in s["per_date"]] == ["2025-04-01", "2025-05-01"]
    assert all(set(r) == set(d.SUMMARY_ROW_KEYS) for r in s["per_date"])
    s2 = d.merge_summary(s, ["2025-06-01"], [_row("2025-04-01", 5)], None)  # same date replaced, others kept
    assert [(r["date"], r["n_detections"]) for r in s2["per_date"]] == [("2025-04-01", 5), ("2025-05-01", 1)]
    assert s2["dates"] == ["2025-01-01", "2025-04-01", "2025-05-01", "2025-06-01"]
    assert s2["tuning"] is None


def test_tuning_entry_needs_sweep_on_same_split():
    sp = d.make_split(tune_dates=["2025-03-01"], holdout_dates=["2025-04-01"])
    log = {"tuning": {"split": sp.to_dict(), "results": []}}
    assert d.tuning_entry(log, sp, 1.0, 3.0) == {
        "split": "tune: dates 2025-03-01; holdout: dates 2025-04-01", "hh_thresh": 1.0, "hv_thresh": 3.0}
    sb = d.make_split(tune_bbox=(-60, -4, -59.5, -3), holdout_bbox=(-59.5, -4, -59, -3))
    assert d.describe_split(sb) == "tune: bbox W,S,E,N -60,-4,-59.5,-3; holdout: bbox W,S,E,N -59.5,-4,-59,-3"
    other = d.make_split(tune_dates=["2025-02-01"], holdout_dates=["2025-04-01"])
    assert d.tuning_entry(log, other, 1.0, 3.0) is None
    assert d.tuning_entry({"tuning": None}, sp, 1.0, 3.0) is None
    assert d.tuning_entry(log, None, 1.0, 3.0) is None


def test_merge_log():
    split_a = {"by": "dates", "tune": ["2025-03-01"], "holdout": ["2025-04-01"]}
    s1 = d.merge_log(None, {"split": split_a, "tuning": {"split": split_a, "results": []}})
    s2 = d.merge_log(s1, {"split": split_a, "dates": {"2025-04-01": {"n_detections": 2}}})
    assert s2["tuning"] == {"split": split_a, "results": []}  # same split: sweep kept
    s3 = d.merge_log(s2, {"split": split_a, "dates": {"2025-05-01": {"n_detections": 1}}})
    assert set(s3["dates"]) == {"2025-04-01", "2025-05-01"}
    s4 = d.merge_log(s3, {"split": None, "dates": {"2025-04-01": {"n_detections": 5}}})
    assert s4["tuning"] is None and s4["dates"]["2025-04-01"]["n_detections"] == 5


def test_export_summary_roundtrip(tmp_path):
    p = str(tmp_path / "summary.json")
    d.export_summary(p, ["2025-04-01"], [_row("2025-04-01", 2)], None)
    d.export_summary(p, ["2025-05-01"], [_row("2025-05-01", 1)], None)
    got = json.load(open(p))
    assert [r["date"] for r in got["per_date"]] == ["2025-04-01", "2025-05-01"] and got["tuning"] is None


# ---- CLI rules ---------------------------------------------------------------------------------------------

def _args(*argv):
    p = d.build_parser()
    return d.check_args(p.parse_args(["--stack", "x.nc", "--min-ha", "1", *argv]), p)


def test_cli_final_requires_forest_mask():
    with pytest.raises(SystemExit):
        _args("--date", "2025-04-01", "--hh-thresh", "1", "--hv-thresh", "3", "--final")
    assert _args("--date", "2025-04-01", "--hh-thresh", "1", "--hv-thresh", "3", "--final",
                 "--forest-mask", "f.tif") is None


def test_cli_rules():
    with pytest.raises(SystemExit):
        _args("--date", "2025-04-01")  # thresholds missing
    with pytest.raises(SystemExit):
        _args("--sweep-hh", "1", "--sweep-hv", "3")  # sweep without a split
    with pytest.raises(SystemExit):
        _args("--date", "2025-04-01", "--hh-thresh", "1", "--hv-thresh", "3", "--multilook", "0")
    sp = _args("--sweep-hh", "1", "2", "--sweep-hv", "3", "--tune-dates", "2025-03-01", "--holdout-dates", "2025-04-01")
    assert sp.by == "dates"
    with pytest.raises(SystemExit):
        _args("--sweep-hh", "1", "--sweep-hv", "3", "--tune-bbox", "0", "0", "1", "1", "--holdout-bbox", "1", "0", "2", "1")
    assert d.build_parser().parse_args(["--stack", "x", "--min-ha", "1"]).multilook == 5
