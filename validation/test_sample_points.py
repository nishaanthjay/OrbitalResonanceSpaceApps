"""Unit tests for sample_points.py and compute_sample_precision.py.

The forest arrays, polygons and label rows here are tiny hand-made examples that exist only in this file. They
are not project data, never saved as data, and say nothing about precision or accuracy of the method.
(pytest's tmp_path holds throw-away test output only.)
"""
import json

import numpy as np
import pytest
from rasterio.transform import from_origin
from shapely.geometry import Point, box, mapping, shape

import compute_sample_precision as csp
import sample_points as sp

T = from_origin(-60.0, -3.0, 0.001, 0.001)  # 0.001 deg pixels, top-left at (-60, -3)


def fc(*feats):
    return {"type": "FeatureCollection", "features": list(feats)}


def det_fc():
    return fc(
        {"type": "Feature", "geometry": mapping(box(-60.0, -3.005, -59.995, -3.0)),
         "properties": {"id": 1, "date": "2025-04-01"}},
        {"type": "Feature", "geometry": mapping(box(-59.990, -3.020, -59.985, -3.015)),
         "properties": {"id": 2, "date": "2025-04-01"}},
        {"type": "Feature", "geometry": mapping(box(-59.985, -3.005, -59.980, -3.000)),
         "properties": {"id": 3, "date": "2025-03-01"}},
    )


def test_sample_points_strata():
    forest = np.ones((20, 20), bool)
    forest[:, 15:] = False  # no forest east of -59.985
    rows = sp.sample_points(det_fc(), forest, T, "EPSG:4326", n=2, seed=1)
    assert list(rows[0]) == sp.COLUMNS
    d = [r for r in rows if r["stratum"] == "detection"]
    nd = [r for r in rows if r["stratum"] == "non_detection"]
    assert len(d) == 2 and len(nd) == 2
    polys = {f["properties"]["id"]: shape(f["geometry"]) for f in det_fc()["features"]}
    for r in d:
        assert polys[r["detection_id"]].contains(Point(r["lon"], r["lat"]))
        assert r["label"] == "" and r["notes"] == ""
    for r in nd:
        assert not any(p.intersects(Point(r["lon"], r["lat"])) for p in polys.values())
        col, row = ~T * (r["lon"], r["lat"])
        assert forest[int(row), int(col)]
    assert rows == sp.sample_points(det_fc(), forest, T, "EPSG:4326", n=2, seed=1)  # reproducible with a seed


def test_sample_points_holdout_and_short_strata():
    forest = np.ones((20, 20), bool)
    rows = sp.sample_points(det_fc(), forest, T, "EPSG:4326", n=15, seed=0, holdout={"dates": ["2025-03-01"]})
    d = [r for r in rows if r["stratum"] == "detection"]
    assert [r["detection_id"] for r in d] == [3]  # only one holdout detection exists
    assert all(r["date"] == "2025-03-01" for r in rows)
    bbox = (-59.995, -3.02, -59.98, -3.0)
    rows = sp.sample_points(det_fc(), forest, T, "EPSG:4326", n=5, seed=0, holdout={"bbox": bbox})
    for r in rows:
        assert bbox[0] <= r["lon"] <= bbox[2] and bbox[1] <= r["lat"] <= bbox[3]
    assert sorted(r["detection_id"] for r in rows if r["stratum"] == "detection") == [2, 3]


def _labels(*pairs):
    return [{"id": i, "stratum": s, "label": lab} for i, (s, lab) in enumerate(pairs)]


def test_compute_sample_precision_excludes_unsure():
    rows = _labels(("detection", "clearing"), ("detection", " Clearing "), ("detection", "no_clearing"),
                   ("detection", "unsure"), ("non_detection", "no_clearing"), ("non_detection", "unsure"))
    res = csp.compute_sample_precision(rows)
    assert res["hand_labeled"] == {"n_sample": 4, "precision": pytest.approx(2 / 3), "n_unsure": 1}
    assert res["non_detection"]["n_unsure"] == 1 and res["non_detection"]["fraction_clearing"] == 0.0
    lo, hi = res["detection"]["wilson_95"]
    assert 0 <= lo < 2 / 3 < hi <= 1
    all_unsure = csp.compute_sample_precision(_labels(("detection", "unsure")))
    assert all_unsure["hand_labeled"] == {"n_sample": 1, "precision": None, "n_unsure": 1}


def test_compute_sample_precision_refuses_unlabeled():
    with pytest.raises(ValueError, match="valid label"):
        csp.compute_sample_precision(_labels(("detection", "clearing"), ("detection", "")))
    with pytest.raises(ValueError):
        csp.compute_sample_precision(_labels(("detection", "maybe")))


def test_write_hand_labeled_keeps_other_fields(tmp_path):
    p = tmp_path / "metrics.json"
    p.write_text(json.dumps({"agreement": None, "hand_labeled": None, "notes": "x"}))
    csp.write_hand_labeled(str(p), {"n_sample": 4, "precision": 0.5, "n_unsure": 1})
    got = json.loads(p.read_text())
    assert got["hand_labeled"] == {"n_sample": 4, "precision": 0.5, "n_unsure": 1} and got["notes"] == "x"


def test_wilson():
    assert csp.wilson_95(0, 0) is None
    lo, hi = csp.wilson_95(15, 15)
    assert hi == 1.0 and lo < 1.0
