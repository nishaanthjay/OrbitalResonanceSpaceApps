import numpy as np

import frame


def test_block_fraction_u8():
    a = np.zeros((10, 10), bool)
    a[:5, :5] = True
    assert frame.block_fraction_u8(a, 5).tolist() == [[1.0, 0.0], [0.0, 0.0]]


def test_with_nonforest():
    m = frame.with_nonforest({"tp": 6, "fp": 2, "fn": 1, "tn": 3})
    assert m["nonforest_precision"] == 3 / 4 and m["nonforest_recall"] == 3 / 5
    assert m["confusion_rows_ref_cols_pred"]["ref_forest"] == [6, 1]


def test_first_switch_index():
    f = np.array([[1, 1, 0, 1], [1, 0, 1, 1], [1, 0, 0, 1]], bool)  # (passes, blocks)
    assert frame.first_switch_index(f).tolist() == [-1, 1, 2, -1]
    g = np.array([[1], [0], [1], [0], [0]], bool)  # went non-forest, back, then stayed non-forest from pass 3
    assert frame.first_switch_index(g).tolist() == [3]


def test_box60():
    m = frame.box60_mask(np.array([62410.0, 200000.0]), np.array([9091730.0]))
    assert m.tolist() == [[True, False]]
