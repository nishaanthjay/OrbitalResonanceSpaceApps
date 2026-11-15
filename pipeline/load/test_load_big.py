import numpy as np
import pytest

import load
from forest_mask import native_grid
from load_big import block_centres, block_mean_linear, grid_index


def test_block_mean_linear_skips_nan_and_floor():
    p = np.full((10, 10), 2.0)
    p[0, 0] = np.nan
    p[0, 1] = 1e-13  # below the validity floor
    p[5:, 5:] = np.nan  # one all-invalid block
    out = block_mean_linear(p, 5)
    assert out.shape == (2, 2)
    assert out[0, 0] == pytest.approx(2.0) and np.isnan(out[1, 1])


def test_block_mean_linear_is_linear_power_mean_and_trims():
    p = np.zeros((6, 7))
    p[:5, :5] = np.r_[[1.0] * 12 + [3.0] * 13].reshape(5, 5)
    out = block_mean_linear(p, 5)
    assert out.shape == (1, 1)
    assert out[0, 0] == pytest.approx((12 * 1 + 13 * 3) / 25)


def test_grid_index_exact_and_refuses_off_grid():
    y = 9380150.0 - 20.0 * np.arange(16344)
    s = grid_index(y, 9121770.0, 3000)
    assert y[s.start] == 9121770.0 and s.stop - s.start == 3000
    with pytest.raises(ValueError):
        grid_index(y, 9121775.0, 10)  # between centres (a relative tolerance would wrongly accept this)
    with pytest.raises(ValueError):
        grid_index(y, y[-5], 10)  # runs off the grid


def test_block_centres_and_native_grid_round_trip():
    x = 62370.0 + 20.0 * np.arange(3000)
    xc = block_centres(x, 5)
    assert xc[0] == 62410.0 and np.allclose(np.diff(xc), 100.0)
    assert np.allclose(native_grid(xc, 5), x)
    assert load.MIN_VALID_POWER == 1e-6
