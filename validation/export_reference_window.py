"""Whole-window reference alerts for the web map (score.py only exports the holdout half).

Reads:  alerts_glad_l.json or alerts_glad_s2.json (fetch_alerts.py rows).
Writes: web/data/reference_alerts.geojson (CONTRACTS.md section 5: Polygon features, EPSG:4326, properties {source, date}):
        one polygon per connected patch of alert pixels of ANY date (score.py --merge-dates; date = earliest pixel date),
        for pixels whose centre is inside --bbox and dated in [--start, --end] (default: first scored date - 24 d to last
        scored date + 24 d, the same window score.py uses). Same function as score.py, so the holdout half is identical to
        the file score.py wrote.
"""
from __future__ import annotations

import argparse
import json

from score import _contract_ref, rows_to_features

SOURCES = {"GLAD-L": ("umd_glad_landsat_alerts__date", 0.00025), "GLAD-S2": ("umd_glad_sentinel2_alerts__date", 0.0001)}


def export(rows: list[dict], source: str, bbox, start: str, end: str) -> dict:
    field, deg = SOURCES[source]
    w, s, e, n = bbox
    keep = [r for r in rows if r.get(field) and start <= str(r[field])[:10] <= end
            and w <= r["longitude"] <= e and s <= r["latitude"] <= n]
    return _contract_ref(rows_to_features(keep, field, deg, source, merge_dates=True))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--alerts", required=True, help="alerts_glad_l.json / alerts_glad_s2.json")
    p.add_argument("--source", choices=list(SOURCES), required=True)
    p.add_argument("--bbox", type=float, nargs=4, metavar=("W", "S", "E", "N"), required=True)
    p.add_argument("--start", required=True, help="YYYY-MM-DD")
    p.add_argument("--end", required=True, help="YYYY-MM-DD")
    p.add_argument("--out", default="web/data/reference_alerts.geojson")
    a = p.parse_args()
    with open(a.alerts, encoding="utf-8") as f:
        rows = json.load(f)
    fc = export(rows, a.source, a.bbox, a.start, a.end)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(fc, f)
    print(f"{len(fc['features'])} {a.source} patches (any size) dated {a.start}..{a.end} -> {a.out}")


if __name__ == "__main__":
    main()
