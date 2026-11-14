"""Hansen GFC loss 2021-2025 as a transparent RGBA WebP on exactly the grid of a web layer COG.

Reads:  Hansen GFC v1.13 lossyear tile (public HTTPS, same tile and window logic as hansen_classes.py) and --grid, a COG
        in web/data/<id>/ (EPSG:3857); only its CRS, transform and size are used.
Writes: --out WebP (lossless RGBA, same width/height and bounds as --grid; transparent where there is no loss in the
        chosen years) and a sidecar JSON with the grid, the year -> colour legend and the source.
lossyear encoding (Hansen et al. 2013; band notes in pipeline/load/forest_mask.py): 0 = no loss, 1..25 = loss in 2001..2025.
Resampling is nearest (a categorical year), so each output pixel is exactly one Hansen pixel's year.
"""
from __future__ import annotations

import argparse
import json

import numpy as np
import rasterio
from PIL import Image
from rasterio.warp import Resampling, reproject, transform_bounds
from rasterio.windows import from_bounds

from build_masks import HANSEN, hansen_tile

# One colour per loss year, light to dark = older to newer. Alpha 255 where there is loss, 0 elsewhere.
PALETTE = {2021: (253, 224, 71), 2022: (251, 146, 60), 2023: (239, 68, 68), 2024: (185, 28, 28), 2025: (91, 14, 74)}


def colourise(years_since_2000: np.ndarray, palette: dict[int, tuple[int, int, int]] = PALETTE) -> np.ndarray:
    """(h, w) lossyear codes -> (h, w, 4) uint8 RGBA; only the years in `palette` are opaque."""
    out = np.zeros((*years_since_2000.shape, 4), np.uint8)
    for year, rgb in palette.items():
        m = years_since_2000 == year - 2000
        out[m, :3] = rgb
        out[m, 3] = 255
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--grid", required=True, help="a web layer COG (EPSG:3857) whose grid the output must match")
    p.add_argument("--out", required=True)
    a = p.parse_args()
    with rasterio.open(a.grid) as g:
        crs, transform, h, w, bounds = g.crs, g.transform, g.height, g.width, g.bounds
    west, south, east, north = transform_bounds(crs, "EPSG:4326", *bounds)
    tile = hansen_tile((west, south, east, north))
    with rasterio.open(HANSEN.format(layer="lossyear", tile=tile)) as src:
        win = from_bounds(west - 0.01, south - 0.01, east + 0.01, north + 0.01, src.transform).round_offsets().round_lengths()
        ly = src.read(1, window=win)
        src_transform, src_crs = src.window_transform(win), src.crs
    dst = np.zeros((h, w), np.uint8)
    reproject(ly, dst, src_transform=src_transform, src_crs=src_crs, dst_transform=transform, dst_crs=crs,
              resampling=Resampling.nearest)
    rgba = colourise(dst)
    Image.fromarray(rgba, "RGBA").save(a.out, format="WEBP", lossless=True, exact=True)
    sidecar = a.out.rsplit(".", 1)[0] + ".json"
    counts = {str(y): int((dst == y - 2000).sum()) for y in PALETTE}
    with open(sidecar, "w", encoding="utf-8") as f:
        json.dump({"source": "Hansen GFC v1.13 lossyear (Hansen et al. 2013, Science 342:850-853)", "tile": tile,
                   "years": {str(y): "#%02x%02x%02x" % rgb for y, rgb in PALETTE.items()}, "pixels_per_year": counts,
                   "grid": {"crs": str(crs), "width": w, "height": h, "bounds": list(bounds), "transform": list(transform)[:6]},
                   "grid_from": a.grid, "resampling": "nearest", "transparent": "no loss in 2021-2025"}, f, indent=1)
    print(f"{w}x{h} RGBA WebP -> {a.out}; loss pixels per year {counts}")


if __name__ == "__main__":
    main()
