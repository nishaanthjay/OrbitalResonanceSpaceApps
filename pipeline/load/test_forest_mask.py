import numpy as np
import rasterio

from forest_mask import _retry, build_grid, forest_from_layers, native_grid, hansen_tile


def test_frame_native_grid():
    xc = 32410 + 100 * np.arange(3026)
    x = native_grid(xc, 5)
    assert x.size == 15130 and np.allclose(x[2::5], xc) and np.allclose(np.diff(x), 20)


def test_rule_and_tile():
    tc, ly, dm = np.array([30, 29, 80, 80]), np.array([0, 0, 3, 0]), np.array([1, 1, 1, 2])
    assert forest_from_layers(tc, ly, dm, 30).tolist() == [1, 0, 0, 0]
    assert hansen_tile(-54, -7) == "00N_060W"


def test_retry():
    n = []
    def f():
        n.append(1)
        if len(n) < 2:
            raise OSError
        return 7
    import time; time.sleep = lambda s: None
    assert _retry(f) == 7
