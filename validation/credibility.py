"""Credibility pack for the 60 km forest map (descriptive only: no new threshold, nothing already scored is rescored).

1. Class metrics: forest AND non-forest precision / recall + confusion matrix, from the counts already in
   validation/scale_metrics.json (a_forest_map.median and median_pure_blocks).
2. Persistence: per block, how many of the 9 passes are classed forest (0-9), decoded from the lossless per-pass
   web layers (web/tools/make_big.py writes them with exact colours, nearest resampling, so every display pixel holds
   the class of one native 100 m block). The "uncertain" class (9-pass median HV within +/-0.5 dB of T_db) needs block
   HV values, i.e. data/stack_big_t2f174.nc; it is written only when --stack is given.
3. Lost-patch categories: a lost patch (web/data/explore/big/lost.geojson) is "alert_supported" when at least one of
   its blocks holds a GLAD-L or GLAD-S2 alert pixel dated in the precision window of PREREG_scale.md (2026-06-26 ..
   2026-11-05), with exactly scale.py's reader and block matching; otherwise "radar_only_unconfirmed".
   Check: on the scored blocks this must reproduce scale_metrics.json (244 GLAD-L and 406 GLAD-S2 lost blocks).
4. Watch priorities: the patches are already 8-connected merges of lost blocks (make_big.py); the 20 largest, with
   the distance from the patch to the nearest block that was already non-forest at the start (non-forest on >= 2 of
   06-26 / 07-08 / 07-20, the complement of the lost rule's start condition).

  python validation/credibility.py --big-dir web/data/explore/big --metrics validation/scale_metrics.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from pyproj import Transformer
from rasterio.features import rasterize
from rasterio.transform import Affine, from_origin
from rasterio.warp import Resampling, reproject
from scipy import ndimage
import shapely
from shapely.geometry import mapping, shape

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import scale  # noqa: E402

# Native block grid of the big stack (PREREG_scale.md: freqA pixel centres x 62370.., y 9121770.., 3000 x 3000 px,
# 5 x 5 blocks). Block centres = first pixel centre + 2 px (40 m).
CRS = "EPSG:32722"
BLOCK_M = 100.0
NY = NX = 600
XC = 62370 + 40 + BLOCK_M * np.arange(NX)
YC = 9121770 - 40 - BLOCK_M * np.arange(NY)
NATIVE_TF = from_origin(XC[0] - BLOCK_M / 2, YC[0] + BLOCK_M / 2, BLOCK_M, BLOCK_M)

FOREST_RGB, NONFOREST_RGB = (0x2F, 0x6B, 0x4F), (0xB4, 0x40, 0x1C)
UNCERTAIN_BAND_DB = 0.5  # display choice for the confidence layer, not a tuned or scored value
UNCERTAIN_RGB = (0x8A, 0x94, 0x90)  # neutral grey
PERSIST_COLORS = ["#b4401c", "#a24a24", "#90542c", "#7e5e34", "#6c683c", "#5a6244", "#485e4a", "#3a644d", "#33684e", "#2f6b4f"]
TOP_N = 20


# ---------- 1. class metrics ----------
def class_metrics(c: dict) -> dict:
    """c = fnf.metrics counts: tp = map forest & Hansen forest, fp = map forest & Hansen non-forest,
    fn = map non-forest & Hansen forest, tn = map non-forest & Hansen non-forest."""
    tp, fp, fn, tn = (int(c[k]) for k in ("tp", "fp", "fn", "tn"))
    n = tp + fp + fn + tn
    return {
        "n": n,
        "confusion": {"rows": "map class", "cols": "Hansen class",
                      "map_forest": {"hansen_forest": tp, "hansen_nonforest": fp},
                      "map_nonforest": {"hansen_forest": fn, "hansen_nonforest": tn}},
        "forest_precision": tp / (tp + fp), "forest_recall": tp / (tp + fn),
        "nonforest_precision": tn / (tn + fn), "nonforest_recall": tn / (tn + fp),
        "overall_agreement": (tp + tn) / n,
        "formulas": {"forest_precision": "tp / (tp + fp)", "forest_recall": "tp / (tp + fn)",
                     "nonforest_precision": "tn / (tn + fn)", "nonforest_recall": "tn / (tn + fp)",
                     "overall_agreement": "(tp + tn) / n"},
    }


# ---------- display layers -> classes ----------
def decode_classes(rgba: np.ndarray) -> np.ndarray:
    """uint8 per display pixel: 0 no data (transparent), 1 forest, 2 non-forest. Raises on any other colour."""
    out = np.zeros(rgba.shape[:2], np.uint8)
    opaque = rgba[..., 3] > 0
    f = opaque & np.all(rgba[..., :3] == FOREST_RGB, axis=-1)
    nf = opaque & np.all(rgba[..., :3] == NONFOREST_RGB, axis=-1)
    if (opaque & ~f & ~nf).any():
        raise ValueError("layer holds colours other than forest / non-forest: not a lossless make_big.py layer")
    out[f], out[nf] = 1, 2
    return out


def persistence(cls: np.ndarray) -> np.ndarray:
    """cls (9, h, w) of decode_classes. -1 where any pass has no data, else number of forest passes (0-9)."""
    valid = (cls > 0).all(axis=0)
    return np.where(valid, (cls == 1).sum(axis=0), -1)


def source_blocks(display_tf: Affine, h: int, w: int) -> np.ndarray:
    """Per display pixel, the flat index (row * NX + col) of the native block that make_big.py's warp sampled, -1 if
    none. Found by warping block indices with the same reproject call (nearest, same grids), so GDAL's approximate
    transformer picks exactly the same source block as it did for the layers."""
    idx = (np.arange(NY * NX, dtype=np.int32) + 1).reshape(NY, NX)
    out = np.zeros((h, w), np.int32)
    reproject(idx, out, src_transform=NATIVE_TF, src_crs=CRS, dst_transform=display_tf, dst_crs="EPSG:3857",
              resampling=Resampling.nearest, src_nodata=0, dst_nodata=0)
    return out - 1


def display_to_native(values: np.ndarray, src: np.ndarray, fill) -> tuple[np.ndarray, np.ndarray]:
    """Carry display-pixel values back to the native block grid with source_blocks().
    Returns (native array, bool 'represented' mask: blocks with at least one display pixel)."""
    keep = src.ravel() >= 0
    flat = src.ravel()[keep]
    out = np.full(NY * NX, fill, dtype=values.dtype)
    rep = np.zeros(NY * NX, bool)
    out[flat] = values.ravel()[keep]
    rep[flat] = True
    return out.reshape(NY, NX), rep.reshape(NY, NX)


def confidence_classes(med: np.ndarray, T: float, band: float = UNCERTAIN_BAND_DB) -> np.ndarray:
    """uint8 per block from the 9-pass median HV (dB): 0 no data, 1 forest, 2 non-forest, 3 uncertain (|med - T| <= band)."""
    out = np.zeros(med.shape, np.uint8)
    ok = np.isfinite(med)
    unc = ok & (np.abs(med - T) <= band)
    out[ok & ~unc & (med >= T)] = 1
    out[ok & ~unc & (med < T)] = 2
    out[unc] = 3
    return out


def warp_to_display(native: np.ndarray, display_tf: Affine, h: int, w: int) -> np.ndarray:
    """Same nearest warp as make_big.py (native block grid -> big.json EPSG:3857 grid); 0 = no data."""
    out = np.zeros((h, w), native.dtype)
    reproject(native, out, src_transform=NATIVE_TF, src_crs=CRS, dst_transform=display_tf, dst_crs="EPSG:3857",
              resampling=Resampling.nearest, src_nodata=0, dst_nodata=0)
    return out


# ---------- lost patches on the native grid ----------
def patch_labels(features: list) -> np.ndarray:
    """Native (600, 600) int array: patch id per block, 0 elsewhere (block centre inside the patch polygon)."""
    to_utm = Transformer.from_crs(4326, CRS, always_xy=True).transform
    fwd = lambda xy: np.column_stack(to_utm(xy[:, 0], xy[:, 1]))  # noqa: E731
    shapes_ = [(mapping(shapely.transform(shape(f["geometry"]), fwd)), int(f["properties"]["id"])) for f in features]
    return rasterize(shapes_, out_shape=(NY, NX), transform=NATIVE_TF, fill=0, dtype="int32")


def in_original_window() -> np.ndarray:
    xx, yy = np.meshgrid(XC, YC)
    lon, lat = Transformer.from_crs(CRS, 4326, always_xy=True).transform(xx, yy)
    w, s, e, n = scale.ORIGINAL_BBOX
    return (lon >= w) & (lon <= e) & (lat >= s) & (lat <= n)


def alert_block_map(source: str, bbox, start: dt.date, end: dt.date) -> np.ndarray:
    adates, alon, alat, _, _ = scale.read_alerts(bbox, source)
    ax, ay = Transformer.from_crs(4326, CRS, always_xy=True).transform(alon, alat)
    r, c = scale.block_index(np.asarray(ax), np.asarray(ay), XC, YC)
    return scale.alert_blocks(adates, r, c, (NY, NX), start, end)


def categorise(labels: np.ndarray, alert_any: np.ndarray) -> dict[int, str]:
    ids = np.unique(labels[labels > 0])
    hit = set(np.unique(labels[(labels > 0) & alert_any]).tolist())
    return {int(i): ("alert_supported" if int(i) in hit else "radar_only_unconfirmed") for i in ids}


def distance_to(target: np.ndarray, labels: np.ndarray) -> dict[int, float]:
    """Per patch id: min distance (m) from any of its block centres to the nearest target block centre."""
    if not target.any():
        return {}
    edt = ndimage.distance_transform_edt(~target) * BLOCK_M
    out = {}
    for i, sl in enumerate(ndimage.find_objects(labels), start=1):
        if sl is None:
            continue
        m = labels[sl] == i
        out[i] = float(edt[sl][m].min())
    return out


def hex_rgb(h: str) -> tuple[int, int, int]:
    return tuple(int(h[k:k + 2], 16) for k in (1, 3, 5))


def run(big_dir: Path, metrics_path: Path, stack: str | None = None) -> dict:
    met = json.loads(metrics_path.read_text())
    big = json.loads((big_dir / "big.json").read_text())
    gj = json.loads((big_dir / "lost.geojson").read_text())
    if met["grid"]["shape"] != [NY, NX] or met["grid"]["block_m"] != BLOCK_M or met["grid"]["crs"] != CRS:
        raise SystemExit("scale_metrics.json grid differs from the PREREG_scale.md block grid assumed here")
    T = float(met["T_db"])
    if T != scale.frozen_T() or T != float(big["T_db"]):
        raise SystemExit("T_db differs between fnf_metrics.json, scale_metrics.json and big.json")
    res = {}

    # 1
    fm = met["a_forest_map"]
    res["class_metrics"] = {"source": "validation/scale_metrics.json a_forest_map (counts copied, not recomputed)",
                            "scope": "scored blocks: big AOI, valid on all 9 passes, original window excluded",
                            "reference": "Hansen GFC v1.13 forest, block forest if >= 50 % of 25 px (a reference, not ground truth)",
                            "median": class_metrics(fm["median"]), "median_pure_blocks": class_metrics(fm["median_pure_blocks"])}

    # display layers (lossless) -> per-pass classes
    tf = Affine(*big["grid"]["transform"])
    cls = np.stack([decode_classes(np.asarray(Image.open(big_dir / f).convert("RGBA"))) for f in big["layers"]["forest"]])
    pers = persistence(cls)
    blk = source_blocks(tf, *pers.shape)
    lost_disp = np.asarray(Image.open(big_dir / big["layers"]["lost"]).convert("RGBA"))[..., 3] > 0

    # 2: persistence image + shares on the native grid
    img = np.zeros(pers.shape + (4,), np.uint8)
    for k, col in enumerate(PERSIST_COLORS):
        img[pers == k] = (*hex_rgb(col), 255)
    Image.fromarray(img, "RGBA").save(big_dir / "persistence.webp", format="WEBP", lossless=True, exact=True)
    pers_n, rep = display_to_native(pers.astype(np.int16), blk, -1)
    valid_n = pers_n >= 0
    counts = {str(k): int((pers_n == k).sum()) for k in range(10)}
    res["persistence"] = {
        "file": "persistence.webp", "definition": "number of the 9 passes on which the block is forest (HV >= T_db); 9 = forest on every pass",
        "colors": dict(zip(map(str, range(10)), PERSIST_COLORS)),
        "source": "decoded from the lossless forest_<date>.webp layers (exact classes, nearest resampling); no stack values used",
        "blocks": {"counted": int(valid_n.sum()), "per_count": counts,
                   "share": {k: v / int(valid_n.sum()) for k, v in counts.items()},
                   "note": "whole 60 km map incl. the original window; native 100 m blocks that have at least one display pixel "
                           f"({int(rep.sum()):,} of {NY * NX:,} blocks; the rest are dropped by nearest resampling and not counted). "
                           "Block of each display pixel found by warping block indices with make_big.py's reproject call."},
    }
    if stack:
        import xarray as xr
        import fnf
        ds = xr.open_dataset(stack)
        if [str(t)[:10] for t in ds.time.values] != big["dates"]:
            raise SystemExit("stack dates differ from big.json")
        if not (np.allclose(ds["x"].values, XC) and np.allclose(ds["y"].values, YC)):
            raise SystemExit("stack grid differs from the PREREG_scale.md block grid")
        hv = ds["hv_db"].values
        with np.errstate(all="ignore"):
            med = fnf.median_feature(np.where(np.isfinite(hv).all(axis=0), hv, np.nan))  # make_big.py's clip
        conf = confidence_classes(med, T)
        disp = warp_to_display(conf, tf, *pers.shape)
        med_disp = decode_classes(np.asarray(Image.open(big_dir / big["layers"]["median"]).convert("RGBA")))
        sure = (disp == 1) | (disp == 2)
        if (disp[sure] != med_disp[sure]).any() or ((disp > 0) != (med_disp > 0)).any():
            raise SystemExit("confidence layer disagrees with forest_median.webp outside the uncertain band")
        img = np.zeros(disp.shape + (4,), np.uint8)
        for v, col in ((1, FOREST_RGB), (2, NONFOREST_RGB), (3, UNCERTAIN_RGB)):
            img[disp == v] = (*col, 255)
        Image.fromarray(img, "RGBA").save(big_dir / "confidence.webp", format="WEBP", lossless=True, exact=True)
        n = int((conf > 0).sum())
        cnt = {"forest": int((conf == 1).sum()), "nonforest": int((conf == 2).sum()), "uncertain": int((conf == 3).sum())}
        res["confidence"] = {"file": "confidence.webp", "uncertain_band_db": UNCERTAIN_BAND_DB, "status": "computed",
                             "definition": f"9-pass median HV within +/-{UNCERTAIN_BAND_DB} dB of T_db = uncertain; otherwise the median map's class",
                             "note": "the +/-0.5 dB band is a display choice, not a tuned or scored value",
                             "colors": {"forest": "#2f6b4f", "non_forest": "#b4401c", "uncertain": "#8a9490"},
                             "scope": "whole 60 km map incl. the original window, native blocks valid on all 9 passes",
                             "blocks": cnt, "share": {k: v / n for k, v in cnt.items()}}
    else:
        res["confidence"] = {"uncertain_band_db": UNCERTAIN_BAND_DB, "status": "pending",
                             "note": "needs block HV from data/stack_big_t2f174.nc (run with --stack); +/-0.5 dB is a display choice"}

    # 3: categories
    feats = gj["features"]
    labels = patch_labels(feats)
    n_blocks = {int(f["properties"]["id"]): int(f["properties"]["n_blocks"]) for f in feats}
    got = np.bincount(labels.ravel(), minlength=max(n_blocks) + 1)
    bad = [i for i, n in n_blocks.items() if got[i] != n]
    if bad:
        raise SystemExit(f"{len(bad)} patches do not rasterise back to their n_blocks (first: {bad[:5]})")
    lost = labels > 0
    lost_back, _ = display_to_native(lost_disp.astype(np.uint8), blk, 0)
    if ((lost_back == 1) != (lost & rep)).any():
        raise SystemExit("lost.webp mapped back to the native grid disagrees with lost.geojson: block mapping is off")
    scored = lost & ~in_original_window()
    if int(scored.sum()) != met["loss_rule"]["lost_blocks"]:
        raise SystemExit(f"scored lost blocks {int(scored.sum())} != scale_metrics {met['loss_rule']['lost_blocks']}")
    bbox = tuple(met["b_alerts"]["alert_bbox_wsen"])
    p0, p1 = (dt.date.fromisoformat(d) for d in met["b_alerts"]["precision_window"])
    alerts = {}
    for src in ("GLAD-L", "GLAD-S2"):
        alerts[src] = alert_block_map(src, bbox, p0, p1)
        want = met["b_alerts"][src]["lost"]["n_with_alert"]
        if int((scored & alerts[src]).sum()) != want:
            raise SystemExit(f"{src}: {int((scored & alerts[src]).sum())} scored lost blocks with an alert != scale_metrics {want}")
    any_alert = alerts["GLAD-L"] | alerts["GLAD-S2"]
    cat = categorise(labels, any_alert)
    area = {int(f["properties"]["id"]): float(f["properties"]["area_ha"]) for f in feats}
    summ = {}
    for c in ("alert_supported", "radar_only_unconfirmed"):
        ids = [i for i, v in cat.items() if v == c]
        summ[c] = {"patches": len(ids), "ha": round(sum(area[i] for i in ids), 2)}
    res["lost_categories"] = {
        "definition": "alert_supported: at least one block of the patch holds a GLAD-L or GLAD-S2 alert pixel dated "
                      f"{p0} .. {p1} (PREREG_scale.md precision window, scale.py matching); radar_only_unconfirmed: none. "
                      "Radar-only patches are unconfirmed radar change, not deforestation.",
        "scope": "all lost patches in lost.geojson (whole 60 km map incl. the original window)",
        "patches": summ,
        "blocks_scored_area": {"lost": int(scored.sum()), "with_glad_l": int((scored & alerts['GLAD-L']).sum()),
                               "with_glad_s2": int((scored & alerts['GLAD-S2']).sum()),
                               "with_either": int((scored & any_alert).sum()),
                               "check": "with_glad_l and with_glad_s2 reproduce scale_metrics.json b_alerts.*.lost.n_with_alert"},
    }
    for f in feats:
        f["properties"]["category"] = cat[int(f["properties"]["id"])]

    # 4: watch priorities
    start_nf = (cls[:3] == 2).sum(axis=0) >= 2
    start_nf_n, _ = display_to_native(start_nf.astype(np.uint8), blk, 0)
    dist = distance_to(start_nf_n.astype(bool), labels)
    ranked = sorted(feats, key=lambda f: (-f["properties"]["area_ha"], f["properties"]["id"]))[:TOP_N]
    res["watch_priorities"] = {
        "definition": f"the {TOP_N} largest lost patches (8-connected merges of lost blocks, lost.geojson), ranked by area. "
                      "distance_m = from the patch's nearest block centre to the nearest block centre that was already non-forest "
                      "at the start (non-forest on >= 2 of 06-26/07-08/07-20); 100 m = touching. Places to check first, not confirmed clearing.",
        "items": [{"id": f["properties"]["id"], "centroid_lon": f["properties"]["centroid_lon"],
                   "centroid_lat": f["properties"]["centroid_lat"], "area_ha": f["properties"]["area_ha"],
                   "category": cat[int(f["properties"]["id"])],
                   "distance_m": round(dist.get(int(f["properties"]["id"]), float("nan")), 1),
                   "in_original_window": f["properties"]["in_original_window"],
                   "first_switch_date": f["properties"].get("first_switch_date")} for f in ranked],
    }
    return res, big, gj


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--big-dir", default="web/data/explore/big")
    p.add_argument("--metrics", default="validation/scale_metrics.json")
    p.add_argument("--stack", default=None, help="data/stack_big_t2f174.nc, only for the uncertain class")
    a = p.parse_args()
    d = Path(a.big_dir)
    res, big, gj = run(d, Path(a.metrics), a.stack)
    big.update(res)
    (d / "big.json").write_text(json.dumps(big, indent=1))
    (d / "lost.geojson").write_text(json.dumps(gj, separators=(",", ":")))
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
