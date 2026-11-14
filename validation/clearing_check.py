"""Clearing check: GLAD alert events per split half in the detectable period, by size.

Reads:  alerts_glad_l.json / alerts_glad_s2.json (fetch_alerts.py) for the window.
Prints: per source and half (north = tune, south = holdout, 1 km buffer strip on the centre latitude, as
        run_chain.sh), the number and area of events with dates in (AFTER, UNTIL], an event being connected alert
        pixels of any date in that period (score.py --merge-dates), at the size cut-offs given.
AFTER is the last date that only ever serves as baseline (the date before the first scored date).
"""
from __future__ import annotations

import argparse
import json
import os

from shapely.geometry import shape

from score import geodesic_ha, rows_to_features

SOURCES = {"GLAD-L": ("alerts_glad_l.json", "umd_glad_landsat_alerts", 0.00025),
           "GLAD-S2": ("alerts_glad_s2.json", "umd_glad_sentinel2_alerts", 0.0001)}


def halves(bbox, buffer_deg: float = 0.0045) -> dict:
    w, s, e, n = bbox
    c = (s + n) / 2
    return {"tune (north)": (w, c + buffer_deg, e, n), "holdout (south)": (w, s, e, c - buffer_deg)}


def events(rows: list[dict], field: str, deg: float, after: str, until: str) -> list[tuple[float, object, str, str]]:
    rows = [r for r in rows if r[field] and after < r[field] <= until]
    fc = rows_to_features(rows, field, deg, "x", merge_dates=True)
    return [(geodesic_ha(g := shape(f["geometry"])), g.representative_point(), f["properties"]["date"],
             f["properties"]["date_last"]) for f in fc["features"]]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--alert-dir", required=True)
    p.add_argument("--bbox", type=float, nargs=4, metavar=("W", "S", "E", "N"), required=True)
    p.add_argument("--after", required=True, help="events dated strictly after this date ...")
    p.add_argument("--until", required=True, help="... and on or before this one (last scored date)")
    p.add_argument("--min-ha", type=float, nargs="+", default=[1.0, 2.0, 5.0])
    p.add_argument("--out", help="optional JSON with the counts")
    a = p.parse_args()
    res = {}
    for src, (fname, ds, deg) in SOURCES.items():
        with open(os.path.join(a.alert_dir, fname), encoding="utf-8") as f:
            ev = events(json.load(f), f"{ds}__date", deg, a.after, a.until)
        for half, (w, s, e, n) in halves(a.bbox).items():
            sel = [x for x in ev if w <= x[1].x <= e and s <= x[1].y <= n]
            rec = {"n_events": len(sel), "area_ha": round(sum(x[0] for x in sel), 2),
                   **{f"n_ge_{c:g}ha": sum(1 for x in sel if x[0] >= c) for c in a.min_ha},
                   "largest": [(round(x[0], 2), x[2], x[3]) for x in sorted(sel, key=lambda x: -x[0])[:5]]}
            res[f"{src} {half}"] = rec
            cuts = "  ".join(f">={c:g} ha: {rec[f'n_ge_{c:g}ha']}" for c in a.min_ha)
            print(f"{src:8s} {half:16s} events {rec['n_events']:5d}  {rec['area_ha']:8.2f} ha  {cuts}  "
                  f"largest {rec['largest'][:3]}")
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump({"bbox": a.bbox, "after": a.after, "until": a.until, "halves": halves(a.bbox), "counts": res},
                      f, indent=1)


if __name__ == "__main__":
    main()
