"""Validation: patch-level agreement of detections with public alerts (RADD, GLAD-L, GLAD-S2, GFW integrated).

Reads:  web/data/detections.geojson (CONTRACTS.md section 2) and reference alerts from the GFW Data API (free API
        key, see README) or a JSON file of the same query rows saved earlier.
Writes: web/data/reference_alerts.geojson (section 5) and web/data/metrics.json (section 4).

Scores the HOLDOUT split only and refuses to run without one. The numbers are agreement with another alert
product, which is a reference and not ground truth: call them agreement, never accuracy.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
import urllib.request
from typing import Callable

from pyproj import Geod
from shapely import STRtree, union_all
from shapely.geometry import box, mapping, shape

BBox = tuple[float, float, float, float]  # (west, south, east, north), EPSG:4326

GFW_API = "https://data-api.globalforestwatch.org"
# GFW Data API dataset ids (checked against GET /dataset/<id>/latest on 2026-11-14)
SOURCES = {
    "RADD": "wur_radd_alerts",
    "GLAD-L": "umd_glad_landsat_alerts",
    "GLAD-S2": "umd_glad_sentinel2_alerts",
    "GFW-INTEGRATED": "gfw_integrated_alerts",
}
CONFIDENCE = ["nominal", "high", "highest"]  # value table of <dataset>__confidence (GET .../latest/fields)
GEOD = Geod(ellps="WGS84")

Http = Callable[..., dict]


def _http(url: str, body: dict | None = None, headers: dict | None = None) -> dict:
    """GET (body None) or POST JSON; returns the parsed JSON response."""
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def _date(s: str) -> str:
    return dt.date.fromisoformat(s).isoformat()  # raises ValueError on anything that is not YYYY-MM-DD


def _days(a: str, b: str) -> int:
    return abs((dt.date.fromisoformat(a) - dt.date.fromisoformat(b)).days)


def geodesic_ha(geom) -> float:
    """Area on the WGS84 ellipsoid in hectares (geometry in EPSG:4326 degrees)."""
    return abs(GEOD.geometry_area_perimeter(geom)[0]) / 1e4


# ---- reference alerts --------------------------------------------------------------------------------------

def grid_from_asset_uri(uri: str) -> float:
    """Pixel size in degrees from a GFW 'Raster tile set' URI '.../epsg-4326/<tile_deg>/<tile_px>/...'.

    e.g. wur_radd_alerts .../epsg-4326/10/100000/date_conf/... -> 10 / 100000 = 1e-4 deg (about 10 m).
    """
    m = re.search(r"/epsg-4326/(\d+)/(\d+)/", uri)
    if not m:
        raise ValueError(f"no epsg-4326 grid in asset uri {uri!r}")
    return int(m.group(1)) / int(m.group(2))


def dataset_pixel_deg(dataset: str, version: str = "latest", get: Http = _http) -> float:
    """Read the dataset's grid from its public metadata (no API key needed for this endpoint)."""
    assets = get(f"{GFW_API}/dataset/{dataset}/{version}")["data"]["assets"]
    for a in assets:
        if a[0] == "Raster tile set" and "/epsg-4326/" in a[1]:
            return grid_from_asset_uri(a[1])
    raise ValueError(f"{dataset}/{version}: no epsg-4326 raster tile set; pass pixel_deg explicitly")


def rows_to_features(rows: list[dict], date_field: str, pixel_deg: float, source: str) -> dict:
    """Alert pixels -> GeoJSON polygons {source, date}: one polygon per connected patch of same-date pixels.

    Each row's longitude/latitude must be a pixel centre on the grid (checked: (coord / pixel_deg) - 0.5 must be
    within 0.05 of an integer); the pixel square is rebuilt from the integer grid index, so neighbours share
    exactly the same edge coordinates, and same-date squares are unioned.
    """
    by_date: dict[str, list] = {}
    for r in rows:
        lon, lat = float(r["longitude"]), float(r["latitude"])
        idx = []
        for v in (lon, lat):
            k = v / pixel_deg - 0.5
            if abs(k - round(k)) > 0.05:
                raise ValueError(f"({lon}, {lat}) is not a pixel centre of a {pixel_deg} deg grid")
            idx.append(round(k))
        i, j = idx
        sq = box(i * pixel_deg, j * pixel_deg, (i + 1) * pixel_deg, (j + 1) * pixel_deg)
        by_date.setdefault(_date(str(r[date_field])[:10]), []).append(sq)
    feats = []
    for d in sorted(by_date):
        u = union_all(by_date[d])
        for g in getattr(u, "geoms", [u]):
            feats.append({"type": "Feature", "geometry": mapping(g), "properties": {"source": source, "date": d}})
    return {"type": "FeatureCollection", "features": feats}


def load_reference(
    source: str,
    bbox: BBox,
    dates: list[str],
    api_key: str | None = None,
    origin: str | None = None,
    min_confidence: str | None = None,
    version: str = "latest",
    rows_file: str | None = None,
    pixel_deg: float | None = None,
    http: Http = _http,
) -> dict:
    """Reference alerts in bbox with min(dates) <= alert date <= max(dates), as GeoJSON polygons {source, date}.

    Queries POST /dataset/<id>/<version>/query/json with the bbox as geometry (needs a GFW API key, header
    x-api-key; also an Origin header if the key is domain-restricted). To catch a silently truncated answer it
    also asks for SUM(area__ha) over the same query and compares it with the rows it got. rows_file instead
    reads rows saved earlier from that same query (a JSON list, or the API's {"data": [...]} answer).
    min_confidence ("nominal" | "high" | "highest") drops lower-confidence pixels after download.
    """
    if source not in SOURCES:
        raise ValueError(f"unknown source {source!r}; one of {sorted(SOURCES)}")
    ds = SOURCES[source]
    start, end = _date(min(dates)), _date(max(dates))
    date_f, conf_f = f"{ds}__date", f"{ds}__confidence"
    if pixel_deg is None:
        pixel_deg = dataset_pixel_deg(ds, version, http)

    if rows_file:
        with open(rows_file, encoding="utf-8") as f:
            got = json.load(f)
        rows = got["data"] if isinstance(got, dict) else got
        rows = [r for r in rows if start <= str(r[date_f])[:10] <= end]
    else:
        if not api_key:
            raise RuntimeError("GFW Data API needs an API key (free): see validation/README.md, then set GFW_API_KEY")
        w, s, e, n = bbox
        geom = {"type": "Polygon", "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]]}
        where = f"WHERE {date_f} >= '{start}' AND {date_f} <= '{end}'"  # dates validated by _date()
        url = f"{GFW_API}/dataset/{ds}/{version}/query/json"
        headers = {"x-api-key": api_key, **({"Origin": origin} if origin else {})}
        rows = http(url, {"sql": f"SELECT longitude, latitude, area__ha, {date_f}, {conf_f} FROM results {where}",
                          "geometry": geom}, headers)["data"]
        total = http(url, {"sql": f"SELECT SUM(area__ha) FROM results {where}", "geometry": geom}, headers)["data"]
        api_ha = float(next(iter(total[0].values())) or 0.0) if total else 0.0
        got_ha = sum(float(r["area__ha"]) for r in rows)
        if abs(api_ha - got_ha) > max(1e-6, 1e-3 * api_ha):
            raise RuntimeError(f"row area {got_ha:.4f} ha != API SUM {api_ha:.4f} ha: answer looks truncated; "
                               "use a smaller bbox or date range")
    if min_confidence:
        keep = set(CONFIDENCE[CONFIDENCE.index(min_confidence):])
        rows = [r for r in rows if r.get(conf_f) in keep]
    return rows_to_features(rows, date_f, pixel_deg, source)


# ---- holdout split -----------------------------------------------------------------------------------------

def make_holdout(holdout_bbox: BBox | None, holdout_dates: list[str] | None) -> dict:
    """The holdout part of pipeline/detect's split. Exactly one of bbox / dates; anything else is refused."""
    if holdout_bbox is not None and holdout_dates:
        raise ValueError("give --holdout-bbox or --holdout-dates, not both")
    if holdout_bbox is not None:
        w, s, e, n = (float(v) for v in holdout_bbox)
        if not (w < e and s < n):
            raise ValueError("holdout bbox needs west < east and south < north")
        return {"bbox": (w, s, e, n)}
    if holdout_dates:
        return {"dates": sorted({_date(d) for d in holdout_dates})}
    raise ValueError("refusing to score: no holdout split given (use the same split as pipeline/detect)")


def in_holdout(feature: dict, holdout: dict) -> bool:
    """bbox split: the patch's representative point is inside the box. dates split: the patch date is listed."""
    if "bbox" in holdout:
        p = shape(feature["geometry"]).representative_point()
        w, s, e, n = holdout["bbox"]
        return w <= p.x <= e and s <= p.y <= n
    return feature["properties"]["date"] in holdout["dates"]


# ---- matching ----------------------------------------------------------------------------------------------

def _cover(geom, others: list) -> float:
    """Fraction of geom's (geodesic) area covered by the union of `others`; 0 if none intersect."""
    if not others:
        return 0.0
    inter = geom.intersection(union_all(others))
    if inter.is_empty:
        return 0.0
    return geodesic_ha(inter) / geodesic_ha(geom)


def match_detections(det: dict, ref: dict, tolerance_days: int, overlap_threshold: float) -> dict:
    """Patch-level matching (rule also in README).

    A detection patch D and a reference patch R are compatible if |date(D) - date(R)| <= tolerance_days.
    D agrees if the union of compatible R covers at least overlap_threshold of D's area, and more than zero;
    likewise R agrees if the union of compatible D covers at least overlap_threshold of R's area.
    Areas are geodesic (WGS84). overlap_threshold = 0 means any overlap.
      precision_like = agreeing detections / detections
      recall_like    = agreeing reference patches / reference patches
      f1_like        = 2 p r / (p + r)
    A ratio with a zero denominator is None. Returns the counts, the three ratios and per-patch details.
    """
    if not 0.0 <= overlap_threshold <= 1.0:
        raise ValueError("overlap_threshold must be in [0, 1]")
    dg = [shape(f["geometry"]) for f in det["features"]]
    rg = [shape(f["geometry"]) for f in ref["features"]]
    dd = [f["properties"]["date"] for f in det["features"]]
    rd = [f["properties"]["date"] for f in ref["features"]]
    rtree, dtree = STRtree(rg), STRtree(dg)

    det_rows = []
    for i, g in enumerate(dg):
        hits = [j for j in rtree.query(g) if _days(dd[i], rd[j]) <= tolerance_days and g.intersects(rg[j])]
        c = _cover(g, [rg[j] for j in hits])
        det_rows.append({"id": det["features"][i]["properties"].get("id"), "date": dd[i], "cover": c,
                         "agrees": c > 0 and c >= overlap_threshold, "ref_dates": sorted({rd[j] for j in hits})})
    ref_rows = []
    for j, g in enumerate(rg):
        hits = [i for i in dtree.query(g) if _days(dd[i], rd[j]) <= tolerance_days and g.intersects(dg[i])]
        c = _cover(g, [dg[i] for i in hits])
        ref_rows.append({"index": j, "date": rd[j], "cover": c, "agrees": c > 0 and c >= overlap_threshold})

    n_det, n_ref = len(det_rows), len(ref_rows)
    a_det, a_ref = sum(r["agrees"] for r in det_rows), sum(r["agrees"] for r in ref_rows)
    p = a_det / n_det if n_det else None
    r = a_ref / n_ref if n_ref else None
    f1 = None if p is None or r is None else (0.0 if p + r == 0 else 2 * p * r / (p + r))
    return {"n_detections": n_det, "n_reference": n_ref, "n_detections_agreeing": a_det,
            "n_reference_agreeing": a_ref, "precision_like": p, "recall_like": r, "f1_like": f1,
            "tolerance_days": tolerance_days, "overlap_threshold": overlap_threshold,
            "detections": det_rows, "reference": ref_rows}


def compute_metrics(matches: dict, tile: str, dates: list[str], reference_source: str, out_path: str) -> dict:
    """Write metrics.json per CONTRACTS.md section 4 (holdout agreement). Keeps an existing hand_labeled block."""
    hand = None
    if os.path.exists(out_path):
        with open(out_path, encoding="utf-8") as f:
            hand = json.load(f).get("hand_labeled")
    m = {
        "agreement": {"precision_like": matches["precision_like"], "recall_like": matches["recall_like"],
                      "f1_like": matches["f1_like"], "level": "patch", "split": "holdout"},
        "hand_labeled": hand,
        "n_detections": matches["n_detections"],
        "n_reference": matches["n_reference"],
        "tile": tile,
        "dates": sorted(dates),
        "reference_source": reference_source,
        "notes": (f"Patch-level agreement with {reference_source} alerts on the holdout split only: dates within "
                  f"+/-{matches['tolerance_days']} days and overlap >= {matches['overlap_threshold']:g} of patch "
                  f"area ({matches['n_detections_agreeing']} of {matches['n_detections']} detections, "
                  f"{matches['n_reference_agreeing']} of {matches['n_reference']} reference patches). "
                  "Alerts are a reference, not ground truth; this is not accuracy."),
    }
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(m, f, indent=1)
    return m


def lag_table(det: dict, matches: dict) -> list[dict]:
    """Per agreeing detection: first_hh_date, first_hv_date and the earliest compatible alert date.

    Rows with any of the three missing are skipped. Lead days are alert date minus first date (positive = the
    radar channel fired before the alert).
    """
    out = []
    for f, m in zip(det["features"], matches["detections"]):
        p = f["properties"]
        hh, hv = p.get("first_hh_date"), p.get("first_hv_date")
        if not (m["agrees"] and hh and hv and m["ref_dates"]):
            continue
        alert = m["ref_dates"][0]
        lead = lambda d: (dt.date.fromisoformat(alert) - dt.date.fromisoformat(d)).days  # noqa: E731
        out.append({"id": p.get("id"), "date": p["date"], "first_hh_date": hh, "first_hv_date": hv,
                    "alert_date": alert, "hh_lead_days": lead(hh), "hv_lead_days": lead(hv)})
    return out


def _filter(fc: dict, keep) -> dict:
    return {"type": "FeatureCollection", "features": [f for f in fc["features"] if keep(f)]}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--detections", default="web/data/detections.geojson")
    p.add_argument("--source", choices=sorted(SOURCES), required=True)
    p.add_argument("--holdout-bbox", type=float, nargs=4, metavar=("W", "S", "E", "N"), help="same as detect")
    p.add_argument("--holdout-dates", nargs="+", help="same as detect")
    p.add_argument("--bbox", type=float, nargs=4, metavar=("W", "S", "E", "N"),
                   help="area to load alerts for; required with --holdout-dates (defaults to the holdout bbox)")
    p.add_argument("--dates", nargs="+", help="detection dates to score with a bbox split (default: all in the file)")
    p.add_argument("--tolerance-days", type=int, required=True)
    p.add_argument("--overlap-threshold", type=float, required=True, help="0..1 of patch area; 0 = any overlap")
    p.add_argument("--min-confidence", choices=CONFIDENCE)
    p.add_argument("--reference-file", help="JSON rows saved from the same GFW query (instead of calling the API)")
    p.add_argument("--origin", help="Origin header, if the API key is restricted to domains")
    p.add_argument("--tile", required=True)
    p.add_argument("--lag-table", help="optional CSV: first_hh_date / first_hv_date / alert date per agreeing detection")
    p.add_argument("--out-dir", default="web/data")
    a = p.parse_args()
    try:
        holdout = make_holdout(a.holdout_bbox, a.holdout_dates)
    except ValueError as e:
        p.error(str(e))

    with open(a.detections, encoding="utf-8") as f:
        det_all = json.load(f)
    if "bbox" in holdout:
        want = set(a.dates) if a.dates else None
        det = _filter(det_all, lambda f: in_holdout(f, holdout) and (want is None or f["properties"]["date"] in want))
        area = tuple(a.bbox) if a.bbox else holdout["bbox"]
    else:
        if not a.bbox:
            p.error("--bbox is required with --holdout-dates")
        det = _filter(det_all, lambda f: in_holdout(f, holdout))
        area = tuple(a.bbox)
    dates = sorted({f["properties"]["date"] for f in det["features"]} | set(holdout.get("dates", [])))
    if not dates:
        p.error("no holdout detection dates to score")
    lo = (dt.date.fromisoformat(dates[0]) - dt.timedelta(days=a.tolerance_days)).isoformat()
    hi = (dt.date.fromisoformat(dates[-1]) + dt.timedelta(days=a.tolerance_days)).isoformat()
    ref = load_reference(a.source, area, [lo, hi], os.environ.get("GFW_API_KEY"), a.origin, a.min_confidence,
                         rows_file=a.reference_file)
    if "bbox" in holdout:
        ref = _filter(ref, lambda f: in_holdout(f, holdout))

    os.makedirs(a.out_dir, exist_ok=True)
    with open(os.path.join(a.out_dir, "reference_alerts.geojson"), "w", encoding="utf-8") as f:
        json.dump(ref, f)
    matches = match_detections(det, ref, a.tolerance_days, a.overlap_threshold)
    m = compute_metrics(matches, a.tile, dates, a.source, os.path.join(a.out_dir, "metrics.json"))
    print(json.dumps(m["agreement"]), m["notes"])
    if a.lag_table:
        rows = lag_table(det, matches)
        with open(a.lag_table, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["id", "date", "first_hh_date", "first_hv_date", "alert_date",
                                              "hh_lead_days", "hv_lead_days"])
            w.writeheader()
            w.writerows(rows)
        print(f"{len(rows)} lag-table rows -> {a.lag_table}")


if __name__ == "__main__":
    main()
