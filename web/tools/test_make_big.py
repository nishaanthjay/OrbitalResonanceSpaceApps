import numpy as np
from rasterio.transform import from_origin

import make_big


def test_classes_and_colours():
    hv = np.array([[-11.0, -11.250146865844727, -12.0, np.nan]])
    c = make_big.classes(hv, -11.250146865844727)
    assert c.tolist() == [[1, 1, 2, 0]]
    img = make_big.rgba(c)
    assert img[0, 0].tolist() == [0x2F, 0x6B, 0x4F, 255]
    assert img[0, 2].tolist() == [0xB4, 0x40, 0x1C, 255]
    assert img[0, 3, 3] == 0


def test_patches_merge_8_connected_and_series_linear_mean():
    lost = np.zeros((4, 4), bool)
    lost[0, 0] = lost[1, 1] = True  # diagonal neighbours -> one patch
    lost[3, 3] = True
    hv = np.full((9, 4, 4), -10.0)
    hv[:, 1, 1] = -20.0
    gj = make_big.patches(lost, hv, from_origin(500000, 9100000, 100, 100), "EPSG:32722", 1.0, np.zeros((4, 4), bool))
    f = gj["features"]
    assert len(f) == 2 and f[0]["properties"]["area_ha"] == 2.0
    expect = 10 * np.log10((0.1 + 0.01) / 2)
    assert abs(f[0]["properties"]["hv_series_db"][0] - round(expect, 2)) < 1e-9


def test_first_flagged():
    F, N = True, False
    forest = np.array([[F, F, F, F, F, F, F, N, N],
                       [F, F, F, N, F, N, N, N, N],
                       [F, F, F, N, N, N, N, N, N],
                       [F, F, F, F, F, F, F, F, N]]).T[:, :, None]
    assert make_big.first_flagged(forest)[:, 0].tolist() == [7, 5, 3, 8]
