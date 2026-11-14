"""Pipeline B: JJ-FAST-style change detection on the dB stack.

Reads:  data/stack_<tile>.nc  (CONTRACTS.md section 1).
Writes: web/data/detections.geojson (section 2) and
        web/data/change_hh_<date>.tif / change_hv_<date>.tif (section 3).

Thresholds and min size come from CLAUDE.md "Confirmed facts". Do not invent them.
"""
from __future__ import annotations

import argparse

import numpy as np
import xarray as xr


def baseline(stack: xr.Dataset, date: str) -> xr.Dataset:
    """Mean dB of all earlier same-track dates before `date`."""
    # TODO: average in dB or linear? decide and document in CLAUDE.md
    raise NotImplementedError


def change_maps(stack: xr.Dataset, date: str) -> tuple[xr.DataArray, xr.DataArray]:
    """Return (d_hh, d_hv): dB difference of `date` minus baseline."""
    raise NotImplementedError


def apply_thresholds(d_hh: xr.DataArray, d_hv: xr.DataArray, hh_thresh: float, hv_thresh: float) -> xr.DataArray:
    """Boolean mask of candidate clearing pixels (drops beyond thresholds, in dB)."""
    # TODO: decide HH-only / HV-only / both; 'early' vs 'late' stage rule
    raise NotImplementedError


def mask_nonforest(mask: xr.DataArray, forest_mask: xr.DataArray) -> xr.DataArray:
    """Keep only pixels that were forest in the baseline."""
    # TODO: choose and cite a forest mask source
    raise NotImplementedError


def cluster_and_filter(mask: xr.DataArray, min_ha: float) -> np.ndarray:
    """Label connected components and drop those smaller than min_ha. Returns label raster."""
    # TODO: scipy.ndimage.label / skimage.measure; pixel area from CLAUDE.md pixel spacing
    raise NotImplementedError


def export_geojson(labels: np.ndarray, d_hh: xr.DataArray, d_hv: xr.DataArray, date: str, out_path: str) -> None:
    """Vectorize labels to EPSG:4326 polygons with properties {id, date, area_ha, d_hh, d_hv, stage}."""
    raise NotImplementedError


def export_cog(change: xr.DataArray, out_path: str) -> None:
    """Write float32 dB change as a Cloud-Optimized GeoTIFF in EPSG:4326, under 20 MB."""
    # TODO: reproject, downsample if > 20 MB
    raise NotImplementedError


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--stack", required=True, help="data/stack_<tile>.nc")
    p.add_argument("--date", required=True, help="YYYY-MM-DD")
    p.add_argument("--hh-thresh", type=float, required=True, help="dB")
    p.add_argument("--hv-thresh", type=float, required=True, help="dB")
    p.add_argument("--min-ha", type=float, required=True)
    p.add_argument("--out-dir", default="web/data")
    p.parse_args()
    # TODO: open stack, run baseline -> change_maps -> thresholds -> mask -> cluster -> exports
    raise NotImplementedError


if __name__ == "__main__":
    main()
