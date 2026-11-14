"""Tests for web_patches.py on a tiny in-memory SYNTHETIC stack (test-only; never saved as data, never used in demos)."""
import numpy as np
import pytest
import xarray as xr
from pyproj import Transformer
from shapely.geometry import box, mapping
from shapely.ops import transform as shp_transform

import web_patches as wp

CRS = "EPSG:32722"
X0, Y0, DATES = 500000.0, 9000000.0, ["2025-01-01", "2025-02-01", "2025-03-01", "2025-04-01"]
TO_LL = Transformer.from_crs(CRS, 4326, always_xy=True).transform


def make_stack():
    """20x20 px at 20 m (4x4 blocks of 100 m after a 5x5 multilook). HH -10 / HV -16 dB, +3 / -5 on block (1, 1) from date 3."""
    n = 20
    hh = np.full((4, n, n), -10.0, np.float32)
    hv = np.full((4, n, n), -16.0, np.float32)
    hh[2:, 5:10, 5:10] += 3
    hv[2:, 5:10, 5:10] -= 5
    return xr.Dataset({"hh_db": (("time", "y", "x"), hh), "hv_db": (("time", "y", "x"), hv)},
                      coords={"time": np.array(DATES, dtype="datetime64[ns]"), "y": Y0 - 20.0 * np.arange(n),
                              "x": X0 + 20.0 * np.arange(n)}, attrs={"crs": CRS})


def det(date, stage, blocks):
    """A detection feature made of 100 m blocks (row, col) of the multilooked grid, in EPSG:4326."""
    boxes = [box(X0 - 10 + 100 * c, Y0 + 10 - 100 * (r + 1), X0 - 10 + 100 * (c + 1), Y0 + 10 - 100 * r) for r, c in blocks]
    from shapely.ops import unary_union
    g = shp_transform(TO_LL, unary_union(boxes))
    return {"type": "Feature", "geometry": mapping(g),
            "properties": {"id": 1, "date": date, "area_ha": 1.0, "d_hh": 0.0, "d_hv": 0.0, "stage": stage,
                           "first_hh_date": date if stage == "early" else None, "first_hv_date": date if stage == "late" else None}}


def fc(*feats):
    return {"type": "FeatureCollection", "features": list(feats)}


def test_same_place_on_two_dates_is_one_patch_with_first_date_and_series():
    out = wp.build_patches(make_stack(), fc(det("2025-04-01", "late", [(1, 1)]), det("2025-03-01", "early", [(1, 1)])), n_looks=5)
    assert len(out["features"]) == 1 and out["series_dates"] == DATES
    p = out["features"][0]["properties"]
    assert p["first_date"] == p["date"] == "2025-03-01"
    assert p["stage"] == "early"  # stage at the FIRST date (HH-led)
    assert p["area_ha"] == pytest.approx(1.0, rel=1e-3)  # one 100 m x 100 m block
    assert p["hh_series_db"] == [-10.0, -10.0, -7.0, -7.0] and p["hv_series_db"] == [-16.0, -16.0, -21.0, -21.0]
    assert p["first_hh_date"] == "2025-03-01" and p["first_hv_date"] == "2025-04-01"
    assert p["d_hh"] == pytest.approx(3.0, abs=0.01) and p["d_hv"] == pytest.approx(-5.0, abs=0.01)


def test_separate_and_touching_patches_and_ids():
    out = wp.build_patches(make_stack(), fc(det("2025-04-01", "late", [(3, 3)]), det("2025-03-01", "late", [(1, 1)]),
                                            det("2025-04-01", "early", [(1, 2)])), n_looks=5)
    fs = out["features"]
    assert [f["properties"]["id"] for f in fs] == [1, 2]
    assert [f["properties"]["first_date"] for f in fs] == ["2025-03-01", "2025-04-01"]
    assert fs[0]["properties"]["area_ha"] == pytest.approx(2.0, rel=1e-3)  # (1,1) + touching (1,2) merge (8-connected)
    for f in fs:
        lon, lat = f["geometry"]["coordinates"][0][0]
        assert -60 < lon < -50 and -90 < lat < 0  # EPSG:4326 degrees


def test_split_label_from_representative_point():
    out_all = wp.build_patches(make_stack(), fc(det("2025-03-01", "late", [(1, 1)])), tune_bbox=(-60, -89, -40, 0), n_looks=5)
    assert out_all["features"][0]["properties"]["split"] == "tune"
    out_none = wp.build_patches(make_stack(), fc(det("2025-03-01", "late", [(1, 1)])), n_looks=5)
    assert out_none["features"][0]["properties"]["split"] == "buffer"


def test_patch_summary_matches_the_patches():
    out = wp.build_patches(make_stack(), fc(det("2025-04-01", "late", [(3, 3)]), det("2025-03-01", "early", [(1, 1)]),
                                            det("2025-04-01", "late", [(1, 1)])), n_looks=5)
    s = wp.patch_summary(out, {"split": "x", "hh_thresh": 1.0, "hv_thresh": 1.0})
    assert s["dates"] == DATES and s["tuning"]["hv_thresh"] == 1.0
    rows = {r["date"]: r for r in s["per_date"]}
    assert set(rows) == {"2025-03-01", "2025-04-01"}  # (1,1) appears once, on its first date
    assert rows["2025-03-01"]["n_detections"] == 1 and rows["2025-03-01"]["early_ha"] == pytest.approx(1.0, rel=1e-3)
    assert rows["2025-04-01"]["late_ha"] == pytest.approx(1.0, rel=1e-3) and rows["2025-04-01"]["early_ha"] == 0.0
