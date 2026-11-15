"""Lost blocks inside official protected areas and Indigenous lands of the 60 km AOI (validation/PREREG_scale.md rule).

Sources (both official, both queried with the AOI box W S E N -54.98 -8.48 -54.42 -7.92):
- Indigenous lands: FUNAI GeoServer layer Funai:tis_poligonais (WFS 1.0.0 GetFeature, GeoJSON, EPSG:4326).
  FUNAI's server refuses scripted clients (HTTP 403), so the response was read in a browser on 2026-11-14 and clipped
  there to the box -55.0 -8.5 -54.4 -7.9 (exact rectangle clipping, coordinates rounded to 1e-6 deg); that file is
  --funai (sha256 9e1407890c62fae49f603ccf806cc13ae86dd79caabd412adde6c22694bdcf72, gitignored under data/).
- Conservation units: MMA CNUC 07/2026 (INDE GeoServer layer MMA:cnuc_26_07_31), fetched here live.

A lost block counts for an area when its centre lies inside the area polygon. Lost = scale.lost_rule on blocks valid
on all 9 dates (the same rule and blocks as validation/scale.py). Counts are given for all valid blocks and for the
scored subset (original 20 km window excluded).

  python validation/protected_areas.py --stack data/stack_big_t2f174.nc --funai data/protected/funai_tis_clip.json \
    --out-geojson web/data/explore/big/protected.geojson --out-json web/data/explore/big/big_protected.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

import numpy as np
import shapely
import xarray as xr
from pyproj import Transformer
from shapely.geometry import box, mapping, shape

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scale  # noqa: E402

AOI_QUERY_BOX = (-54.98, -8.48, -54.42, -7.92)
CNUC_URL = ("https://geoservicos.inde.gov.br/geoserver/MMA/ows?service=WFS&version=1.0.0&request=GetFeature"
            "&typeName=MMA:cnuc_26_07_31&outputFormat=application/json&srsName=EPSG:4326"
            "&bbox={w},{s},{e},{n},EPSG:4326")
FUNAI_URL = ("https://geoserver.funai.gov.br/geoserver/Funai/ows?service=WFS&version=1.0.0&request=GetFeature"
             "&typeName=Funai%3Atis_poligonais&outputFormat=application%2Fjson&srsName=EPSG:4326"
             "&bbox=-54.98,-8.48,-54.42,-7.92,EPSG:4326")
SIMPLIFY_DEG = 0.0002  # ~22 m, display file only; counts use the unsimplified polygons


def blocks_in(poly, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    """Bool mask of block centres inside poly (boundary counts as inside)."""
    return shapely.covers(poly, shapely.points(lon, lat))


def fetch_cnuc(bbox) -> list[dict]:
    w, s, e, n = bbox
    with urllib.request.urlopen(CNUC_URL.format(w=w, s=s, e=e, n=n), timeout=120) as r:
        return json.load(r)["features"]


def run(stack: str, funai_path: str) -> tuple[dict, dict]:
    ds = xr.open_dataset(stack)
    hv = ds["hv_db"].values
    valid = np.isfinite(hv).all(axis=0)
    lost = scale.lost_rule(hv >= scale.frozen_T()) & valid
    xx, yy = np.meshgrid(ds["x"].values, ds["y"].values)
    lon, lat = Transformer.from_crs(ds.attrs["crs"], 4326, always_xy=True).transform(xx, yy)
    w, s, e, n = scale.ORIGINAL_BBOX
    scored = valid & ~((lon >= w) & (lon <= e) & (lat >= s) & (lat <= n))
    block_ha = float(abs(ds["x"].values[1] - ds["x"].values[0]) ** 2 / 1e4)
    aoi = box(lon.min(), lat.min(), lon.max(), lat.max())

    raw = Path(funai_path).read_bytes()
    funai = json.loads(raw)
    areas = []
    for f in funai["features"]:
        p = f["properties"]
        areas.append({"name": f"TI {p['terrai_nome']}", "kind": "Indigenous land (Terra Indigena)",
                      "source": "FUNAI tis_poligonais", "official_id": p["terrai_codigo"],
                      "detail": {k: p[k] for k in ("etnia_nome", "fase_ti", "modalidade_ti", "uf_sigla",
                                                    "superficie_perimetro_ha", "data_atualizacao")},
                      "geom": shape(f["geometry"])})
    cnuc = fetch_cnuc(AOI_QUERY_BOX)
    for f in cnuc:
        p = f["properties"]
        areas.append({"name": p["nome_uc"], "kind": f"Conservation unit ({p.get('categoria')}, {p.get('esfera')})",
                      "source": "MMA CNUC 07/2026", "official_id": p.get("cd_cnuc"), "detail": {},
                      "geom": shape(f["geometry"])})

    rows, feats = [], []
    for a in areas:
        g = a["geom"].intersection(aoi)
        if g.is_empty:
            continue
        inside = blocks_in(g, lon, lat)
        row = {"name": a["name"], "kind": a["kind"], "source": a["source"], "official_id": a["official_id"],
               **a["detail"],
               "valid_blocks_inside": int((inside & valid).sum()),
               "lost_blocks_inside": int((inside & lost).sum()),
               "lost_ha_inside": round(float((inside & lost).sum() * block_ha), 1),
               "scored_valid_blocks_inside": int((inside & scored).sum()),
               "scored_lost_blocks_inside": int((inside & lost & scored).sum()),
               "scored_lost_ha_inside": round(float((inside & lost & scored).sum() * block_ha), 1)}
        v = row["valid_blocks_inside"]
        row["lost_share_of_valid_blocks"] = row["lost_blocks_inside"] / v if v else None
        rows.append(row)
        lp = g.representative_point()
        feats.append({"type": "Feature", "properties": {"name": a["name"], "kind": a["kind"], "source": a["source"],
                                                        "label_lon": round(lp.x, 5), "label_lat": round(lp.y, 5)},
                      "geometry": mapping(shapely.set_precision(g.simplify(SIMPLIFY_DEG, preserve_topology=True), 1e-5))})
    outside = valid.copy()
    for a in areas:
        g = a["geom"].intersection(aoi)
        if not g.is_empty:
            outside &= ~blocks_in(g, lon, lat)
    summary = {
        "command": "python validation/protected_areas.py --stack data/stack_big_t2f174.nc --funai data/protected/funai_tis_clip.json "
                   "--out-geojson web/data/explore/big/protected.geojson --out-json web/data/explore/big/big_protected.json",
        "rule": "lost block (scale.lost_rule, valid on all 9 dates) whose centre lies inside the official polygon",
        "block_ha": block_ha, "aoi_lonlat_wsen": list(aoi.bounds),
        "total_lost_blocks": int(lost.sum()), "total_lost_blocks_scored": int((lost & scored).sum()),
        "areas": rows,
        "outside_all_areas": {"valid_blocks": int(outside.sum()), "lost_blocks": int((lost & outside).sum()),
                              "lost_share_of_valid_blocks": float((lost & outside).sum() / outside.sum()) if outside.sum() else None},
        "sources": {
            "funai": {"url": FUNAI_URL, "read": "2026-11-14 in a browser (scripted requests get HTTP 403)",
                      "server_timestamp": funai.get("timeStamp"), "features_in_query_box": funai.get("totalFeatures"),
                      "clipped_file_sha256": hashlib.sha256(raw).hexdigest(), "clip_box_wsen": funai.get("clip_box_wsen"),
                      "licence": "FUNAI geoprocessing page: may be reproduced provided the source is cited"},
            "cnuc": {"url": CNUC_URL.format(w=AOI_QUERY_BOX[0], s=AOI_QUERY_BOX[1], e=AOI_QUERY_BOX[2], n=AOI_QUERY_BOX[3]),
                     "features_in_query_box": len(cnuc), "fetched": "at run time"},
        },
        "display_file": {"simplify_deg": SIMPLIFY_DEG, "note": "protected.geojson is clipped to the AOI box and simplified for display; counts use unsimplified polygons"},
    }
    return summary, {"type": "FeatureCollection", "features": feats}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--stack", default="data/stack_big_t2f174.nc")
    p.add_argument("--funai", default="data/protected/funai_tis_clip.json")
    p.add_argument("--out-geojson", default="web/data/explore/big/protected.geojson")
    p.add_argument("--out-json", default="web/data/explore/big/big_protected.json")
    a = p.parse_args()
    summary, fc = run(a.stack, a.funai)
    Path(a.out_geojson).write_text(json.dumps(fc, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    Path(a.out_json).write_text(json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "sources"}, indent=1, ensure_ascii=False))
    print(f"protected.geojson {Path(a.out_geojson).stat().st_size:,d} bytes")


if __name__ == "__main__":
    main()
