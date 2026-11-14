import numpy as np
from fnf import metrics, otsu_threshold, youden_threshold


def _data():
    r = np.random.default_rng(0)
    ref = np.arange(2000) % 2 == 0
    return np.where(ref, r.normal(-8, 1, 2000), r.normal(-14, 1, 2000)), ref


def test_youden_and_otsu_split_two_clusters():
    x, ref = _data()
    T, J = youden_threshold(x, ref)
    assert -12.5 < T < -9.5 and J > 0.95
    assert -12.5 < otsu_threshold(x) < -9.5


def test_metrics_known_confusion():
    ref = np.array([1, 1, 1, 0, 0, 0, 0, 0], bool)
    pred = np.array([1, 1, 0, 1, 0, 0, 0, 0], bool)
    m = metrics(pred, ref)
    assert (m["tp"], m["fp"], m["fn"], m["tn"]) == (2, 1, 1, 4)
    assert abs(m["oa"] - 0.75) < 1e-9 and abs(m["all_forest_baseline"] - 3 / 8) < 1e-9
    assert abs(m["kappa"] - 0.4666667) < 1e-6  # (0.75-0.53125)/(1-0.53125)
