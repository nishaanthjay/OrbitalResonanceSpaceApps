"""Unit tests for score.py.

All polygons and alert rows here are tiny hand-made examples that exist only in this file to exercise the code.
They are not alert data, never saved as project data, and say nothing about agreement or accuracy. No network:
the GFW API is replaced by a fake. (pytest's tmp_path holds throw-away test output only.)
"""
import json
import sys

import pytest
from shapely.geometry import box, mapping

import score as sc


def fc(*feats):
    return {"type": "FeatureCollection", "features": list(feats)}


def feat(geom, **props):
    return {"type": "Feature", "geometry": mapping(geom), "properties": props}


# ---- grid and rows -> polygons -----------------------------------------------------------------------------

def test_grid_from_asset_uri():
    # URI shapes as returned by GET /dataset/<id>/latest (wur_radd_alerts, umd_glad_landsat_alerts)
    assert sc.grid_from_asset_uri("s3://b/wur_radd_alerts/v1/raster/epsg-4326/10/100000/date_conf/geotiff/{tile_id}.tif") \
        == pytest.approx(1e-4)
    assert sc.grid_from_asset_uri("s3://b/x/v1/raster/epsg-4326/10/40000/date_conf/geotiff/{tile_id}.tif") \
        == pytest.approx(2.5e-4)
    with pytest.raises(ValueError):
        sc.grid_from_asset_uri("s3://b/x/v1/raster/epsg-3857/zoom_14/date_conf_default/geotiff/{tile_id}.tif")


def test_dataset_pixel_deg_reads_metadata():
    def get(url, body=None, headers=None):
        assert url.endswith("/dataset/wur_radd_alerts/latest") and body is None
        return {"data": {"assets": [["COG", "s3://b/cog/default.tif"],
                                    ["Raster tile set", "s3://b/raster/epsg-4326/10/100000/date_conf/x.tif"]]}}
    assert sc.dataset_pixel_deg("wur_radd_alerts", get=get) == pytest.approx(1e-4)


def _rows():
    # three edge-adjacent 1e-4 deg pixels on one date + one pixel on another date (pixel centres end in 5)
    return [
        {"longitude": -60.00005, "latitude": -3.00005, "wur_radd_alerts__date": "2025-04-02"},
        {"longitude": -59.99995, "latitude": -3.00005, "wur_radd_alerts__date": "2025-04-02"},
        {"longitude": -59.99985, "latitude": -3.00005, "wur_radd_alerts__date": "2025-04-02"},
        {"longitude": -59.99005, "latitude": -3.00505, "wur_radd_alerts__date": "2025-04-20"},
    ]


def test_rows_to_features_unions_same_date_patches():
    out = sc.rows_to_features(_rows(), "wur_radd_alerts__date", 1e-4, "RADD")
    assert [f["properties"] for f in out["features"]] == [{"source": "RADD", "date": "2025-04-02"},
                                                          {"source": "RADD", "date": "2025-04-20"}]
    from shapely.geometry import shape
    g = shape(out["features"][0]["geometry"])
    assert g.geom_type == "Polygon"
    assert g.bounds == pytest.approx((-60.0001, -3.0001, -59.9998, -3.0), abs=1e-9)
    with pytest.raises(ValueError):  # not a pixel centre of this grid
        sc.rows_to_features([{"longitude": -60.0, "latitude": -3.00005, "wur_radd_alerts__date": "2025-04-02"}],
                            "wur_radd_alerts__date", 1e-4, "RADD")


# ---- load_reference with a fake API ------------------------------------------------------------------------

class FakeAPI:
    def __init__(self, rows, total_ha):
        self.rows, self.total, self.calls = rows, total_ha, []

    def __call__(self, url, body=None, headers=None):
        self.calls.append((url, body, headers))
        if body is None:
            return {"data": {"assets": [["Raster tile set", "s3://b/raster/epsg-4326/10/100000/date_conf/x.tif"]]}}
        if body["sql"].startswith("SELECT SUM"):
            return {"data": [{"sum": self.total}]}
        return {"data": self.rows}


def _api_rows():
    rows = _rows()
    for r, c in zip(rows, ["nominal", "high", "highest", "nominal"]):
        r["area__ha"] = 0.0123
        r["wur_radd_alerts__confidence"] = c
    return rows


def test_load_reference_queries_api_and_checks_total():
    api = FakeAPI(_api_rows(), 4 * 0.0123)
    out = sc.load_reference("RADD", (-60.1, -3.1, -59.9, -2.9), ["2025-04-30", "2025-04-01"], api_key="k",
                            origin="example.org", http=api)
    assert len(out["features"]) == 2
    url, body, headers = api.calls[1]
    assert url == "https://data-api.globalforestwatch.org/dataset/wur_radd_alerts/latest/query/json"
    assert headers == {"x-api-key": "k", "Origin": "example.org"}
    assert "wur_radd_alerts__date >= '2025-04-01' AND wur_radd_alerts__date <= '2025-04-30'" in body["sql"]
    assert body["geometry"]["coordinates"][0][0] == [-60.1, -3.1]
    hi = sc.load_reference("RADD", (-60.1, -3.1, -59.9, -2.9), ["2025-04-01", "2025-04-30"], api_key="k",
                           min_confidence="high", http=FakeAPI(_api_rows(), 4 * 0.0123))
    assert [f["properties"]["date"] for f in hi["features"]] == ["2025-04-02"]  # nominal pixels dropped


def test_load_reference_refuses_truncated_answer_and_missing_key():
    with pytest.raises(RuntimeError, match="truncated"):
        sc.load_reference("RADD", (-60.1, -3.1, -59.9, -2.9), ["2025-04-01", "2025-04-30"], api_key="k",
                          http=FakeAPI(_api_rows(), 10.0))
    with pytest.raises(RuntimeError, match="API key"):
        sc.load_reference("RADD", (-60.1, -3.1, -59.9, -2.9), ["2025-04-01", "2025-04-30"], http=FakeAPI([], 0))
    with pytest.raises(ValueError):  # dates go into SQL, so anything not YYYY-MM-DD is rejected
        sc.load_reference("RADD", (0, 0, 1, 1), ["2025-04-01' OR '1'='1"], api_key="k", http=FakeAPI([], 0))
    with pytest.raises(ValueError):
        sc.load_reference("NOPE", (0, 0, 1, 1), ["2025-04-01"], api_key="k", http=FakeAPI([], 0))


def test_load_reference_rows_file(tmp_path):
    p = tmp_path / "rows.json"
    p.write_text(json.dumps({"data": _api_rows()}))
    out = sc.load_reference("RADD", (0, 0, 1, 1), ["2025-04-01", "2025-04-10"], rows_file=str(p), pixel_deg=1e-4)
    assert [f["properties"]["date"] for f in out["features"]] == ["2025-04-02"]  # 04-20 is outside the window


# ---- holdout -----------------------------------------------------------------------------------------------

def test_make_holdout_refuses_without_split():
    with pytest.raises(ValueError, match="refusing"):
        sc.make_holdout(None, None)
    with pytest.raises(ValueError):
        sc.make_holdout((0, 0, 1, 1), ["2025-04-01"])
    with pytest.raises(ValueError):
        sc.make_holdout((1, 0, 0, 1), None)
    assert sc.make_holdout(None, ["2025-04-02", "2025-04-01"]) == {"dates": ["2025-04-01", "2025-04-02"]}


def test_in_holdout():
    f = feat(box(0.1, 0.1, 0.2, 0.2), date="2025-04-01")
    assert sc.in_holdout(f, {"bbox": (0, 0, 1, 1)}) and not sc.in_holdout(f, {"bbox": (1, 0, 2, 1)})
    assert sc.in_holdout(f, {"dates": ["2025-04-01"]}) and not sc.in_holdout(f, {"dates": ["2025-05-01"]})


def test_score_main_refuses_without_split(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["score.py", "--source", "RADD", "--tolerance-days", "10",
                                      "--overlap-threshold", "0", "--tile", "T", "--bbox", "0", "0", "1", "1"])
    with pytest.raises(SystemExit):
        sc.main()


# ---- matching ----------------------------------------------------------------------------------------------

def _case():
    det = fc(feat(box(0, 0, 0.01, 0.01), id=1, date="2025-04-01", first_hh_date="2025-03-01",
                  first_hv_date="2025-04-01"),
             feat(box(1, 1, 1.01, 1.01), id=2, date="2025-04-01", first_hh_date="2025-04-01", first_hv_date=None))
    ref = fc(feat(box(0.005, 0, 0.015, 0.01), source="RADD", date="2025-03-25"),  # covers half of det 1
             feat(box(1, 1, 1.01, 1.01), source="RADD", date="2025-01-01"),  # same place as det 2, too early
             feat(box(5, 5, 5.01, 5.01), source="RADD", date="2025-04-01"))  # nothing detected there
    return det, ref


def test_match_any_overlap():
    det, ref = _case()
    m = sc.match_detections(det, ref, tolerance_days=10, overlap_threshold=0.0)
    assert [r["agrees"] for r in m["detections"]] == [True, False]
    assert [r["agrees"] for r in m["reference"]] == [True, False, False]
    assert m["detections"][0]["cover"] == pytest.approx(0.5, abs=1e-3)
    assert m["precision_like"] == 0.5 and m["recall_like"] == pytest.approx(1 / 3)
    assert m["f1_like"] == pytest.approx(0.4)
    m2 = sc.match_detections(det, ref, tolerance_days=100, overlap_threshold=0.0)  # now det 2 / ref 2 are compatible
    assert [r["agrees"] for r in m2["detections"]] == [True, True]


def test_match_overlap_threshold_and_edges():
    det, ref = _case()
    m = sc.match_detections(det, ref, tolerance_days=10, overlap_threshold=0.6)
    assert m["precision_like"] == 0.0 and m["recall_like"] == 0.0 and m["f1_like"] == 0.0
    touch = fc(feat(box(0.01, 0, 0.02, 0.01), source="RADD", date="2025-04-01"))  # shares only an edge
    m2 = sc.match_detections(fc(det["features"][0]), touch, 10, 0.0)
    assert m2["precision_like"] == 0.0
    empty = sc.match_detections(fc(), fc(), 10, 0.0)
    assert empty["precision_like"] is None and empty["recall_like"] is None and empty["f1_like"] is None
    with pytest.raises(ValueError):
        sc.match_detections(det, ref, 10, 1.5)


def test_min_ref_ha_limits_recall_only():
    det, ref = _case()
    tiny = feat(box(0.0, 0.0, 0.0001, 0.0001), source="RADD", date="2025-04-01")  # ~0.012 ha, inside det 1
    ref["features"].append(tiny)
    m = sc.match_detections(det, ref, 10, 0.0, min_ref_ha=1.0)  # the 0.01 deg refs are ~120 ha
    assert m["n_reference_all"] == 4 and m["n_reference"] == 3
    assert m["recall_like"] == pytest.approx(1 / 3)  # tiny agreeing patch not counted
    assert m["precision_like"] == 0.5  # precision still sees every reference patch
    assert sc.match_detections(det, ref, 10, 0.0)["recall_like"] == pytest.approx(2 / 4)


def test_compute_metrics_contract_and_keeps_hand_labeled(tmp_path):
    det, ref = _case()
    m = sc.match_detections(det, ref, 10, 0.0)
    out = str(tmp_path / "metrics.json")
    got = sc.compute_metrics(m, "T01", ["2025-04-01"], "RADD", out)
    assert set(got) == {"agreement", "hand_labeled", "n_detections", "n_reference", "tile", "dates",
                        "reference_source", "notes"}
    assert got["agreement"] == {"precision_like": 0.5, "recall_like": pytest.approx(1 / 3),
                                "f1_like": pytest.approx(0.4), "level": "patch", "split": "holdout"}
    assert got["hand_labeled"] is None and got["n_detections"] == 2 and got["n_reference"] == 3
    assert "accuracy" not in json.dumps(got["agreement"])
    hl = {"n_sample": 15, "precision": 0.8, "n_unsure": 1}
    saved = json.load(open(out))
    saved["hand_labeled"] = hl
    json.dump(saved, open(out, "w"))
    assert sc.compute_metrics(m, "T01", ["2025-04-01"], "RADD", out)["hand_labeled"] == hl


def test_lag_table_skips_missing():
    det, ref = _case()
    m = sc.match_detections(det, ref, 100, 0.0)
    rows = sc.lag_table(det, m)
    assert rows == [{"id": 1, "date": "2025-04-01", "first_hh_date": "2025-03-01", "first_hv_date": "2025-04-01",
                     "alert_date": "2025-03-25", "hh_lead_days": 24, "hv_lead_days": -7}]  # det 2 has no HV date
