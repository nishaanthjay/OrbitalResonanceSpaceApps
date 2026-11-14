"""Tiny in-memory test for export_hansen_loss.colourise (hand-made lossyear codes, no network)."""
import numpy as np

from export_hansen_loss import PALETTE, colourise


def test_only_2021_to_2025_are_opaque():
    ly = np.array([[0, 20, 21], [22, 25, 5]])  # 0 = no loss; 20 = loss 2020; 21..25 = 2021..2025; 5 = loss 2005
    rgba = colourise(ly)
    assert rgba.shape == (2, 3, 4)
    assert rgba[..., 3].tolist() == [[0, 0, 255], [255, 255, 0]]
    assert tuple(rgba[0, 2, :3]) == PALETTE[2021] and tuple(rgba[1, 1, :3]) == PALETTE[2025]
