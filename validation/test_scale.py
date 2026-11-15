import datetime as dt

import numpy as np
import pytest

import scale


def test_frozen_T_is_fnf_value():
    assert scale.frozen_T() == pytest.approx(-11.250146865844727)


def test_lost_rule_exact_definition():
    F, N = True, False
    cases = {  # 9 passes -> expected
        (F, F, F, F, F, F, F, N, N): True,
        (F, N, F, F, F, F, F, N, N): True,   # 2 of first 3
        (N, N, F, F, F, F, F, N, N): False,  # only 1 of first 3
        (F, F, F, F, F, F, F, F, N): False,  # forest on 09-30
        (F, F, F, F, F, F, F, N, F): False,  # forest on 10-12
        (F, F, F, N, N, N, N, N, N): True,   # middle passes do not matter
    }
    arr = np.array(list(cases)).T
    assert scale.lost_rule(arr).tolist() == list(cases.values())
    with pytest.raises(ValueError):
        scale.lost_rule(arr[:8])


def test_block_fraction():
    m = np.zeros((10, 10))
    m[:5, :5] = 1
    m[5:, :5][:3] = 1  # 15 of 25
    assert scale.block_fraction(m, 5).tolist() == [[1.0, 0.0], [0.6, 0.0]]


def test_block_index_footprints():
    xc = np.array([50.0, 150.0, 250.0])
    yc = np.array([950.0, 850.0])
    r, c = scale.block_index(np.array([0.0, 99.9, 100.0, 299.9, 300.0, 120.0]),
                             np.array([1000.0, 900.1, 900.0, 800.1, 950.0, 799.0]), xc, yc)
    assert c.tolist() == [0, 0, 1, 2, -1, -1]
    assert r.tolist() == [0, 0, 1, 1, -1, -1]


def test_alert_blocks_date_window_inclusive():
    d = np.array(["2026-07-19", "2026-07-20", "2026-10-12", "2026-10-13"], dtype="datetime64[D]")
    r, c = np.array([0, 0, 1, 1]), np.array([0, 1, 0, 1])
    m = scale.alert_blocks(d, r, c, (2, 2), dt.date(2026, 7, 20), dt.date(2026, 10, 12))
    assert m.tolist() == [[False, True], [True, False]]


def test_agreement_counts_inside_area_only():
    pred = np.array([True, True, False, False, True])
    rp = np.array([True, False, False, True, True])
    rr = np.array([True, False, True, True, True])
    area = np.array([True, True, True, True, False])
    a = scale.agreement(pred, rp, rr, area)
    assert (a["n_blocks"], a["n_with_alert"], a["n_reference"], a["n_reference_hit"]) == (2, 1, 3, 1)
    assert a["precision_like"] == 0.5 and a["recall_like"] == pytest.approx(1 / 3)
    none = scale.agreement(np.zeros(5, bool), rp, rr, area)
    assert none["precision_like"] is None
