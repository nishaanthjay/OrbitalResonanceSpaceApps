"""First-switch map (descriptive only: no new score, no new threshold).

For each lost block (validation/PREREG_scale.md rule via scale.lost_rule, unchanged; blocks valid on all 9 dates), the
first pass after 07-20 (08-13 onward) on which it is non-forest and stays non-forest through 10-12. For a lost block
this is 08-13, 08-25, 09-06, 09-18 or 09-30 (the rule needs 09-30 and 10-12 non-forest).

Writes (in web/data/explore/big/):
- first_switch.webp: lossless RGBA on the EPSG:3857 grid of big.json (nearest), coloured by date, transparent elsewhere;
- big.json: adds "first_switch" (legend date -> colour, file, definition, block counts); nothing else is changed;
- lost.geojson: adds first_switch_date to every patch = the earliest first-switch date over the patch's blocks.

  python validation/first_switch.py --stack data/stack_big_t2f174.nc --big-dir web/data/explore/big
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import xarray as xr
from PIL import Image
from rasterio.transform import Affine, from_origin
from rasterio.warp import Resampling, reproject
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scale  # noqa: E402

FIRST_AFTER = 3  # index of 08-13, the first pass after 07-20
PALETTE = ["#fde047", "#fb923c", "#ef4444", "#b91c1c", "#5b0e4a"]  # same ramp as the Hansen loss overlay


def first_switch(forest: np.ndarray, first: int = FIRST_AFTER) -> np.ndarray:
    """Index of the earliest pass k >= first with non-forest on every pass k..last; -1 if none."""
    stay = np.flip(np.logical_and.accumulate(np.flip(~forest, axis=0), axis=0), axis=0)
    out = np.full(forest.shape[1:], -1, int)
    for k in range(forest.shape[0] - 1, first - 1, -1):
        out[stay[k]] = k
    return out


def hex_rgb(h: str) -> tuple[int, int, int]:
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def run(stack: str, big_dir: str) -> dict:
    ds = xr.open_dataset(stack)
    hv = ds["hv_db"].values
    dates = [str(t)[:10] for t in ds.time.values]
    if dates != scale.DATES:
        raise SystemExit("stack dates differ from PREREG_scale.md")
    valid = np.isfinite(hv).all(axis=0)
    forest = hv >= scale.frozen_T()
    lost = scale.lost_rule(forest) & valid
    fs = np.where(lost, first_switch(forest), -1)
    if (fs[lost] < FIRST_AFTER).any() or (fs[lost] > 7).any():
        raise SystemExit("unexpected first-switch index for a lost block")
    switch_dates = dates[FIRST_AFTER:8]
    legend = dict(zip(switch_dates, PALETTE))

    big_path, lost_path = Path(big_dir) / "big.json", Path(big_dir) / "lost.geojson"
    big = json.loads(big_path.read_text())
    g = big["grid"]
    if g["crs"] != "EPSG:3857":
        raise SystemExit("big.json grid is not EPSG:3857")
    xc, yc = ds["x"].values, ds["y"].values
    d = float(xc[1] - xc[0])
    src_tf = from_origin(xc[0] - d / 2, yc[0] + d / 2, d, d)
    code = np.where(lost, fs - FIRST_AFTER + 1, 0).astype(np.uint8)  # 1..5, 0 = none
    out = np.zeros((g["height"], g["width"]), np.uint8)
    reproject(code, out, src_transform=src_tf, src_crs=ds.attrs["crs"], dst_transform=Affine(*g["transform"]),
              dst_crs="EPSG:3857", resampling=Resampling.nearest, src_nodata=0, dst_nodata=0)
    img = np.zeros(out.shape + (4,), np.uint8)
    for i, col in enumerate(PALETTE, start=1):
        img[out == i] = (*hex_rgb(col), 255)
    Image.fromarray(img, "RGBA").save(Path(big_dir) / "first_switch.webp", format="WEBP", lossless=True, exact=True)

    counts = {dte: int((fs[lost] == FIRST_AFTER + i).sum()) for i, dte in enumerate(switch_dates)}
    big["first_switch"] = {
        "file": "first_switch.webp", "legend": legend, "block_counts": counts, "lost_blocks": int(lost.sum()),
        "definition": "per lost block (PREREG_scale.md rule, valid on all 9 dates): the first pass after 07-20 on which it is "
                      "non-forest and stays non-forest through 10-12. Descriptive only; no new score or threshold.",
        "command": "python validation/first_switch.py --stack data/stack_big_t2f174.nc --big-dir web/data/explore/big"}
    big_path.write_text(json.dumps(big, indent=1))

    gj = json.loads(lost_path.read_text())
    lab, n = ndimage.label(lost, structure=np.ones((3, 3), int))
    if n != len(gj["features"]):
        raise SystemExit(f"{n} patches here vs {len(gj['features'])} in lost.geojson; regenerate lost.geojson first")
    earliest = ndimage.minimum(fs, lab, index=np.arange(1, n + 1))
    by_id = {f["properties"]["id"]: f for f in gj["features"]}
    mismatch = 0
    for i in range(1, n + 1):
        f = by_id[i]
        f["properties"]["first_switch_date"] = dates[int(earliest[i - 1])]
        m = lab == i
        if abs(f["properties"]["n_blocks"] - int(m.sum())) or (f["properties"].get("first_flagged") not in (None, f["properties"]["first_switch_date"])):
            mismatch += 1
    if mismatch:
        raise SystemExit(f"{mismatch} patches disagree with lost.geojson (ids / sizes / first_flagged)")
    lost_path.write_text(json.dumps(gj, separators=(",", ":")))
    patch_counts = {dte: sum(f["properties"]["first_switch_date"] == dte for f in gj["features"]) for dte in switch_dates}
    return {"block_counts": counts, "patch_counts": patch_counts, "lost_blocks": int(lost.sum()), "patches": n}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--stack", default="data/stack_big_t2f174.nc")
    p.add_argument("--big-dir", default="web/data/explore/big")
    a = p.parse_args()
    print(json.dumps(run(a.stack, a.big_dir), indent=1))


if __name__ == "__main__":
    main()
