import numpy as np

import first_switch as fsw
import scale


def test_first_switch_after_0720_and_stays():
    F, N = True, False
    forest = np.array([[F, F, F, F, F, F, F, N, N],   # switch 09-30 -> 7
                       [F, F, F, N, F, N, N, N, N],   # flips back on 08-25, final run from 09-06 -> 5
                       [F, N, N, N, N, N, N, N, N],   # non-forest before 07-20 too: first after 07-20 is 08-13 -> 3
                       [F, F, F, F, F, F, F, F, N]]).T[:, :, None]  # only 10-12 -> 8 (not lost)
    assert fsw.first_switch(forest)[:, 0].tolist() == [7, 5, 3, 8]
    lost = scale.lost_rule(forest)[:, 0].tolist()
    assert lost == [True, True, False, False]


def test_palette_and_hex():
    assert len(fsw.PALETTE) == 5 and fsw.hex_rgb("#fde047") == (253, 224, 71)
