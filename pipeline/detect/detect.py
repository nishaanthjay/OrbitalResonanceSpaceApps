"""Pipeline B: JJ-FAST-style change detection on the dB stack.

Reads:  data/stack_<tile>.nc  (CONTRACTS.md section 1: dims (time, y, x), hh_db / hv_db float32 dB,
        CRS in attrs["crs"], time as datetime64; one track/frame only, so "same-track" is guaranteed by load).
Writes: web/data/detections.geojson (section 2; features for the same date are replaced, others kept) and
        web/data/change_hh_<date>.tif / change_hv_<date>.tif (section 3).

What the JJ-FAST papers (see README Sources) say, and what they do not:
  - Detection compares the latest image with the average of past images (KC25 slides, "Average" vs "Latest").
  - Early-stage clearing: HH increases (mean +1.2 dB in their example); late stage: HV decreases (mean -3.2 dB)
    (KC23). Our early/late labels follow that.
  - Threshold values are marked "Parameter is under adjusting" and were for ALOS-2 ScanSAR, so none are
    hardcoded here: thresholds and min size are CLI parameters (record the chosen values in CLAUDE.md).
  - NOT stated in the papers: whether the average is taken in dB or linear power. See baseline().
"""
from __future__ import annotations

import argparse
import json
import os
from typing import Literal

import numpy as np
import xarray as xr
import rioxarray  # noqa: F401  (registers the .rio accessor)
from pyproj import CRS, Transformer
from rasterio.enums import Resampling
from rasterio.features import shapes
from scipy import ndimage
from shapely.geometry import mapping, shape
from shapely.ops import transform as shp_transform

STAGE_NONE, STAGE_EARLY, STAGE_LATE = 0, 1, 2
STAGE_NAMES = {STAGE_EARLY: "early", STAGE_LATE: "late"}
MAX_COG_BYTES = 20 * 1024 * 1024


def _crs(da: xr.DataArray | xr.Dataset) -> CRS:
    crs = da.rio.crs
    if crs is None:
        raise ValueError("no CRS on data; the stack must carry attrs['crs'] (CONTRACTS.md section 1)")
    return CRS.from_user_input(crs)


def _with_crs(da: xr.DataArray, crs: str) -> xr.DataArray:
    return da.rio.write_crs(crs)


def baseline(stack: xr.Dataset, date: str, average: Literal["linear", "db"] = "linear") -> xr.Dataset:
    """Mean backscatter of all dates strictly earlier than `date` (the stack is a single track).

    Averaging domain: the JJ-FAST papers do not state it, so this is OUR choice, default "linear":
    power is averaged in linear units then converted back to dB. Linear power is what speckle and
    multilooking average over, so it is the unbiased estimate of the expected backscatter; averaging in dB
    gives the geometric mean, biased low and more outlier-robust. Pass average="db" to compare. This is an
    open decision for the team to confirm against real data.
    """
    t = np.datetime64(date, "ns")
    prev = stack[["hh_db", "hv_db"]].sel(time=stack["time"] < t)
    if prev.sizes["time"] == 0:
        raise ValueError(f"no dates earlier than {date} in the stack; cannot form a baseline")
    out = {}
    for v in ("hh_db", "hv_db"):
        if average == "linear":
            m = (10.0 ** (prev[v] / 10.0)).mean("time", skipna=True)
            out[v] = (10.0 * np.log10(m)).astype(np.float32)
        elif average == "db":
            out[v] = prev[v].mean("time", skipna=True).astype(np.float32)
        else:
            raise ValueError("average must be 'linear' or 'db'")
    ds = xr.Dataset(out, attrs=stack.attrs)
    return ds


def change_maps(stack: xr.Dataset, date: str, average: Literal["linear", "db"] = "linear") -> tuple[xr.DataArray, xr.DataArray]:
    """Return (d_hh, d_hv): dB of `date` minus the baseline, float32, with CRS attached."""
    t = np.datetime64(date, "ns")
    if t not in stack["time"].values:
        raise KeyError(f"{date} is not a date in the stack")
    cur = stack.sel(time=t)
    base = baseline(stack, date, average)
    crs = stack.attrs["crs"]
    d_hh = _with_crs((cur["hh_db"] - base["hh_db"]).astype(np.float32).rename("d_hh"), crs)
    d_hv = _with_crs((cur["hv_db"] - base["hv_db"]).astype(np.float32).rename("d_hv"), crs)
    return d_hh, d_hv


def apply_thresholds(
    d_hh: xr.DataArray,
    d_hv: xr.DataArray,
    hh_thresh: float | None,
    hv_thresh: float | None,
) -> tuple[xr.DataArray, xr.DataArray]:
    """Candidate clearing pixels and their stage. Thresholds are positive dB magnitudes (parameters, no defaults).

    - HH rise:  d_hh >= hh_thresh   -> early-stage signal (HH-led)
    - HV drop:  d_hv <= -hv_thresh  -> late-stage signal (HV-led)
    A pixel is a candidate if either fires ("and/or"). Stage is "late" when HV fires (including both),
    "early" when only HH fires. Pass None to disable a channel. NaN pixels never fire.

    Returns (mask: bool, stage: int8 with 0 none / 1 early / 2 late).
    """
    hh_hit = (d_hh >= hh_thresh) if hh_thresh is not None else xr.zeros_like(d_hh, dtype=bool)
    hv_hit = (d_hv <= -hv_thresh) if hv_thresh is not None else xr.zeros_like(d_hv, dtype=bool)
    mask = hh_hit | hv_hit
    stage = xr.where(hv_hit, STAGE_LATE, xr.where(hh_hit, STAGE_EARLY, STAGE_NONE)).astype(np.int8)
    return mask.rename("mask"), stage.rename("stage")


def mask_nonforest(mask: xr.DataArray, forest_mask: xr.DataArray) -> xr.DataArray:
    """Keep only candidate pixels that are forest. `forest_mask` is a boolean raster on the same grid as `mask`.

    OPEN DECISION (team): which forest-mask dataset to use. Candidates, all free (verify current URLs/versions):
      1. Hansen/UMD Global Forest Change (treecover2000 + lossyear, 30 m): GEE asset UMD/hansen/global_forest_change_*
         or GeoTIFF tiles from the Hansen project page. Threshold treecover (e.g. >= 30 %) and remove lossyear <= baseline year.
      2. ESA WorldCover 10 m (class 10 = tree cover): open bucket s3://esa-worldcover (anonymous access) or the
         terrascope.be viewer; only 2020/2021 epochs.
      3. JAXA global PALSAR/PALSAR-2 forest/non-forest (FNF) map, 25 m yearly: free download from the JAXA EORC
         site (registration); same L-band sensor family as JJ-FAST's own mask.
    The mask must be resampled onto the stack grid first (see load_forest_mask()).
    """
    if mask.shape != forest_mask.shape:
        raise ValueError(f"forest mask shape {forest_mask.shape} != detection grid {mask.shape}; reproject it first")
    return mask & xr.DataArray(forest_mask.values.astype(bool), coords=mask.coords, dims=mask.dims)


def load_forest_mask(path: str, template: xr.DataArray) -> xr.DataArray:
    """Read a binary forest raster (non-zero = forest, nodata = not forest) and resample it onto `template`'s grid."""
    raw = rioxarray.open_rasterio(path).squeeze(drop=True)
    nodata = raw.rio.nodata
    m = raw.rio.reproject_match(template, resampling=Resampling.nearest)
    v = m.values
    ok = v != 0
    if nodata is not None:
        ok &= v != nodata
    return xr.DataArray(ok, coords=template.coords, dims=template.dims)


def pixel_area_ha(da: xr.DataArray) -> np.ndarray:
    """Per-pixel area in hectares, shape (ny, nx), from the real grid spacing and CRS.

    Projected CRS: |dx|*|dy| in metres (other units rejected). Geographic CRS: geodesic area of each row's
    cell on the CRS ellipsoid, so it varies with latitude.
    """
    crs = _crs(da)
    dx, dy = (abs(v) for v in da.rio.resolution())
    ny, nx = da.sizes["y"], da.sizes["x"]
    if crs.is_geographic:
        geod = crs.get_geod()
        rows = []
        for yc in da["y"].values:
            lo, hi = float(yc) - dy / 2, float(yc) + dy / 2
            a, _ = geod.polygon_area_perimeter([0, dx, dx, 0], [lo, lo, hi, hi])
            rows.append(abs(a) / 1e4)
        return np.repeat(np.asarray(rows)[:, None], nx, axis=1)
    unit = crs.axis_info[0].unit_name.lower()
    if unit not in ("metre", "meter"):
        raise ValueError(f"unsupported CRS length unit {unit!r}; reproject the stack to metres or degrees")
    return np.full((ny, nx), dx * dy / 1e4)


def cluster_and_filter(mask: xr.DataArray, min_ha: float) -> xr.DataArray:
    """Label 8-connected clusters of True pixels and drop clusters smaller than `min_ha`.

    Cluster area is the sum of real per-pixel areas (pixel_area_ha), not a hardcoded value.
    Returns an int32 label raster (0 = background, ids renumbered 1..n) on the same grid as `mask`.
    """
    lab, n = ndimage.label(mask.values.astype(bool), structure=np.ones((3, 3), dtype=int))
    out = np.zeros(lab.shape, dtype=np.int32)
    if n:
        ids = np.arange(1, n + 1)
        areas = ndimage.sum(pixel_area_ha(mask), lab, index=ids)
        keep = ids[np.asarray(areas) >= min_ha]
        for new_id, old_id in enumerate(keep, start=1):
            out[lab == old_id] = new_id
    return xr.DataArray(out, coords=mask.coords, dims=mask.dims, name="label").rio.write_crs(_crs(mask))


def export_geojson(
    labels: xr.DataArray,
    d_hh: xr.DataArray,
    d_hv: xr.DataArray,
    stage: xr.DataArray,
    date: str,
    out_path: str,
) -> int:
    """Write polygons (EPSG:4326) with {id, date, area_ha, d_hh, d_hv, stage}; returns the number of features for `date`.

    d_hh / d_hv are cluster means. stage is "late" if at least half of the cluster's pixels are late-stage, else
    "early". If out_path already exists, features with the same date are replaced and other dates are kept
    (ids of new features continue after the highest kept id), so one file can hold several dates.
    """
    crs = _crs(labels)
    lab = labels.values.astype(np.int32)
    ids = np.arange(1, int(lab.max()) + 1)
    area = np.asarray(ndimage.sum(pixel_area_ha(labels), lab, index=ids)) if len(ids) else []
    mhh = np.atleast_1d(ndimage.mean(d_hh.values, lab, index=ids)) if len(ids) else []
    mhv = np.atleast_1d(ndimage.mean(d_hv.values, lab, index=ids)) if len(ids) else []
    late = np.atleast_1d(ndimage.mean((stage.values == STAGE_LATE).astype(float), lab, index=ids)) if len(ids) else []

    kept: list[dict] = []
    if os.path.exists(out_path):
        with open(out_path, encoding="utf-8") as f:
            kept = [ft for ft in json.load(f)["features"] if ft["properties"].get("date") != date]
    offset = max((ft["properties"]["id"] for ft in kept), default=0)

    to4326 = Transformer.from_crs(crs, 4326, always_xy=True).transform
    feats = []
    for geom, val in shapes(lab, mask=lab > 0, transform=labels.rio.transform(), connectivity=8):
        i = int(val) - 1
        feats.append({
            "type": "Feature",
            "geometry": mapping(shp_transform(to4326, shape(geom))),
            "properties": {
                "id": offset + int(val),
                "date": date,
                "area_ha": float(area[i]),
                "d_hh": float(mhh[i]),
                "d_hv": float(mhv[i]),
                "stage": "late" if late[i] >= 0.5 else "early",
            },
        })
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": kept + feats}, f)
    return len(feats)


def export_cog(change: xr.DataArray, out_path: str) -> None:
    """Write the float32 dB change as a Cloud-Optimized GeoTIFF in EPSG:4326, under 20 MB.

    Uses rasterio's GDAL "COG" driver via rioxarray (DEFLATE + floating-point predictor, NaN nodata). If the file is
    over 20 MB the raster is block-averaged by 2 and rewritten until it fits.
    """
    da = change.astype(np.float32).rio.reproject("EPSG:4326", nodata=np.nan, resampling=Resampling.bilinear)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    for _ in range(6):
        da.rio.to_raster(out_path, driver="COG", compress="DEFLATE", predictor=3, dtype="float32")
        if os.path.getsize(out_path) < MAX_COG_BYTES:
            return
        da = da.coarsen(y=2, x=2, boundary="trim").mean().rio.write_crs("EPSG:4326")
    raise RuntimeError(f"{out_path} still over 20 MB after downsampling")


def run(
    stack: xr.Dataset,
    date: str,
    hh_thresh: float | None,
    hv_thresh: float | None,
    min_ha: float,
    out_dir: str,
    forest_mask: xr.DataArray | None = None,
    average: Literal["linear", "db"] = "linear",
) -> int:
    """Full chain for one date on an in-memory stack; writes outputs to out_dir; returns number of detections."""
    d_hh, d_hv = change_maps(stack, date, average)
    mask, stage = apply_thresholds(d_hh, d_hv, hh_thresh, hv_thresh)
    if forest_mask is not None:
        mask = mask_nonforest(mask, forest_mask)
    labels = cluster_and_filter(mask, min_ha)
    n = export_geojson(labels, d_hh, d_hv, stage, date, os.path.join(out_dir, "detections.geojson"))
    export_cog(d_hh, os.path.join(out_dir, f"change_hh_{date}.tif"))
    export_cog(d_hv, os.path.join(out_dir, f"change_hv_{date}.tif"))
    return n


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--stack", required=True, help="data/stack_<tile>.nc")
    p.add_argument("--date", required=True, help="YYYY-MM-DD, must be in the stack")
    p.add_argument("--hh-thresh", type=float, required=True, help="HH rise threshold, positive dB (early stage)")
    p.add_argument("--hv-thresh", type=float, required=True, help="HV drop threshold, positive dB (late stage)")
    p.add_argument("--min-ha", type=float, required=True, help="minimum detection size in hectares")
    p.add_argument("--forest-mask", help="binary forest GeoTIFF (non-zero = forest); omit only for debugging")
    p.add_argument("--average", choices=["linear", "db"], default="linear", help="baseline averaging domain")
    p.add_argument("--out-dir", default="web/data")
    a = p.parse_args()

    stack = xr.open_dataset(a.stack)
    fm = None
    if a.forest_mask:
        fm = load_forest_mask(a.forest_mask, _with_crs(stack["hh_db"].isel(time=0), stack.attrs["crs"]))
    else:
        print("WARNING: no --forest-mask; non-forest changes will be reported as detections")
    n = run(stack, a.date, a.hh_thresh, a.hv_thresh, a.min_ha, a.out_dir, fm, a.average)
    print(f"{n} detections for {a.date} -> {a.out_dir}")


if __name__ == "__main__":
    main()
