"""Tiny in-memory test for alert_prior_clearing.prior_loss_share (hand-made values, no network)."""
import numpy as np

from alert_prior_clearing import prior_loss_share


def test_prior_loss_share_counts_only_loss_2001_to_2025():
    k, n = prior_loss_share(np.array([0, 0, 3, 25, 25, 12]))  # 0 = no loss
    assert (k, n) == (4, 6)
    assert prior_loss_share(np.array([], dtype=int)) == (0, 0)
    assert prior_loss_share(np.array([0, 0])) == (0, 2)
