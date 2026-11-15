import numpy as np
from rasterio.transform import Affine

import optical_layers as ol


def test_nearest_date():
    av = ["2026-06-29", "2026-07-04", "2026-07-09"]
    assert ol.nearest_date("2026-07-08", av) == ("2026-07-09", 1)
    assert ol.nearest_date("2026-07-06", av) == ("2026-07-04", -2)  # nearer than 07-09 (3 d)
    assert ol.nearest_date("2026-07-06", ["2026-07-04", "2026-07-08"]) == ("2026-07-04", -2)  # tie -> earlier
    assert ol.nearest_date("2026-08-13", av) is None  # nothing within 6 days


def test_stretch_fixed_and_monotone():
    s = ol.stretch(np.array([-0.1, 0.0, 0.075, 0.30, 0.9]))
    assert s[0] == 0 and s[1] == 0 and s[3] == 255 and s[4] == 255 and s[1] < s[2] < s[3]


def test_box_mask_centre_inside_far_outside():
    # a 2 x 2 px grid in EPSG:3857 around the box centre (lon -54.699, lat -8.1995) and one 5 deg away
    from pyproj import Transformer
    cx, cy = Transformer.from_crs(4326, 3857, always_xy=True).transform(-54.699, -8.1995)
    tf = Affine(100, 0, cx - 100, 0, -100, cy + 100)
    assert ol.box_mask(tf, (2, 2)).all()
    fx, fy = Transformer.from_crs(4326, 3857, always_xy=True).transform(-50.0, -3.0)
    assert not ol.box_mask(Affine(100, 0, fx, 0, -100, fy), (2, 2)).any()
