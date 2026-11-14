# pipeline/detect — Pipeline B (Max #2)

**Reads:** `data/stack_<tile>.nc` (CONTRACTS.md section 1), binary forest-mask GeoTIFF, optional stable-forest mask GeoTIFF.
**Writes:** `web/data/detections.geojson` (features for the same date are replaced, other dates kept), `web/data/change_hh_<date>.tif`, `web/data/change_hv_<date>.tif` (CONTRACTS.md sections 2 and 3), `web/data/summary.json` (shape below, matches what `web/app.js` reads; **not yet in CONTRACTS.md**), and a detect log `data/detect_log_<tile>.json` (`--log`; gitignored working record of the split, tuning sweep, normalization offsets and parameters).

```bash
# 1. sweep thresholds on the TUNE set only (writes the sweep table to the detect log; no detections)
python pipeline/detect/detect.py --stack data/stack_T01.nc --min-ha HA --forest-mask forest.tif \
  --tune-dates D1 D2 --holdout-dates D3 D4 --sweep-hh 0.5 1 1.5 2 --sweep-hv 1 2 3 4
# 2. a person picks --hh-thresh / --hv-thresh from that table, then detects on all dates (tune and holdout)
python pipeline/detect/detect.py --stack data/stack_T01.nc --date D1 D2 D3 D4 \
  --hh-thresh DB --hv-thresh DB --min-ha HA --forest-mask forest.tif \
  --tune-dates D1 D2 --holdout-dates D3 D4 --final
python -m pytest pipeline/detect     # synthetic in-memory tests only; needs: pip install pytest
```
Thresholds are positive dB magnitudes: HH rise >= `--hh-thresh` (early stage), HV drop >= `--hv-thresh` (late stage). Record the chosen values and min size in CLAUDE.md. Omitting `--forest-mask` prints a warning and skips masking (debug only); `--final` refuses to run without it.

## Processing order (per date)
1. **Multilook** (`--multilook N`, default 5; 1 = off): average non-overlapping N x N blocks **in linear power**, back to dB. Done once on the whole stack, before anything else.
2. **Change**: dB of the date minus the baseline (mean of all earlier dates, `--average linear|db`).
3. **Stable-forest normalization**, per date and per polarization:

   `d_norm(p) = d(p) - median{ d(q) : q in S, d(q) finite }`

   where `S` is the stable-forest mask (`--stable-mask`, default: the forest mask). The median over `S` estimates the scene-wide shift that is not clearing (wet/dry canopy, calibration) and is robust to the few cleared pixels inside `S`. Skipped (with a warning) if neither mask is given. The offsets are stored in the detect log (`dates.<date>.normalization`).
4. **Thresholds** on `d_norm`, then the forest mask, then 8-connected clusters >= `--min-ha`.

Exported `d_hh` / `d_hv` (COGs and geojson properties) are the **raw** change (date minus baseline, as CONTRACTS.md section 3 says), not `d_norm`; add the stored offset to compare them with the thresholds.

## Multilook and minimum detectable size
After N x N looks one pixel covers `N*dx` by `N*dy` (dx, dy = the stack's real spacing; areas always come from the real grid spacing and CRS, `pixel_area_ha`). So:
- The smallest possible detection is one multilooked pixel, `N^2 * dx * dy`. The effective minimum size is `max(--min-ha, N^2 * dx * dy / 10^4)` ha. With the default N=5 that is 25 input pixels.
- Clearings narrower than about N input pixels are averaged with intact forest and may no longer cross the threshold (a synthetic unit test shows a 2x2-pixel block of -5 dB disappearing at N=5 with a 3 dB threshold).
- If pipeline/load already multilooks, use `--multilook 1` so looks are not applied twice.
The NISAR pixel spacing is not yet confirmed (CLAUDE.md), so no hectare value is stated here.

## Tune / holdout split
Give `--tune-bbox W S E N` + `--holdout-bbox W S E N` (EPSG:4326, must not overlap; a pixel belongs to a box if its centre is inside) **or** `--tune-dates ...` + `--holdout-dates ...` (disjoint). The split is stored in the detect log; give validation/score.py the same holdout arguments.
- `sweep_thresholds()` (CLI `--sweep-hh/--sweep-hv`) runs every (HH, HV) pair on the tune set only and records detection counts and areas per setting in the detect log (`tuning.results`). It computes no score and chooses nothing; it refuses holdout dates. Thresholds are picked by a person, never on the holdout.
- With a bbox split, the sweep counts only pixels inside the tune box (clusters crossing the edge are cut). Normalization offsets still use the whole scene's stable mask: they use no reference labels.
- Pass the same split arguments on the detection run. `summary.json` `tuning` is filled only if the log holds a sweep made under that same split; otherwise it is `null` (and a sweep under a different split is dropped from the log).

## Optional geojson properties (not yet in CONTRACTS.md)
`first_hh_date`, `first_hv_date` (`"YYYY-MM-DD"` or `null`): the earliest stack date, up to the detection date, on which that channel's threshold fired on at least half of the detection's pixels (same half rule as `stage`). Each date's change is against the mean of all dates before it. `null` = never fired.

## `web/data/summary.json` (not yet in CONTRACTS.md; shape taken from what `web/app.js` reads)
Exactly these fields; web lists any other field as unexpected.
```json
{"per_date": [{"date": "YYYY-MM-DD", "n_detections": 0, "total_area_ha": 0.0, "early_ha": 0.0, "late_ha": 0.0}],
 "tuning": {"split": "tune", "hh_thresh": 0.0, "hv_thresh": 0.0}}
```
`early_ha` / `late_ha` sum the areas of detections whose `stage` is early / late. Rows are replaced by date, other dates kept, sorted by date. `tuning` is `null` when the thresholds did not come from a tune-set sweep under the current split.

## Detect log `data/detect_log_<tile>.json` (our working record, gitignored)
```json
{"tile": "T01", "crs": "EPSG:32722", "pixel_spacing": {"x": 0.0, "y": 0.0, "unit": "metre"}, "multilook": 5,
 "split": {"by": "dates", "tune": ["YYYY-MM-DD"], "holdout": ["YYYY-MM-DD"]}, "final": true,
 "dates": {"YYYY-MM-DD": {"n_detections": 0, "total_area_ha": 0.0, "early_ha": 0.0, "late_ha": 0.0,
   "baseline_dates": ["YYYY-MM-DD"], "normalization": {"hh_offset_db": 0.0, "hv_offset_db": 0.0, "n_stable_px_hh": 0, "n_stable_px_hv": 0},
   "hh_thresh": 0.0, "hv_thresh": 0.0, "min_ha": 0.0, "average": "linear", "multilook": 5,
   "forest_mask": "path", "stable_mask": "forest_mask", "final": true, "split_part": "tune|holdout|null"}},
 "tuning": {"on": "tune", "split": {}, "dates": ["YYYY-MM-DD"], "min_ha": 0.0, "results":
   [{"hh_thresh": 0.0, "hv_thresh": 0.0, "min_ha": 0.0, "n_detections": 0, "area_ha": 0.0, "per_date": {"YYYY-MM-DD": 0}}],
   "note": "..."}}
```
`split` is `null` without a split; `split.tune/holdout` are `[W, S, E, N]` for a bbox split. Copy the chosen thresholds and the sweep table into CLAUDE.md / the submission if they need to be shared.

## What the JJ-FAST papers say (and don't)
- Latest image vs the average of past images; early stage = HH increase (mean +1.2 dB in their example), late stage = HV decrease (mean -3.2 dB) (KC23).
- Thresholds were for ALOS-2 ScanSAR and are marked "Parameter is under adjusting" (KC25), so none are hardcoded.
- The papers do **not** say whether the average is in dB or linear power. We default to linear power (`--average linear`); `--average db` is the alternative.
- Stable-forest normalization, multilooking and the tune/holdout sweep are our additions, not taken from the papers.

## Open decisions for the team
1. **Baseline averaging domain** (linear vs dB): confirm on real data.
2. **Forest mask source** (not chosen here). Free candidates, verify current access/versions before use:
   - Hansen/UMD Global Forest Change (30 m treecover2000 + lossyear): Google Earth Engine asset or GeoTIFF tiles from the project page. Threshold tree cover and drop pixels already lost before the baseline.
   - ESA WorldCover (10 m, class 10 = tree cover): open AWS bucket `esa-worldcover` (anonymous), 2020/2021 epochs only.
   - JAXA PALSAR/PALSAR-2 global forest/non-forest map (25 m, yearly): free download from JAXA EORC (registration). Same L-band family JJ-FAST uses.
3. **Stable-forest mask**: default is the forest mask; a stricter one (e.g. forest with no loss in recent years) would keep the median further from real clearings.
4. Thresholds (HH, HV), `--min-ha` and `--multilook`, picked from the tune-set sweep.

## Notes
- Detection area uses the real pixel spacing/CRS (geodesic area if the stack is in degrees), after multilooking.
- Tests use tiny synthetic arrays that live only in `test_detect.py`. They are never saved as data, never used in demos, and prove nothing about accuracy. Throw-away test outputs go to pytest's `tmp_path`.
