"""Export per-date radar layers for the web map from a load stack.

Reads:  data/stack_<tile>.nc (CONTRACTS.md section 1: dims (time, y, x), hh_db / hv_db float32 dB, attrs["crs"], attrs["bbox_wsen"])
        and a binary forest-mask GeoTIFF on the same grid (1 = forest; pipeline/load/forest_mask.py).
Writes: <out-dir>/<id>/composite_<date>.tif   uint8 RGB: R = HH, G = HV, B = HH - HV (dB ratio)
        <out-dir>/<id>/hh_<date>.tif, hv_<date>.tif   uint8 grayscale
        and merges an entry for <id> into <out-dir>/locations.json (with the dB stretch used).

All outputs are Cloud-Optimized GeoTIFFs in EPSG:3857 with overviews and compression. EPSG:3857 (not 4326) because the
web app reads them with maplibre-cog-protocol, which does not reproject and rejects any other CRS (its README,
"COG generation tips"). Tiling scheme GoogleMapsCompatible, 256 px blocks, as that README recommends.

One fixed stretch per channel for ALL dates: the lo/hi percentiles of the stable-forest pixels (forest mask) pooled over
every exported date, so brightness is comparable between dates. Pixel value 0 = no data (transparent); valid values are 1..255.
Stack coordinates are taken as pixel centres (the rioxarray convention the rest of the pipeline uses).
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from typing import Iterable

import numpy as np
import rasterio
import rasterio.shutil
import rioxarray
import xarray as xr

CHANNELS = ("hh", "hv", "ratio")  # ratio = HH - HV in dB


def forest_mask_on_grid(path: str, stack: xr.Dataset) -> np.ndarray:
    """Boolean forest mask; refuses a mask that is not on exactly the stack grid."""
    m = rioxarray.open_rasterio(path).squeeze(drop=True)
    if m.shape != (stack.sizes["y"], stack.sizes["x"]):
        raise SystemExit(f"forest mask shape {m.shape} != stack grid {(stack.sizes['y'], stack.sizes['x'])}")
    if not (np.allclose(m.x.values, stack.x.values) and np.allclose(m.y.values, stack.y.values)):
        raise SystemExit("forest mask coordinates differ from the stack's x/y; rebuild it on the stack grid")
    return m.values == 1


def channel(stack: xr.Dataset, name: str) -> np.ndarray:
    """(time, y, x) float32 dB for 'hh', 'hv' or 'ratio' (HH - HV)."""
    hh, hv = stack["hh_db"].values, stack["hv_db"].values
    return {"hh": hh, "hv": hv, "ratio": hh - hv}[name]


def fixed_stretch(stack: xr.Dataset, forest: np.ndarray, lo_pct: float, hi_pct: float) -> dict:
    """lo/hi dB per channel from stable-forest pixels pooled over all dates in `stack`."""
    out = {}
    for name in CHANNELS:
        v = channel(stack, name)[:, forest]
        v = v[np.isfinite(v)]
        if v.size == 0:
            raise SystemExit("no finite stable-forest pixels; cannot choose a stretch")
        lo, hi = np.percentile(v, [lo_pct, hi_pct])
        out[name] = {"lo": round(float(lo), 2), "hi": round(float(hi), 2), "n_pixels": int(v.size)}
    return out


def to_uint8(db: np.ndarray, lo: float, hi: float) -> np.ndarray:
    """Linear stretch lo..hi dB -> 1..255; non-finite -> 0 (no data)."""
    ok = np.isfinite(db)
    scaled = np.clip((np.where(ok, db, lo) - lo) / (hi - lo), 0.0, 1.0)
    return np.where(ok, 1 + np.rint(scaled * 254), 0).astype(np.uint8)


def write_cog(bands: np.ndarray, transform, crs: str, out_path: str, compress: str, quality: int) -> int:
    """Write (n, y, x) uint8 (0 = nodata) as an EPSG:3857 COG with overviews; returns file size in bytes.

    Lossless (DEFLATE, ZSTD, ...): nodata 0 is declared on the source and carried to the output.
    JPEG (lossy, much smaller for speckled radar; gray layers are stored as 3 identical bands): JPEG artifacts would leave a fringe around a nodata value, so the
    validity goes into an alpha band instead, which GDAL stores as a lossless 1-bit mask (maplibre-cog-protocol README,
    "COG generation tips"). Pixels that are valid but dark are clamped to >= 1 either way.
    """
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    jpeg = compress.upper() == "JPEG"
    if jpeg and bands.shape[0] == 1:
        # GDAL's COG driver writes a 1-band + alpha JPEG source as 3-band YCbCr and loses the mask, so replicate the
        # gray band to R = G = B (identical chroma costs almost nothing) and keep the mask working.
        bands = np.repeat(bands, 3, axis=0)
    n, h, w = bands.shape
    with tempfile.TemporaryDirectory() as tmp:
        src_path = os.path.join(tmp, "src.tif")
        if jpeg:
            alpha = ((bands != 0).all(axis=0) * 255).astype(np.uint8)
            data, count, nodata = np.concatenate([bands, alpha[None]]), n + 1, None
        else:
            data, count, nodata = bands, n, 0
        with rasterio.open(src_path, "w", driver="GTiff", height=h, width=w, count=count, dtype="uint8",
                           crs=crs, transform=transform, nodata=nodata) as dst:
            dst.write(data)
            if jpeg:
                dst.colorinterp = (*dst.colorinterp[:n], rasterio.enums.ColorInterp.alpha)
        opts = dict(TILING_SCHEME="GoogleMapsCompatible", BLOCKSIZE=256, COMPRESS=compress.upper(),
                    RESAMPLING="BILINEAR", OVERVIEW_RESAMPLING="AVERAGE")
        if jpeg:
            opts["QUALITY"] = quality
        rasterio.shutil.copy(src_path, out_path, driver="COG", **opts)
    return os.path.getsize(out_path)


def export(stack: xr.Dataset, forest: np.ndarray, dates: Iterable[str], out_dir: str, compress: str, quality: int,
           lo_pct: float, hi_pct: float) -> tuple[dict, dict]:
    """Write all layers for `dates`; returns (stretch, {file: bytes})."""
    stretch = fixed_stretch(stack, forest, lo_pct, hi_pct)
    template = stack["hh_db"].isel(time=0).rio.write_crs(stack.attrs["crs"])
    transform, crs = template.rio.transform(), stack.attrs["crs"]
    sizes = {}
    for d in dates:
        t = np.datetime64(d, "ns")
        i = int(np.flatnonzero(stack["time"].values == t)[0])
        u = {n: to_uint8(channel(stack, n)[i], stretch[n]["lo"], stretch[n]["hi"]) for n in CHANNELS}
        comp = np.stack([u["hh"], u["hv"], u["ratio"]])
        comp[:, (comp == 0).any(axis=0)] = 0  # any channel invalid -> whole pixel transparent
        for name, arr in (("composite", comp), ("hh", u["hh"][None]), ("hv", u["hv"][None])):
            p = os.path.join(out_dir, f"{name}_{d}.tif")
            sizes[p] = write_cog(arr, transform, crs, p, compress, quality)
    return stretch, sizes


def merge_locations(path: str, entry: dict) -> None:
    """Insert/replace the entry with the same id in locations.json (other locations kept)."""
    data = {"locations": []}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    data["locations"] = [e for e in data["locations"] if e["id"] != entry["id"]] + [entry]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--stack", required=True)
    p.add_argument("--forest-mask", required=True, help="binary GeoTIFF on the stack grid; defines the stable forest used for the stretch")
    p.add_argument("--id", required=True, help="location id, e.g. spara")
    p.add_argument("--name", required=True)
    p.add_argument("--notes", default="")
    p.add_argument("--dates", nargs="+", help="YYYY-MM-DD subset to export (default: every date in the stack)")
    p.add_argument("--out-dir", default="web/data", help="data folder; layers go to <out-dir>/<id>/")
    p.add_argument("--compress", default="DEFLATE", help="COG compression: DEFLATE/ZSTD (lossless) or JPEG (lossy, smallest)")
    p.add_argument("--quality", type=int, default=85, help="JPEG quality 1-100 (only with --compress JPEG)")
    p.add_argument("--low-pct", type=float, default=2.0)
    p.add_argument("--high-pct", type=float, default=98.0)
    a = p.parse_args()

    stack = xr.open_dataset(a.stack)
    have = [str(t)[:10] for t in stack["time"].values]
    dates = a.dates or have
    missing = [d for d in dates if d not in have]
    if missing:
        raise SystemExit(f"dates not in the stack: {missing}; stack has {have}")
    dates = sorted(dates)
    forest = forest_mask_on_grid(a.forest_mask, stack)
    # Stretch from the exported dates only, so excluded (bad) dates cannot influence it.
    sub = stack.sel(time=[np.datetime64(d, "ns") for d in dates])
    loc_dir = os.path.join(a.out_dir, a.id)
    stretch, sizes = export(sub, forest, dates, loc_dir, a.compress, a.quality, a.low_pct, a.high_pct)

    w, s, e, n = (float(v) for v in stack.attrs["bbox_wsen"])
    entry = {
        "id": a.id, "name": a.name, "bbox": [w, s, e, n], "center": [round((w + e) / 2, 4), round((s + n) / 2, 4)],
        "dates": dates, "crs": "EPSG:3857",
        "layers": {k: f"data/{a.id}/{k}_{{date}}.tif" for k in ("composite", "hh", "hv")},
        "stretch": {**{k: {"lo": v["lo"], "hi": v["hi"], "unit": "dB"} for k, v in stretch.items()},
                    "basis": f"stable-forest pixels (forest mask), all exported dates, percentiles {a.low_pct}-{a.high_pct}",
                    "ratio_is": "HH - HV in dB", "nodata_value": 0},
        "notes": a.notes,
    }
    merge_locations(os.path.join(a.out_dir, "locations.json"), entry)
    total = sum(sizes.values())
    stack.close()
    for f, b in sizes.items():
        print(f"{b / 1e6:7.2f} MB  {f}")
    print(f"{total / 1e6:7.2f} MB  total for {a.id} ({len(sizes)} files)")
    print("stretch:", json.dumps(stretch))


if __name__ == "__main__":
    main()
