"""Pipeline B: JJ-FAST-style change detection on the dB stack.

Reads:  data/stack_<tile>.nc  (CONTRACTS.md section 1: dims (time, y, x), hh_db / hv_db float32 dB,
        CRS in attrs["crs"], time as datetime64; one track/frame only, so "same-track" is guaranteed by load).
Writes: web/data/detections.geojson (section 2; features for the same date are replaced, others kept;
        optional extra properties first_hh_date / first_hv_date), web/data/change_hh_<date>.tif /
        change_hv_<date>.tif (section 3), web/data/summary.json (section 6) and a detect log
        data/detect_log_<tile>.json (split, tuning sweep, normalization offsets, parameters; gitignored record).

Order per date: multilook (linear power) -> change vs baseline -> stable-forest normalization -> thresholds ->
forest mask -> clusters >= min size. Exported d_hh / d_hv (COGs and geojson) are the raw dB change (date minus
baseline, as CONTRACTS.md section 3 says); the normalization offsets are recorded in summary.json.

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
from dataclasses import dataclass
from typing import Literal

import numpy as np
import xarray as xr
import rioxarray  # noqa: F401  (registers the .rio accessor)
from pyproj import CRS, Transformer
from rasterio.enums import Resampling
from rasterio.features import shapes
from scipy import ndimage
from shapely.geometry import box, mapping, shape
from shapely.ops import transform as shp_transform

STAGE_NONE, STAGE_EARLY, STAGE_LATE = 0, 1, 2
STAGE_NAMES = {STAGE_EARLY: "early", STAGE_LATE: "late"}
MAX_COG_BYTES = 20 * 1024 * 1024
FIRST_FIRE_FRAC = 0.5  # same "at least half the cluster" rule as the stage label

BBox = tuple[float, float, float, float]  # (west, south, east, north), EPSG:4326


def _crs(da: xr.DataArray | xr.Dataset) -> CRS:
    crs = da.rio.crs
    if crs is None:
        raise ValueError("no CRS on data; the stack must carry attrs['crs'] (CONTRACTS.md section 1)")
    return CRS.from_user_input(crs)


def _with_crs(da: xr.DataArray, crs: str) -> xr.DataArray:
    return da.rio.write_crs(crs)


def multilook(stack: xr.Dataset, n: int = 5) -> xr.Dataset:
    """Average non-overlapping n x n pixel blocks of every date, in linear power, then convert back to dB.

    Applied before the change maps and thresholds, to reduce speckle. Averaging is in linear power (the domain
    speckle averages in); NaN pixels are skipped, edge rows/cols that do not fill a block are dropped. The new x/y
    coordinates are the block centres, so pixel_area_ha() sees the real coarser spacing (n*dx by n*dy).
    n=1 returns the stack unchanged (use it if pipeline/load already multilooked).
    """
    if n < 1:
        raise ValueError("multilook n must be >= 1")
    if n == 1:
        return stack
    out = {}
    for v in ("hh_db", "hv_db"):
        # xarray 2026.9 coarsen().mean() rejects an explicit skipna; its default already skips NaN for floats
        lin = (10.0 ** (stack[v] / 10.0)).coarsen(y=n, x=n, boundary="trim").mean()
        out[v] = (10.0 * np.log10(lin)).astype(np.float32)
    return xr.Dataset(out, attrs=stack.attrs)


def normalize_stable(change: xr.DataArray, stable_mask: xr.DataArray) -> tuple[xr.DataArray, float, int]:
    """Stable-forest normalization of one change map (one date, one polarization).

        d_norm(p) = d(p) - median{ d(q) : q in S, d(q) finite }

    S is the stable-forest boolean mask on the same grid. The median over S estimates the scene-wide shift
    that is not clearing (e.g. wetter or drier canopy, calibration), and is robust to the few cleared pixels
    inside S. Returns (d_norm, offset_db, n_pixels_used).
    """
    s = np.asarray(stable_mask.values, dtype=bool)
    if s.shape != change.shape:
        raise ValueError(f"stable mask shape {s.shape} != change map {change.shape}; reproject it first")
    vals = change.values[s & np.isfinite(change.values)]
    if vals.size == 0:
        raise ValueError("stable mask has no finite pixels; cannot normalize")
    off = float(np.median(vals))
    return (change - off).astype(np.float32).rename(change.name), off, int(vals.size)


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


def pixel_spacing(da: xr.DataArray) -> dict:
    """Real grid spacing of `da` (after any multilook) and its CRS unit, for summary.json."""
    dx, dy = (abs(float(v)) for v in da.rio.resolution())
    return {"x": dx, "y": dy, "unit": _crs(da).axis_info[0].unit_name}


def bbox_mask(template: xr.DataArray, bbox: BBox) -> xr.DataArray:
    """True where the pixel centre lies inside bbox (west, south, east, north in EPSG:4326), on template's grid."""
    w, s, e, n = bbox
    xx, yy = np.meshgrid(template["x"].values, template["y"].values)
    lon, lat = Transformer.from_crs(_crs(template), 4326, always_xy=True).transform(xx, yy)
    inside = (lon >= w) & (lon <= e) & (lat >= s) & (lat <= n)
    return xr.DataArray(inside, coords={"y": template["y"].values, "x": template["x"].values}, dims=("y", "x"))


@dataclass(frozen=True)
class Split:
    """Tune/holdout split, by area (two EPSG:4326 boxes) or by dates (two date lists).

    Thresholds may only be explored on `tune` (sweep_thresholds); `holdout` is kept for validation/score.py.
    """
    by: Literal["bbox", "dates"]
    tune: tuple
    holdout: tuple

    def to_dict(self) -> dict:
        return {"by": self.by, "tune": list(self.tune), "holdout": list(self.holdout)}


def make_split(
    tune_bbox: BBox | None = None,
    holdout_bbox: BBox | None = None,
    tune_dates: list[str] | None = None,
    holdout_dates: list[str] | None = None,
) -> Split | None:
    """Build and check a split; None if nothing is given. Both boxes or both date lists, never a mix.

    Boxes need west < east and south < north and must not overlap (shared edges are fine). Date lists must be
    non-empty, YYYY-MM-DD, and disjoint.
    """
    by_box = tune_bbox is not None or holdout_bbox is not None
    by_dates = bool(tune_dates) or bool(holdout_dates)
    if by_box and by_dates:
        raise ValueError("split by bbox or by dates, not both")
    if by_box:
        if tune_bbox is None or holdout_bbox is None:
            raise ValueError("give both --tune-bbox and --holdout-bbox")
        boxes = []
        for b in (tune_bbox, holdout_bbox):
            w, s, e, n = (float(v) for v in b)
            if not (w < e and s < n):
                raise ValueError(f"invalid bbox {list(b)}: need west < east and south < north")
            boxes.append((w, s, e, n))
        if box(*boxes[0]).intersection(box(*boxes[1])).area > 0:
            raise ValueError("tune and holdout boxes overlap")
        return Split("bbox", boxes[0], boxes[1])
    if by_dates:
        if not tune_dates or not holdout_dates:
            raise ValueError("give both --tune-dates and --holdout-dates")
        t = tuple(sorted({str(np.datetime64(d, "D")) for d in tune_dates}))
        h = tuple(sorted({str(np.datetime64(d, "D")) for d in holdout_dates}))
        if set(t) & set(h):
            raise ValueError(f"dates in both tune and holdout: {sorted(set(t) & set(h))}")
        return Split("dates", t, h)
    return None


def _resolve_stable(stable_mask, forest_mask):
    """stable_mask="forest" (the default) means: use the forest mask. None disables normalization."""
    if isinstance(stable_mask, str) and stable_mask == "forest":
        return forest_mask
    return stable_mask


def _date_changes(stack: xr.Dataset, date: str, average: str, stable_mask: xr.DataArray | None):
    """(d_hh, d_hv) raw, (n_hh, n_hv) normalized, and the normalization record, for one date."""
    d_hh, d_hv = change_maps(stack, date, average)
    if stable_mask is None:
        rec = {"hh_offset_db": None, "hv_offset_db": None, "n_stable_px_hh": 0, "n_stable_px_hv": 0}
        return d_hh, d_hv, d_hh, d_hv, rec
    n_hh, o_hh, k_hh = normalize_stable(d_hh, stable_mask)
    n_hv, o_hv, k_hv = normalize_stable(d_hv, stable_mask)
    rec = {"hh_offset_db": o_hh, "hv_offset_db": o_hv, "n_stable_px_hh": k_hh, "n_stable_px_hv": k_hv}
    return d_hh, d_hv, n_hh, n_hv, rec


def _candidates(n_hh, n_hv, hh_thresh, hv_thresh, forest_mask=None, region=None):
    mask, stage = apply_thresholds(n_hh, n_hv, hh_thresh, hv_thresh)
    if forest_mask is not None:
        mask = mask_nonforest(mask, forest_mask)
    if region is not None:
        mask = mask & xr.DataArray(np.asarray(region.values, bool), coords=mask.coords, dims=mask.dims)
    return mask, stage


def _hits(n_hh, n_hv, hh_thresh, hv_thresh) -> tuple[np.ndarray, np.ndarray]:
    """Per-channel firing (same rule as apply_thresholds), kept separate so "both fired" is not lost."""
    hh = n_hh.values >= hh_thresh if hh_thresh is not None else np.zeros(n_hh.shape, bool)
    hv = n_hv.values <= -hv_thresh if hv_thresh is not None else np.zeros(n_hv.shape, bool)
    return hh, hv


def first_fire_dates(
    labels: xr.DataArray,
    hits: dict[str, tuple[np.ndarray, np.ndarray]],
    frac: float = FIRST_FIRE_FRAC,
) -> list[tuple[str | None, str | None]]:
    """Per detection label 1..n: (first_hh_date, first_hv_date).

    Each is the earliest date in `hits` on which that channel's threshold fired on at least `frac` of the
    detection's pixels, or None if it never did. `hits` maps "YYYY-MM-DD" -> (hh_hit, hv_hit) boolean arrays on
    the labels grid, made with the same multilook / normalization / thresholds as the detection; pass only dates
    up to and including the detection date. Each date's change is against the mean of all dates before it.
    """
    lab = labels.values.astype(np.int32)
    n = int(lab.max())
    ids = np.arange(1, n + 1)
    first_hh: list[str | None] = [None] * n
    first_hv: list[str | None] = [None] * n
    for d in sorted(hits):
        if n == 0:
            break
        hh, hv = hits[d]
        fh = np.atleast_1d(ndimage.mean(hh.astype(float), lab, index=ids))
        fv = np.atleast_1d(ndimage.mean(hv.astype(float), lab, index=ids))
        for i in range(n):
            if first_hh[i] is None and fh[i] >= frac:
                first_hh[i] = d
            if first_hv[i] is None and fv[i] >= frac:
                first_hv[i] = d
    return list(zip(first_hh, first_hv))


def sweep_thresholds(
    stack: xr.Dataset,
    split: Split,
    hh_grid: list[float],
    hv_grid: list[float],
    min_ha: float,
    dates: list[str] | None = None,
    forest_mask: xr.DataArray | None = None,
    stable_mask: xr.DataArray | None | Literal["forest"] = "forest",
    average: Literal["linear", "db"] = "linear",
) -> list[dict]:
    """Detection counts for every (hh_thresh, hv_thresh) on the grid, on the TUNE part of `split` only.

    Records counts and areas per setting, never a score, and chooses nothing: a person reads the table and picks
    thresholds, which therefore never depend on the holdout.
      - split by dates: runs on split.tune (`dates`, if given, must be a subset of it, else ValueError)
      - split by bbox:  runs on `dates` (required) and counts only pixels whose centre is inside split.tune
    Same chain as run(): normalization, thresholds, forest mask, clusters >= min_ha.
    """
    if split is None:
        raise ValueError("sweep_thresholds needs a tune/holdout split")
    region = None
    if split.by == "dates":
        use = list(split.tune) if dates is None else [str(np.datetime64(d, "D")) for d in dates]
        leak = set(use) - set(split.tune)
        if leak:
            raise ValueError(f"refusing to sweep on non-tune dates {sorted(leak)}")
    else:
        if not dates:
            raise ValueError("a bbox split sweep needs the dates to run on")
        use = list(dates)
        region = bbox_mask(_with_crs(stack["hh_db"].isel(time=0), stack.attrs["crs"]), split.tune)
    stable = _resolve_stable(stable_mask, forest_mask)
    changes = {d: _date_changes(stack, d, average, stable)[2:4] for d in use}
    rows = []
    for hh in hh_grid:
        for hv in hv_grid:
            per_date, area = {}, 0.0
            for d, (n_hh, n_hv) in changes.items():
                mask, _ = _candidates(n_hh, n_hv, hh, hv, forest_mask, region)
                lab = cluster_and_filter(mask, min_ha)
                per_date[d] = int(lab.values.max())
                area += float(pixel_area_ha(lab)[lab.values > 0].sum())
            rows.append({"hh_thresh": hh, "hv_thresh": hv, "min_ha": min_ha,
                         "n_detections": sum(per_date.values()), "area_ha": area, "per_date": per_date})
    return rows


def export_geojson(
    labels: xr.DataArray,
    d_hh: xr.DataArray,
    d_hv: xr.DataArray,
    stage: xr.DataArray,
    date: str,
    out_path: str,
    first_dates: list[tuple[str | None, str | None]] | None = None,
) -> int:
    """Write polygons (EPSG:4326) with {id, date, area_ha, d_hh, d_hv, stage}; returns the number of features for `date`.

    d_hh / d_hv are cluster means. stage is "late" if at least half of the cluster's pixels are late-stage, else
    "early". If out_path already exists, features with the same date are replaced and other dates are kept
    (ids of new features continue after the highest kept id), so one file can hold several dates.
    first_dates (optional, one (first_hh_date, first_hv_date) per label 1..n, see first_fire_dates()) adds the
    optional nullable properties first_hh_date / first_hv_date.
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
        props = {
            "id": offset + int(val),
            "date": date,
            "area_ha": float(area[i]),
            "d_hh": float(mhh[i]),
            "d_hv": float(mhv[i]),
            "stage": "late" if late[i] >= 0.5 else "early",
        }
        if first_dates is not None:
            props["first_hh_date"], props["first_hv_date"] = first_dates[i]
        feats.append({"type": "Feature", "geometry": mapping(shp_transform(to4326, shape(geom))), "properties": props})
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
    stable_mask: xr.DataArray | None | Literal["forest"] = "forest",
) -> dict:
    """Full chain for one date on an in-memory (already multilooked) stack; writes outputs to out_dir.

    stable_mask defaults to the forest mask ("forest"); None skips normalization. Returns the per-date record
    used in summary.json: counts, areas, baseline dates and normalization offsets.
    """
    date = str(np.datetime64(date, "D"))
    stable = _resolve_stable(stable_mask, forest_mask)
    all_dates = [str(t) for t in stack["time"].values.astype("datetime64[D]")]
    if date not in all_dates:
        raise KeyError(f"{date} is not a date in the stack")
    hits, cur = {}, None
    for d in all_dates[1:]:  # dates that have a baseline, up to the detection date
        if d > date:
            break
        d_hh, d_hv, n_hh, n_hv, norm = _date_changes(stack, d, average, stable)
        hits[d] = _hits(n_hh, n_hv, hh_thresh, hv_thresh)
        if d == date:
            cur = (d_hh, d_hv, n_hh, n_hv, norm)
    if cur is None:
        raise ValueError(f"{date} is the first date in the stack; it has no baseline")
    d_hh, d_hv, n_hh, n_hv, norm = cur
    mask, stage = _candidates(n_hh, n_hv, hh_thresh, hv_thresh, forest_mask)
    labels = cluster_and_filter(mask, min_ha)
    first = first_fire_dates(labels, hits)
    n = export_geojson(labels, d_hh, d_hv, stage, date, os.path.join(out_dir, "detections.geojson"), first)
    export_cog(d_hh, os.path.join(out_dir, f"change_hh_{date}.tif"))
    export_cog(d_hv, os.path.join(out_dir, f"change_hv_{date}.tif"))

    lab = labels.values
    ids = np.arange(1, n + 1)
    area = np.atleast_1d(ndimage.sum(pixel_area_ha(labels), lab, index=ids)) if n else np.array([])
    late = np.atleast_1d(ndimage.mean((stage.values == STAGE_LATE).astype(float), lab, index=ids)) if n else np.array([])
    return {
        "n_detections": n,
        "total_area_ha": float(area.sum()),
        "early_ha": float(area[late < 0.5].sum()),  # same per-cluster stage rule as export_geojson
        "late_ha": float(area[late >= 0.5].sum()),
        "baseline_dates": [d for d in all_dates if d < date],
        "normalization": norm,
    }


SUMMARY_ROW_KEYS = ("date", "n_detections", "total_area_ha", "early_ha", "late_ha")


def merge_summary(old: dict | None, dates: list[str], rows: list[dict], tuning: dict | None) -> dict:
    """summary.json content per CONTRACTS.md section 6: {"dates", "per_date", "tuning"}.

    `dates` = every stack date the detections used (baseline and detection dates), merged with the stored ones.
    per_date rows are replaced by date and other dates kept (like the geojson), sorted by date. `tuning` is
    {"split": <description>, "hh_thresh", "hv_thresh"} when the thresholds came from a tune-set sweep, else None.
    """
    by_date = {r["date"]: r for r in (old or {}).get("per_date") or []}
    by_date.update({r["date"]: {k: r[k] for k in SUMMARY_ROW_KEYS} for r in rows})
    all_dates = sorted(set((old or {}).get("dates") or []) | set(dates) | set(by_date))
    return {"dates": all_dates, "per_date": [by_date[d] for d in sorted(by_date)], "tuning": tuning}


def export_summary(out_path: str, dates: list[str], rows: list[dict], tuning: dict | None) -> dict:
    """Write web/data/summary.json (CONTRACTS.md section 6), merged with any existing file by date."""
    old = None
    if os.path.exists(out_path):
        with open(out_path, encoding="utf-8") as f:
            old = json.load(f)
    summary = merge_summary(old, dates, rows, tuning)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=1)
    return summary


def describe_split(split: Split) -> str:
    """Human-readable split for summary.json tuning.split, e.g. "tune: dates 2025-11-02; holdout: dates 2025-11-14"."""
    if split.by == "dates":
        return f"tune: dates {', '.join(split.tune)}; holdout: dates {', '.join(split.holdout)}"
    fmt = lambda b: "bbox W,S,E,N " + ",".join(f"{v:g}" for v in b)  # noqa: E731
    return f"tune: {fmt(split.tune)}; holdout: {fmt(split.holdout)}"


def tuning_entry(log: dict, split: Split | None, hh_thresh: float, hv_thresh: float) -> dict | None:
    """summary.json "tuning": only if the detect log holds a tune-set sweep made under this same split."""
    sweep = (log or {}).get("tuning")
    if split is None or not sweep or sweep.get("split") != split.to_dict():
        return None
    return {"split": describe_split(split), "hh_thresh": hh_thresh, "hv_thresh": hv_thresh}


def merge_log(old: dict | None, new: dict) -> dict:
    """Detect log (data/detect_log_<tile>.json): the full record behind summary.json.

    Top-level keys are overwritten; "dates" entries are replaced per date, other dates kept. A stored "tuning"
    sweep made under a different split is dropped, since it no longer describes the tune set.
    """
    out = dict(old or {})
    dates = dict(out.get("dates") or {})
    dates.update(new.get("dates") or {})
    out.update({k: v for k, v in new.items() if k != "dates"})
    out["dates"] = dates
    if "tuning" not in new and out.get("tuning") and out["tuning"].get("split") != out.get("split"):
        out["tuning"] = None
    out.setdefault("tuning", None)
    return out


def export_log(path: str, new: dict) -> dict:
    old = None
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            old = json.load(f)
    log = merge_log(old, new)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=1)
    return log


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--stack", required=True, help="data/stack_<tile>.nc")
    p.add_argument("--date", nargs="+", help="YYYY-MM-DD ..., each in the stack (not needed to sweep a date split)")
    p.add_argument("--hh-thresh", type=float, help="HH rise threshold, positive dB (early stage)")
    p.add_argument("--hv-thresh", type=float, help="HV drop threshold, positive dB (late stage)")
    p.add_argument("--min-ha", type=float, required=True, help="minimum detection size in hectares")
    p.add_argument("--forest-mask", help="binary forest GeoTIFF (non-zero = forest); required with --final")
    p.add_argument("--stable-mask", help="binary stable-forest GeoTIFF for normalization (default: the forest mask)")
    p.add_argument("--average", choices=["linear", "db"], default="linear", help="baseline averaging domain")
    p.add_argument("--multilook", type=int, default=5, help="n x n looks in linear power before thresholding; 1 = off")
    p.add_argument("--tune-bbox", type=float, nargs=4, metavar=("W", "S", "E", "N"), help="EPSG:4326")
    p.add_argument("--holdout-bbox", type=float, nargs=4, metavar=("W", "S", "E", "N"), help="EPSG:4326")
    p.add_argument("--tune-dates", nargs="+", help="YYYY-MM-DD ...")
    p.add_argument("--holdout-dates", nargs="+", help="YYYY-MM-DD ...")
    p.add_argument("--sweep-hh", type=float, nargs="+", help="HH grid: sweep the tune set instead of detecting")
    p.add_argument("--sweep-hv", type=float, nargs="+", help="HV grid: sweep the tune set instead of detecting")
    p.add_argument("--final", action="store_true", help="submission run; requires --forest-mask")
    p.add_argument("--out-dir", default="web/data")
    p.add_argument("--log", help="detect log JSON (default: data/detect_log_<tile>.json next to the stack)")
    return p


def check_args(a: argparse.Namespace, p: argparse.ArgumentParser) -> Split | None:
    """Cross-argument rules argparse cannot express; exits via p.error(). Returns the split (or None)."""
    if a.final and not a.forest_mask:
        p.error("--final requires --forest-mask")
    if a.multilook < 1:
        p.error("--multilook must be >= 1")
    try:
        split = make_split(a.tune_bbox, a.holdout_bbox, a.tune_dates, a.holdout_dates)
    except ValueError as e:
        p.error(str(e))
    if a.sweep_hh is not None or a.sweep_hv is not None:
        if not a.sweep_hh or not a.sweep_hv:
            p.error("give both --sweep-hh and --sweep-hv")
        if split is None:
            p.error("--sweep-hh/--sweep-hv need a split (--tune-bbox/--holdout-bbox or --tune-dates/--holdout-dates)")
        if split.by == "bbox" and not a.date:
            p.error("sweeping a bbox split needs --date")
    else:
        if a.hh_thresh is None or a.hv_thresh is None:
            p.error("--hh-thresh and --hv-thresh are required unless sweeping")
        if not a.date:
            p.error("--date is required unless sweeping a date split")
    return split


def main() -> None:
    p = build_parser()
    a = p.parse_args()
    split = check_args(a, p)

    stack = multilook(xr.open_dataset(a.stack), a.multilook)
    tmpl = _with_crs(stack["hh_db"].isel(time=0), stack.attrs["crs"])
    fm = load_forest_mask(a.forest_mask, tmpl) if a.forest_mask else None
    if fm is None:
        print("WARNING: no --forest-mask; non-forest changes will be reported as detections")
    if a.stable_mask:
        sm, sm_name = load_forest_mask(a.stable_mask, tmpl), a.stable_mask
    else:
        sm, sm_name = fm, ("forest_mask" if fm is not None else None)
        if sm is None:
            print("WARNING: no --stable-mask or --forest-mask; stable-forest normalization skipped")
    tile = stack.attrs.get("tile")
    log_path = a.log or os.path.join(os.path.dirname(os.path.abspath(a.stack)),
                                     f"detect_log_{tile}.json" if tile else "detect_log.json")
    top = {"tile": tile, "crs": str(stack.attrs["crs"]), "pixel_spacing": pixel_spacing(tmpl),
           "multilook": a.multilook, "split": split.to_dict() if split else None}
    params = {"min_ha": a.min_ha, "average": a.average, "multilook": a.multilook,
              "forest_mask": a.forest_mask, "stable_mask": sm_name}

    if a.sweep_hh:
        rows = sweep_thresholds(stack, split, a.sweep_hh, a.sweep_hv, a.min_ha, a.date, fm, sm, a.average)
        tuning = {"on": "tune", "split": top["split"], "dates": sorted(rows[0]["per_date"]) if rows else [],
                  **params, "results": rows,
                  "note": "detection counts per setting on the tune set only; not scores; thresholds are chosen "
                          "by a person from this table, never on the holdout"}
        export_log(log_path, {**top, "tuning": tuning})
        print("hh_thresh  hv_thresh  n_detections  area_ha   (tune set only)")
        for r in rows:
            print(f"{r['hh_thresh']:9.2f}  {r['hv_thresh']:9.2f}  {r['n_detections']:12d}  {r['area_ha']:.2f}")
        print(f"-> {log_path} (tuning)")
        return

    dates, rows = {}, []
    for d in a.date:
        info = run(stack, d, a.hh_thresh, a.hv_thresh, a.min_ha, a.out_dir, fm, a.average, sm)
        d = str(np.datetime64(d, "D"))
        part = None
        if split is not None and split.by == "dates":
            part = "tune" if d in split.tune else "holdout" if d in split.holdout else None
        dates[d] = {**info, **params, "hh_thresh": a.hh_thresh, "hv_thresh": a.hv_thresh,
                    "final": a.final, "split_part": part}
        rows.append({"date": d, **info})
        print(f"{info['n_detections']} detections for {d} -> {a.out_dir}")
    log = export_log(log_path, {**top, "final": a.final, "dates": dates})
    tuning = tuning_entry(log, split, a.hh_thresh, a.hv_thresh)
    if tuning is None:
        print("NOTE: no tune-set sweep on record for this split; summary.json tuning = null")
    used = sorted({b for r in rows for b in r["baseline_dates"]} | {r["date"] for r in rows})
    export_summary(os.path.join(a.out_dir, "summary.json"), used, rows, tuning)
    print(f"-> {os.path.join(a.out_dir, 'summary.json')}, log {log_path}")


if __name__ == "__main__":
    main()
