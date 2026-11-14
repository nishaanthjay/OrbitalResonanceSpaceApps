"""Share of GLAD alert pixels that fall on land Hansen GFC already marks as cleared before 2026.

Reads:  alerts_glad_l.json / alerts_glad_s2.json (fetch_alerts.py rows) and the Hansen GFC v1.13 lossyear tile
        (same public tile and window as hansen_classes.py).
Prints: per source, for alert pixels dated in a period, how many have Hansen lossyear in 1..25 (loss 2001-2025, i.e.
        cleared before 2026) at the pixel centre, per split half (north = tune, south = holdout, as clearing_check.py)
        and for the whole window. Periods: all of 2026, and the scored period (AFTER, UNTIL].
A reading aid, not a score: it explains why alerts may not be on forest our mask allows detections in.
"""
from __future__ import annotations

import argparse
import json
import os

import numpy as np
import rasterio
from rasterio.transform import rowcol
from rasterio.windows import from_bounds

from build_masks import HANSEN, hansen_tile
from clearing_check import SOURCES, halves


def prior_loss_share(lossyear_at_pixels: np.ndarray) -> tuple[int, int]:
    """(pixels with Hansen loss 2001-2025, all pixels): lossyear 1..25 means cleared before 2026."""
    ly = np.asarray(lossyear_at_pixels)
    return int(((ly >= 1) & (ly <= 25)).sum()), int(ly.size)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--alert-dir", required=True)
    p.add_argument("--bbox", type=float, nargs=4, metavar=("W", "S", "E", "N"), required=True)
    p.add_argument("--after", required=True, help="scored period starts strictly after this date")
    p.add_argument("--until", required=True, help="... and ends on or before this one")
    p.add_argument("--out", help="optional JSON with the counts")
    a = p.parse_args()
    w, s, e, n = a.bbox
    tile = hansen_tile(a.bbox)
    with rasterio.open(HANSEN.format(layer="lossyear", tile=tile)) as src:
        win = from_bounds(w - 0.01, s - 0.01, e + 0.01, n + 0.01, src.transform).round_offsets().round_lengths()
        ly = src.read(1, window=win)
        transform = src.window_transform(win)
    periods = {"2026 (all)": ("2025-12-31", "2026-12-31"), f"scored period ({a.after}, {a.until}]": (a.after, a.until)}
    res = {"tile": tile, "bbox": a.bbox, "results": {}}
    for src_name, (fname, dataset, _deg) in SOURCES.items():
        field = f"{dataset}__date"
        with open(os.path.join(a.alert_dir, fname), encoding="utf-8") as f:
            rows = [r for r in json.load(f) if r.get(field)]
        lon = np.array([r["longitude"] for r in rows])
        lat = np.array([r["latitude"] for r in rows])
        date = np.array([r[field] for r in rows])
        inside = (lon >= w) & (lon <= e) & (lat >= s) & (lat <= n)
        rr, cc = rowcol(transform, lon, lat)
        rr, cc = np.clip(np.asarray(rr), 0, ly.shape[0] - 1), np.clip(np.asarray(cc), 0, ly.shape[1] - 1)
        at = ly[rr, cc]
        for pname, (after, until) in periods.items():
            in_period = inside & (date > after) & (date <= until)
            for half, (hw, hs, he, hn) in {**halves(a.bbox), "whole window": a.bbox}.items():
                in_half = in_period & (lon >= hw) & (lon <= he) & (lat >= hs) & (lat <= hn)
                k, tot = prior_loss_share(at[in_half])
                res["results"][f"{src_name} | {pname} | {half}"] = {"on_prior_loss": k, "alert_pixels": tot,
                                                                      "share": round(k / tot, 4) if tot else None}
                print(f"{src_name:8s} {pname:36s} {half:16s} alert pixels {tot:8d}  on Hansen loss 2001-2025 {k:8d}  "
                      f"{k / tot:.1%}" if tot else f"{src_name:8s} {pname:36s} {half:16s} no alert pixels")
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(res, f, indent=1)


if __name__ == "__main__":
    main()
