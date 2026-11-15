import numpy as np
import pytest

import cloud_blindness as cb


def item(i, date, tile, updated):
    return {"id": i, "properties": {"datetime": f"{date}T14:00:00Z", "grid:code": tile, "updated": updated}}


def test_dedupe_keeps_latest_per_tile_and_groups_by_date():
    its = [item("a", "2026-07-01", "MGRS-21LYL", "1"), item("b", "2026-07-01", "MGRS-21LYL", "2"),
           item("c", "2026-07-01", "MGRS-21MYM", "1"), item("d", "2026-07-04", "MGRS-21LYL", "1")]
    out = cb.dedupe(its)
    assert sorted(out) == ["2026-07-01", "2026-07-04"]
    assert sorted(i["id"] for i in out["2026-07-01"]) == ["b", "c"]


def test_mosaic_first_nonzero_wins():
    a = np.array([[0, 4], [9, 0]], np.uint8)
    b = np.array([[5, 8], [4, 0]], np.uint8)
    assert cb.mosaic([a, b]).tolist() == [[5, 4], [9, 0]]


def test_fractions_classes():
    scl = np.array([4, 5, 6, 3, 8, 9, 10, 0, 7, 2], np.uint8)
    f = cb.fractions(scl, np.ones(10, bool))
    assert f["clear_fraction"] == pytest.approx(0.3)
    assert f["cloud_shadow_cirrus_fraction"] == pytest.approx(0.4)
    assert f["nodata_fraction"] == pytest.approx(0.1)
    assert f["other_fraction"] == pytest.approx(0.2)


def test_longest_gap_between_good_views():
    g = cb.longest_gap(["2026-07-01", "2026-07-11", "2026-08-10"], "2026-06-26", "2026-10-12")
    assert g["longest_gap_days_between_good_views"] == 30 and g["between"] == ("2026-07-11", "2026-08-10")
    assert g["longest_gap_days_incl_window_ends"] == 63  # 08-10 -> 10-12
    assert cb.longest_gap(["2026-07-01"])["longest_gap_days_between_good_views"] is None


def test_summarise_threshold_inclusive():
    rows = [{"date": "2026-07-01", "aoi": {"clear_fraction": 0.80}}, {"date": "2026-07-04", "aoi": {"clear_fraction": 0.79}},
            {"date": "2026-07-09", "aoi": {"clear_fraction": 1.0}}]
    s = cb.summarise(rows, "aoi")
    assert s["n_ge_80pct_clear"] == 2 and s["median_clear_fraction"] == 0.80
