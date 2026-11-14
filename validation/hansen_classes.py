"""Hansen GFC class of each detection (reading aid for hand labels; changes no threshold).

Reads:  final/detections.geojson (EPSG:4326 polygons) and the Hansen GFC v1.13 treecover2000 / lossyear tile.
Prints: per split half, the Hansen class of the detections: by majority class per detection and by pixel area.
        Classes: "loss YYYY" (lossyear 1..25), "intact" (treecover2000 >= 30 % and no loss 2001-2025),
        "non-forest 2000" (treecover2000 < 30 %, no loss). A pixel counts if its centre is inside the polygon.
Detections are assigned to a half by their representative point, as diagnose.py.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter

import numpy as np
import rasterio
from rasterio.features import geometry_mask
from rasterio.windows import from_bounds
from shapely.geometry import shape

from build_masks import HANSEN, hansen_tile
from clearing_check import halves


def classes(tc: np.ndarray, ly: np.ndarray, tc_min: float) -> np.ndarray:
    loss = np.char.add("loss ", (2000 + ly.astype(int)).astype(str))
    return np.where(ly > 0, loss, np.where(tc >= tc_min, "intact", "non-forest 2000"))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--detections", required=True)
    p.add_argument("--bbox", type=float, nargs=4, metavar=("W", "S", "E", "N"), required=True)
    p.add_argument("--treecover-min", type=float, default=30.0)
    p.add_argument("--out", help="optional JSON with per-detection classes and the summaries")
    a = p.parse_args()
    with open(a.detections, encoding="utf-8") as f:
        det = json.load(f)["features"]
    tile = hansen_tile(a.bbox)
    w, s, e, n = a.bbox
    layers = {}
    for layer in ("treecover2000", "lossyear"):
        with rasterio.open(HANSEN.format(layer=layer, tile=tile)) as src:
            win = from_bounds(w - 0.01, s - 0.01, e + 0.01, n + 0.01, src.transform).round_offsets().round_lengths()
            layers[layer] = src.read(1, window=win)
            transform = src.window_transform(win)
    tc, ly = layers["treecover2000"], layers["lossyear"]
    cls = classes(tc, ly, a.treecover_min)
    res = {"tile": tile, "halves": {}, "detections": []}
    for half, (hw, hs, he, hn) in halves(a.bbox).items():
        maj, area = Counter(), Counter()
        sel = []
        for f in det:
            g = shape(f["geometry"])
            rp = g.representative_point()
            if not (hw <= rp.x <= he and hs <= rp.y <= hn):
                continue
            inside = ~geometry_mask([g], out_shape=cls.shape, transform=transform, all_touched=False)
            c = Counter(cls[inside].tolist())
            top = c.most_common(1)[0][0] if c else "no pixel"
            maj[top] += 1
            area.update(c)
            sel.append(f)
            res["detections"].append({"id": f["properties"]["id"], "half": half, "majority": top,
                                      "pixels": dict(c), "any_loss": any(k.startswith("loss") for k in c)})
        npx = sum(area.values())
        any_loss = sum(1 for d in res["detections"] if d["half"] == half and d["any_loss"])
        res["halves"][half] = {"n": len(sel), "majority": dict(maj.most_common()),
                               "pixel_share": {k: round(v / npx, 4) for k, v in area.most_common()} if npx else {},
                               "n_with_any_loss_pixel": any_loss}
        print(f"{half}: n {len(sel)}, Hansen pixels {npx}, detections with any loss pixel {any_loss}")
        print("  by majority class: " + ", ".join(f"{k} {v} ({v / len(sel):.1%})" for k, v in maj.most_common()))
        print("  by pixel area:     " + ", ".join(f"{k} {v / npx:.1%}" for k, v in area.most_common()))
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(res, f, indent=1)


if __name__ == "__main__":
    main()
