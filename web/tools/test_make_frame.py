import numpy as np
from rasterio.transform import from_origin

import make_frame


def test_downsample_and_switch_colours():
    a = np.arange(16).reshape(4, 4)
    assert make_frame.downsample(a, 2).tolist() == [[5, 7], [13, 15]]
    img = make_frame.switch_rgba(np.array([[0, 1, 9]]), make_frame.SWITCH_COLOURS)
    assert img[0, 0, 3] == 0 and img[0, 1].tolist() == [0x44, 0x01, 0x54, 255] and img[0, 2, 3] == 255


def test_patches_categories_first_switch_series_and_geojson():
    lost = np.zeros((4, 4), bool)
    lost[0, 0] = lost[1, 1] = True  # diagonal -> one 8-connected patch
    lost[3, 3] = True
    hv = np.full((9, 4, 4), -10.0)
    hv[:, 1, 1] = -20.0
    first = np.full((4, 4), -1)
    first[0, 0], first[1, 1], first[3, 3] = 5, 3, 7
    alert = np.zeros((4, 4), bool)
    alert[1, 1] = True
    dates = [f"d{i}" for i in range(9)]
    lab, props = make_frame.patch_table(lost, hv, first, alert, dates, 1.0)
    assert [p["area_ha"] for p in props] == [2.0, 1.0]
    assert props[0]["first_switch_date"] == "d3" and props[0]["category"] == "alert_supported"
    assert props[1]["first_switch_date"] == "d7" and props[1]["category"] == "radar_only_unconfirmed"
    assert props[0]["hv_series_db"][0] == -15.0
    gj = make_frame.geojson(lab, props, from_origin(500000, 9100000, 100, 100), "EPSG:32722")
    assert len(gj["features"]) == 2
    assert len(make_frame.geojson(lab, props, from_origin(500000, 9100000, 100, 100), "EPSG:32722", 1.5)["features"]) == 1
