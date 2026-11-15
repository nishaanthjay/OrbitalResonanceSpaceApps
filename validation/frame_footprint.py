"""Footprint of NISAR track 2 frame 174 on the 9 pre-registered dates, from granule metadata only (no pixels).

  python validation/frame_footprint.py --out validation/frame_footprint.json
Reads each granule's boundingPolygon (asf_search), projects to EPSG:32722, intersects the 9 polygons, and snaps the
intersection to the 100 m block grid of the big stack (freqA pixel centres x 62370.., y 9121770.. step 20 m; blocks of 5).
Writes the polygon intersection, the block-grid window (first block centre, nx, ny) and the shrunk rectangle used.
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline" / "load"))
import numpy as np
from pyproj import Transformer
from shapely.geometry import shape, Polygon, box
from shapely.ops import transform as shp_transform
import load

DATES = ["2026-06-26", "2026-07-08", "2026-07-20", "2026-08-13", "2026-08-25", "2026-09-06", "2026-09-18", "2026-09-30", "2026-10-12"]
KEY = load.GroupKey(2, 174, "ASCENDING", "20+5")
X0, Y0 = 62370.0, 9121770.0  # first freqA pixel centre of the big stack; blocks are 5 px = 100 m, block centres at X0 + 40 + 100 k


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default="validation/frame_footprint.json")
    a = ap.parse_args()
    grans = load.search_granules((-56.5, -9.5, -53.0, -6.5), "2026-06-20", "2026-10-20", KEY)
    got = [g.properties["startTime"][:10] for g in grans]
    if got != DATES:
        raise SystemExit(f"dates {got} != {DATES}")
    tf = Transformer.from_crs(4326, 32722, always_xy=True).transform
    polys, rows = [], []
    for g in grans:
        p = g.properties
        poly = shp_transform(tf, shape(g.geometry))
        polys.append(poly)
        rows.append({"date": p["startTime"][:10], "scene": p["sceneName"], "area_km2": poly.area / 1e6,
                     "bounds_utm": [round(v) for v in poly.bounds]})
    inter = polys[0]
    for q in polys[1:]:
        inter = inter.intersection(q)
    out = {"dates": got, "per_date": rows, "intersection_area_km2": inter.area / 1e6, "intersection_bounds_utm": list(inter.bounds),
           "intersection_wkt": inter.wkt}
    Path(a.out).write_text(json.dumps(out, indent=2))
    print(json.dumps({k: v for k, v in out.items() if k != "intersection_wkt"}, indent=2))


if __name__ == "__main__":
    main()
