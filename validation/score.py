"""Validation: score detections against public alerts (GLAD / RADD).

Reads:  web/data/detections.geojson (CONTRACTS.md section 2) and a reference alert source.
Writes: web/data/reference_alerts.geojson (section 5) and web/data/metrics.json (section 4).
"""
from __future__ import annotations

import argparse

import geopandas as gpd

BBox = tuple[float, float, float, float]  # (west, south, east, north), EPSG:4326


def load_reference(source: str, bbox: BBox, dates: list[str]) -> gpd.GeoDataFrame:
    """Load GLAD or RADD alerts clipped to bbox and dates; EPSG:4326, columns {source, date}."""
    # TODO: pick the access method for `source` ("GLAD" | "RADD") and cite it
    raise NotImplementedError


def match_detections(det: gpd.GeoDataFrame, ref: gpd.GeoDataFrame, tolerance_days: int) -> dict:
    """Spatially match detections to reference within +/- tolerance_days. Returns TP/FP/FN counts."""
    # TODO: define the matching rule (any overlap? IoU?) and document it
    raise NotImplementedError


def compute_metrics(matches: dict, tile: str, dates: list[str], reference_source: str, out_path: str) -> dict:
    """Compute precision/recall/F1 and write metrics.json per CONTRACTS.md section 4."""
    raise NotImplementedError


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--detections", default="web/data/detections.geojson")
    p.add_argument("--source", choices=["GLAD", "RADD"], required=True)
    p.add_argument("--bbox", type=float, nargs=4, metavar=("W", "S", "E", "N"), required=True)
    p.add_argument("--dates", nargs="+", required=True, help="YYYY-MM-DD ...")
    p.add_argument("--tolerance-days", type=int, required=True)
    p.add_argument("--tile", required=True)
    p.add_argument("--out-dir", default="web/data")
    p.parse_args()
    # TODO: load_reference -> match_detections -> compute_metrics
    raise NotImplementedError


if __name__ == "__main__":
    main()
