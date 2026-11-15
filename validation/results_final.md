# S Para final results (track 2, frame 174, 9 dates)

Run 2026-11-14. Every number below was printed by the command next to it (run from the repo root unless it starts with `cd validation`; `OUT=data/final_spara`, gitignored; the shell variables are the files `$OUT/tune_bbox.txt` and `$OUT/hold_bbox.txt`). The numbers are **agreement with another alert product**. Alerts are a reference, not ground truth: this is not accuracy. Nothing was retuned after the holdout numbers were seen, and the holdout was scored once per source with no rerun.

## Setup
| Item | Value | Command / source |
|---|---|---|
| Stack | `data/stack_spara_t2f174.nc`, 9 dates, sha256 `0e8ab5dd...b267e` (matches CLAUDE.md) | `sha256sum data/stack_spara_t2f174.nc` |
| Window | W S E N -54.7900 -8.2900 -54.6080 -8.1090 | CLAUDE.md |
| Tune half (north) | -54.79 -8.195 -54.608 -8.109 | `$OUT/tune_bbox.txt` (centre latitude + 0.0045 deg) |
| Holdout half (south) | -54.79 -8.29 -54.608 -8.204 | `$OUT/hold_bbox.txt` (centre latitude - 0.0045 deg); 1 km buffer strip between |
| Hansen forest mask | 66.0 % forest, 33.8 % of the window had loss 2001-2025 (same file hash as before the rebuild) | `python pipeline/load/forest_mask.py --stack data/stack_spara_t2f174.nc --out data/forest_mask_spara_t2f174.tif` |
| Alerts | GLAD-L 52,772 pixels, GLAD-S2 1,087,012 pixels (all dates) | `python validation/fetch_alerts.py --bbox -54.7900 -8.2900 -54.6080 -8.1090 --out-dir $OUT` |
| Chain masks | forest_mask 56.3 % (577,438 px), stable_forest 51.6 % (529,042 px) | `python validation/build_masks.py --stack data/stack_spara_t2f174.nc --first-date 2026-06-26 --alert-dir $OUT --out-dir $OUT` |
| Scored dates | 2026-07-20, 08-13, 08-25, 09-06, 09-18, 09-30, 10-12 (each has >= 2 earlier dates; 06-26 and 07-08 serve only as baseline) | my choice, consistent with `validation/run_chain.sh` |

`validation/run_chain.sh` is a zsh script and was not run as a script; its steps were run one by one with the same arguments (steps 1 to 4). Its step 5 (blind label sheet) and the holdout noise-floor diagnostic were not run, so `hand_labeled` is `null` (pending) and the holdout was not looked at before scoring.

## Thresholds (chosen on the north half only, before any scoring; written to CLAUDE.md in commit 65fd478)
| Item | Value | Command |
|---|---|---|
| HH rise threshold | 1.0 dB | `python validation/noise_floor.py --stack data/stack_spara_t2f174.nc --stable-mask $OUT/stable_forest.tif --region-bbox $(cat $OUT/tune_bbox.txt) --date <7 scored dates> --out $OUT/noise_floor_tune.json` -> "CFAR (pooled firing <= 0.01): hh_thresh 1.0 hv_thresh 1.0" |
| HV drop threshold | 1.0 dB (run as `--hv-thresh -1.0`; the patched detect.py treats -1 and 1 alike) | same command |
| Minimum detection size | 2 ha | fixed in `run_chain.sh` before any sweep; **not** chosen from data. One 5x5-multilook pixel is 1 ha |
| Multilook | 5x5 | detect.py default |

The rule picks the smallest threshold of the grid {1, 1.5, 2, 2.5, 3, 3.5, 4, 5, 6} dB with <= 1 % of tune-half stable-forest pixels firing, pooled over the scored dates (pooled firing of tune-half stable forest at 1.0 dB: HH 0.77 %, HV 0.90 %, both <= 1 %; at 1.5 dB: HH 0.024 %, HV 0.058 %; from `$OUT/noise_floor_tune.json`, `dates.pooled.<ch>.fire_frac`). 1.0 is the grid minimum, so lower values were not evaluated. Tune-half stable-forest robust noise s.d. on single dates: 0.39 to 0.45 dB.

Sweep on the tune half (record only, no score): `python pipeline/detect/detect.py --stack data/stack_spara_t2f174.nc --date <7 dates> --min-ha 2 --forest-mask $OUT/forest_mask.tif --stable-mask $OUT/stable_forest.tif --tune-bbox ... --holdout-bbox ... --sweep-hh 1 1.5 2 2.5 3 3.5 4 5 6 --sweep-hv 1 1.5 2 2.5 3 3.5 4 5 6 --log $OUT/detect_log_spara_t2f174.json` (table in `$OUT/sweep_tune.txt`; for example HH 1.0 / HV 1.0 gives 114 detections, 243 ha on the tune half).

## Detections
Command: `python pipeline/detect/detect.py --stack data/stack_spara_t2f174.nc --date <7 dates> --hh-thresh 1.0 --hv-thresh -1.0 --min-ha 2 --forest-mask $OUT/forest_mask.tif --stable-mask $OUT/stable_forest.tif --tune-bbox $(cat $OUT/tune_bbox.txt) --holdout-bbox $(cat $OUT/hold_bbox.txt) --final --out-dir $OUT/final --log $OUT/detect_log_spara_t2f174.json`

| Count | Value |
|---|---|
| Per-date detections, whole window (what is scored) | 181 (28, 54, 23, 21, 22, 15, 18 on the 7 dates) |
| of which tune half / holdout half | 116 / 57 (8 in the buffer strip) |
| Merged patches shown on the map (`web/data/detections.geojson`) | 157 (102 tune, 48 holdout, 7 buffer); 360 ha in total |

Merge command: `python pipeline/detect/web_patches.py --stack data/stack_spara_t2f174.nc --detections $OUT/final/detections.geojson --tune-bbox ... --holdout-bbox ... --out web/data/detections.geojson --summary-out web/data/summary.json --tuning-from $OUT/final/summary.json`. A patch is the 8-connected union of the per-date detections; `first_date` is its earliest detection date; the 9-value `hh_series_db` / `hv_series_db` are the patch means of the 5x5-multilooked full-precision stack. The scored file is the per-date one; the metrics count per-date detections.

## Agreement with GLAD alerts, holdout (south half) only, scored once per source
Tolerance 24 days, any overlap (`--overlap-threshold 0`), 57 per-date detections.
Primary command (per source `f` = `glad_l` / `glad_s2`): `python validation/score.py --detections $OUT/final/detections.geojson --source GLAD-L --reference-file $OUT/alerts_glad_l.json --holdout-bbox $(cat $OUT/hold_bbox.txt) --tolerance-days 24 --overlap-threshold 0 --merge-dates --min-ref-ha 1 --tile spara_t2f174 --lag-table $OUT/score_glad_l/lag.csv --out-dir $OUT/score_glad_l`
Secondary command: the same without `--merge-dates --min-ref-ha 1 --lag-table` (pixel-patch reference, `--out-dir $OUT/score_glad_l_secondary`).

| Source, variant | precision_like | recall_like | F1_like | detections agreeing | reference patches agreeing |
|---|---|---|---|---|---|
| **GLAD-L, primary (web metrics.json)** | **0.0351** | **0.0** | **0.0** | 2 of 57 | 0 of 179 (events >= 1 ha, merged across dates; 2082 events of any size) |
| GLAD-S2, primary | 0.0351 | 0.0182 | 0.0240 | 2 of 57 | 1 of 55 (events >= 1 ha; 7562 of any size) |
| GLAD-L, secondary | 0.0351 | 0.0016 | 0.0030 | 2 of 57 | 11 of 6950 |
| GLAD-S2, secondary | 0.0351 | 0.0020 | 0.0037 | 2 of 57 | 36 of 18433 |

GLAD-L is the headline source for `web/data/metrics.json` and `reference_alerts.geojson`. This was decided before scoring, because its encoding is documented in `validation/fetch_alerts.py` while GLAD-S2's alert classes are not. `n_reference` in the web file is 179 (the primary GLAD-L recall denominator).

### Lag table
`score.py --lag-table $OUT/score_glad_l/lag.csv` wrote **0 rows**. A row needs an agreeing detection with both `first_hh_date` and `first_hv_date`; the 2 agreeing detections each have only one of the two (id 176: HH first 2026-10-12, HV none; id 178: HV first 2026-09-30, HH none). No timeliness claim is possible from this run.

## Share of 2026 GLAD alerts on land already cleared before 2026
Command: `cd validation && python alert_prior_clearing.py --alert-dir ../$OUT --bbox -54.7900 -8.2900 -54.6080 -8.1090 --after 2026-07-08 --until 2026-10-12 --out ../$OUT/alert_prior_clearing.json`. Alert pixels whose centre has Hansen GFC lossyear 1..25 (loss 2001-2025) at the pixel; Hansen is a 2025 product, so this is "cleared before 2026" by Hansen's own mapping.

| Source | Period | Alert pixels | On Hansen loss 2001-2025 | Share |
|---|---|---|---|---|
| GLAD-L | 2026 (all), whole window | 45,312 | 41,915 | **92.5 %** |
| GLAD-L | 2026 (all), holdout half | 19,057 | 16,351 | 85.8 % |
| GLAD-L | scored period (2026-07-08, 2026-10-12], whole window | 30,948 | 29,734 | 96.1 % |
| GLAD-L | scored period, holdout half | 10,732 | 9,880 | 92.1 % |
| GLAD-S2 | 2026 (all), whole window | 48,714 | 15,590 | **32.0 %** |
| GLAD-S2 | 2026 (all), holdout half | 38,900 | 13,675 | 35.2 % |
| GLAD-S2 | scored period, whole window | 26,337 | 9,695 | 36.8 % |
| GLAD-S2 | scored period, holdout half | 19,832 | 8,506 | 42.9 % |

The detect forest mask excludes Hansen loss 2001-2025 (`forest_mask.tif`), so detections cannot fall on that land; this is consistent with, but does not prove, the low agreement.

## Supporting diagnostics (reading aids; none was used to choose anything)
- `cd validation && python clearing_check.py --alert-dir ../$OUT --bbox -54.7900 -8.2900 -54.6080 -8.1090 --after 2026-07-08 --until 2026-10-12`: GLAD alert **events** dated in (2026-07-08, 2026-10-12]: GLAD-L north 873 events (1460 ha; 62 of >= 1 ha), south 1763 events (812 ha; 115 of >= 1 ha); GLAD-S2 north 1232 events (62 ha; 9 of >= 1 ha), south 6519 events (242 ha; 15 of >= 1 ha). The largest GLAD-L north event is 1034.76 ha.
- `cd validation && python hansen_classes.py --detections ../$OUT/final/detections.geojson --bbox -54.7900 -8.2900 -54.6080 -8.1090`: by pixel area the detections lie on Hansen "intact" forest 99.1 % (north) and 98.0 % (south); 116 of 116 and 56 of 57 detections have intact as their majority class.

## Web files
`web/data/detections.geojson` (157 patches, EPSG:4326), `reference_alerts.geojson` (2982 GLAD-L event patches any size dated 2026-06-26..2026-11-05; `cd validation && python export_reference_window.py --alerts ../$OUT/alerts_glad_l.json --source GLAD-L --bbox -54.7900 -8.2900 -54.6080 -8.1090 --start 2026-06-26 --end 2026-11-05`; its holdout-half subset has the same 2082 patches as the file `score.py` wrote), `metrics.json` (agreement.split = "holdout"; `hand_labeled` null), `summary.json` (per first_date from the patches, `tuning` from detect), `explore/spara/hansen_loss.webp` (Hansen loss 2021-2025, RGBA, 1280 x 1280 on the grid and bounds of `composite_2026-06-26.tif`; `cd validation && python export_hansen_loss.py --grid ../web/data/spara/composite_2026-06-26.tif --out ../web/data/explore/spara/hansen_loss.webp`). `du -sb web/data` = 57,128,007 bytes (under the 60 MB budget).

Tests: `python -m pytest -q pipeline/detect validation` -> 62 passed.

## Hand-labelled check (Sentinel-2 chips)
Labeller: **Claude, the same assistant that ran the detection**, looking at the chips only; the key (`data/labels_private/labels_key.csv`, gitignored) was not opened until the labels were written. This is not an independent human label, and the chips are speckled (per-band stretch over forest), so only bare patches of roughly >= 1 ha are visible. Treat 0 as "no visible clearing at the point", not as a proven rate. A human re-label of `validation/labels_blank.csv` should replace it.

Sample (seed 20261114): 15 holdout + 15 tune per-date detections (one random point inside each), 15 controls on stable forest outside any detection (8 holdout half, 7 tune half), shuffled as P01-P45.
`cd validation && python make_label_sheet.py --detections ../data/final_spara/final/detections.geojson --stable-mask ../data/final_spara/stable_forest.tif --tune-bbox $(cat ../data/final_spara/tune_bbox.txt) --hold-bbox $(cat ../data/final_spara/hold_bbox.txt) --seed 20261114 --blank ../data/labels_private/sheet_s2.csv --key ../data/labels_private/labels_key.csv`
Chips: `python validation/s2_chips.py --sheet data/labels_private/sheet_s2.csv --out-dir validation/chips --log data/labels_private/chips_log.json` (before 2026-06-24, after 2026-11-11 for 30 points and 2026-11-01 for one). **14 of 45 points had no clear after scene** (labelled `unsure`, note "no clear image"). Labels: `validation/labels_filled.csv`.

Scoring (`C="python validation/compute_sample_precision.py --csv validation/labels_filled.csv --key data/labels_private/labels_key.csv"`):
| Group | Command | Points | cleared | not_cleared | unsure | precision (unsure excluded) | Wilson 95 % |
|---|---|---|---|---|---|---|---|
| Holdout detections (written to `metrics.json` `hand_labeled`) | `$C --half holdout` | 15 | 0 | 6 | 9 | 0.0 (0 of 6) | 0.00-0.39 |
| Tune detections (record only) | `$C --half tune --metrics <scratch>` | 15 | 0 | 14 | 1 | 0.0 (0 of 14) | 0.00-0.22 |
| Both halves | `$C --metrics <scratch>` | 30 | 0 | 20 | 10 | 0.0 (0 of 20) | 0.00-0.16 |
| Controls (stable forest, no detection) | same | 15 | 0 | 10 | 5 | false-positive rate 0 of 10 | 0.00-0.28 |

Reading: no labelled detection showed visible clearing, and the controls look the same as the detections, so the chips show no difference between detected and undetected forest. Only 6 of 15 holdout detections have usable images, so the holdout precision is weakly determined. `metrics.json` `hand_labeled` = `{n_sample: 15, precision: 0.0, n_unsure: 9}`. Tests: `python -m pytest -q validation` -> 26 passed.

## Forest map at scale (60 x 60 km, out-of-sample)
Run 2026-11-14, once, rules fixed in `validation/PREREG_scale.md` (committed in 1a8197a before the stack existed). T_db = -11.250146865844727 dB, unchanged from `fnf_metrics.json`. Every number below is in `validation/scale_metrics.json`, printed by:
`python validation/scale.py --stack data/stack_big_t2f174.nc --mask data/forest_mask_big_t2f174.tif --out validation/scale_metrics.json`
(inputs: `cd pipeline/load && python load_big.py --x0 62370 --y0 9121770 --nx 3000 --ny 3000 --block 5 --start 2026-06-20 --end 2026-10-20 --track 2 --frame 174 --direction ASCENDING --mode 20+5 --tile big_t2f174 --out-dir ../../data`, sha256 a33aaf28...d399c; `python pipeline/load/forest_mask.py --stack data/stack_big_t2f174.nc --out data/forest_mask_big_t2f174.tif --subdivide 5`). The original 20 km window is excluded from every score.

### Band choice
`cd pipeline/load && python freq_compare.py --bbox -54.7900 -8.2900 -54.6080 -8.1090 --start 2026-06-20 --end 2026-10-20 --track 2 --frame 174 --direction ASCENDING --mode 20+5 --out ../../data/freq_compare_spara.json`: frequencyB HV vs 4x4-averaged frequencyA HV, median |difference| 0.713 to 0.732 dB per date, **0.720 dB pooled** (528,101 px) > 0.3 dB, so frequencyA with 5x5 linear block averaging was used.

### Area
| Item | Value |
|---|---|
| Grid | EPSG:32722, 600 x 600 blocks of 100 m, lon/lat -54.9725 -8.4722 -54.4248 -7.9266 |
| Blocks valid on all 9 dates | 199,204 of 360,000 (55.3 %; the swath's west edge cuts the box) |
| of which in the original window (excluded) | 40,284 |
| **Scored blocks** | **158,920** (~1,589 km2) |

### (a) Forest map vs Hansen v1.13 (block forest if >= 50 % of 25 px)
| Map | n | OA | kappa | forest precision | forest recall | all-forest baseline |
|---|---|---|---|---|---|---|
| **9-date median** | 158,920 | **0.9543** | **0.8562** | 0.9856 | 0.9577 | 0.8133 |
| median, pure blocks (Hansen fraction <= 0.1 or >= 0.9) | 150,660 | 0.9683 | 0.8922 | 0.9934 | 0.9683 | 0.8314 |

Median confusion: TP 123,786, FP 1,804, FN 5,465, TN 27,865 (all-non-forest baseline 0.1867).

Per date, same frozen T (OA / kappa; baseline 0.8133 for every date): 06-26 0.9397 / 0.8143; 07-08 0.9349 / 0.8027; 07-20 0.9417 / 0.8198; 08-13 0.9404 / 0.8160; 08-25 0.9399 / 0.8163; 09-06 0.9369 / 0.8053; 09-18 0.9256 / 0.7796; 09-30 0.9183 / 0.7621; 10-12 0.9185 / 0.7629.

Reading: every single pass and the median beat the all-forest baseline (0.8133) on ground the threshold never saw. Single-pass OA drifts down from 0.94 to 0.92 over 09-18..10-12 (late dry season); the cause is not tested here.

### (b) Class-switch lost blocks vs GLAD alerts
Rule: forest on >= 2 of 06-26 / 07-08 / 07-20 AND non-forest on 09-30 and 10-12. **2,816 lost blocks** (2,816 ha, 1.77 % of scored blocks; 2,272 of them Hansen forest). Control: 2,816 blocks drawn (seed 20261114) from 101,293 stable-forest blocks (forest on all 9 dates, Hansen forest, not lost).
Reference blocks = alert dated 2026-07-20..10-12; precision window 2026-06-26..11-05 (+/- 24 days).

| Source | Set | blocks with alert / blocks | precision_like | reference blocks hit / reference | recall_like |
|---|---|---|---|---|---|
| GLAD-L | **lost** | 244 / 2,816 | **0.0866** | 177 / 3,550 | **0.0499** |
| GLAD-L | control | 10 / 2,816 | 0.0036 | 3 / 3,550 | 0.0008 |
| GLAD-S2 | **lost** | 406 / 2,816 | **0.1442** | 323 / 4,843 | **0.0667** |
| GLAD-S2 | control | 44 / 2,816 | 0.0156 | 32 / 4,843 | 0.0066 |

Recall on reference blocks that are Hansen forest: GLAD-L lost 66 / 389 = 0.1697 (control 3 / 389 = 0.0077); GLAD-S2 lost 201 / 2,851 = 0.0705 (control 32 / 2,851 = 0.0112).
Alert pixels read in the AOI box (all dates): GLAD-L 148,423 (2026 file), GLAD-S2 6,774,396; none undated.

Reading: the lost blocks agree with alerts far more often than random stable forest does (precision_like 24x the control for GLAD-L, 9x for GLAD-S2), but in absolute terms most lost blocks have no alert (91 % for GLAD-L, 86 % for GLAD-S2) and most alerted blocks are not flagged (recall_like 5 % and 7 %). 2,299 of the 2,999 merged lost patches in `web/data/explore/big/lost.geojson` are a single 1 ha block, consistent with speckle or moisture flips on single blocks; this was not filtered because the pre-registered rule has no size filter. Agreement numbers, not accuracy.

### Web files
`python web/tools/make_big.py --stack data/stack_big_t2f174.nc --metrics validation/scale_metrics.json --out-dir web/data/explore/big`: 9 `forest_<date>.webp`, `forest_median.webp`, `lost.webp` (603 x 607 px, EPSG:3857, lossless RGBA, 4.8 to 11.6 KB each), `lost.geojson` (2,999 patches, 4,618 ha incl. 923 patches touching the original window, flagged `in_original_window`; 1.39 MB), `big.json` (bounds, grid, dates, T_db, original window, scores copied from `scale_metrics.json`). All of `web/data` = 58,624,727 bytes (under 60 MB).

Tests: `python -m pytest -q pipeline/load validation web/tools` -> 45 passed.


## Cloud blindness (Sentinel-2 vs NISAR, 60 km AOI)
Run 2026-11-14, descriptive (no threshold or score from the forest map changed). Command:
`python validation/cloud_blindness.py --stack data/stack_big_t2f174.nc --out validation/cloud_blindness.json --web-out web/data/explore/big/cloud.json`
Source: Earth Search STAC v1, `sentinel-2-l2a` (same search as `s2_chips.py`), 2026-06-26..2026-10-12: 64 items, 63 after one-per-tile-and-date, grouped into one scene per acquisition date (tiles MGRS 21LYL + 21MYM mosaicked). Per scene, SCL resampled (mode) onto the stack's 100 m block grid; clear = SCL 4, 5, 6, everything else not clear (cloud, shadow, cirrus, and also no data). Good view = clear fraction >= 0.80.

| Area | Scenes | >= 80 % clear | Median clear fraction | Longest gap between >= 80 %-clear views |
|---|---|---|---|---|
| **60 x 60 km AOI** (360,000 blocks) | **32** | **19** | **0.886** | **20 days** (2026-09-19 to 2026-10-09) |
| NISAR footprint (199,204 blocks, valid on all 9 passes) | 32 | 22 | 0.900 | 17 days (2026-09-22 to 2026-10-09) |
| NISAR (L-band, same footprint) | 9 passes | 9 of 9 usable | n/a | 24 days (07-20 to 08-13, one missed pass) |

Per-scene clear % over the AOI (date: %): 06-29 86.1 ; 07-01 99.9 ; 07-04 99.9 ; 07-09 92.2 ; 07-11 0.1 ; 07-14 99.5 ; 07-19 99.5 ; 07-24 99.8 ; 07-29 78.1 ; 07-31 45.3 ; 08-03 99.9 ; 08-08 99.7 ; 08-10 15.2 ; 08-13 99.9 ; 08-18 100.0 ; 08-20 99.2 ; 08-23 91.1 ; 08-28 99.9 ; 08-30 98.0 ; 09-02 83.5 ; 09-07 0.0 ; 09-09 0.3 ; 09-12 62.4 ; 09-17 76.3 ; 09-19 91.0 ; 09-22 77.7 ; 09-27 72.4 ; 09-29 0.0 ; 10-02 1.6 ; 10-07 59.5 ; 10-09 87.3 ; 10-12 89.9. Fully clouded scenes (clear < 2 %): 07-11, 09-07, 09-09, 09-29, 10-02.

Reading, stated plainly: this window is the dry season, and Sentinel-2 saw this AOI well. 19 of 32 scenes were >= 80 % clear, and its longest gap between good views (20 days) is **shorter** than NISAR's longest gap between passes (24 days). So for June to October 2026 here, "optical goes blind" is not supported by the numbers; NISAR's advantage in this window is that every pass is usable (9 of 9, no cloud screening), not more frequent views. Clouding grows from September (4 of the 5 near-total cloud scenes fall 09-07..10-02). SCL alone is an upper bound on usable views: `s2_chips.py` found SCL misses smoke/haze (S Para 2026-10-12, AOT 0.17-0.25) and small cumulus. The wet season (roughly November to May, not in this window) was not measured.

## First-switch map (descriptive)
`python validation/first_switch.py --stack data/stack_big_t2f174.nc --big-dir web/data/explore/big`: for each lost block (PREREG_scale.md rule unchanged, valid on all 9 dates, whole 60 km map incl. the test window: 4,618 blocks), the first pass after 07-20 on which it is non-forest and stays non-forest through 10-12. Blocks: 08-13 427, 08-25 212, 09-06 328, 09-18 1,347, 09-30 2,304. Patches (earliest block date per patch; 2,999 patches): 08-13 358, 08-25 165, 09-06 253, 09-18 883, 09-30 1,340. Written to `web/data/explore/big/first_switch.webp` (legend in `big.json` under `first_switch`) and `first_switch_date` in `lost.geojson`. No new score or threshold. Half of the lost blocks switch only at 09-30, the last pass the rule allows, so most flags rest on two passes.

Tests: `python -m pytest -q validation pipeline/load web/tools` -> 53 passed.


## Forest map, full frame (NISAR track 2 frame 174, out-of-sample)
Run once on 2026-11-14 under `validation/PREREG_frame.md` (committed before streaming and scoring); no rerun, no retuning, T_db = -11.250146865844727 dB fixed. Every number below is read from `validation/frame_metrics.json`, produced by one command:
`python validation/frame.py --stack data/stack_frame_t2f174.nc --mask data/forest_mask_frame_t2f174.tif --alerts-dir data/final_frame --out validation/frame_metrics.json`
Stack: `data/stack_frame_t2f174.nc` (see CLAUDE.md "Frame stack"), mask `data/forest_mask_frame_t2f174.tif` (`python pipeline/load/forest_mask.py --grid-from 32410 9353930 3026 2819 --subdivide 5 --out data/forest_mask_frame_t2f174.tif`), alerts `data/final_frame/` (`validation/fetch_alerts_frame.py`).

### Area
- Grid 3026 x 2819 blocks of 100 m = 8,530,294 blocks; valid on all 9 dates: 5,910,947 (69.3 % of the rectangle).
- Excluded from every score: the 60 km box, 199,204 valid blocks, which already contains the original 20 km window (40,284 of them). Scored = 5,910,947 - 199,204.
- Scored: 5,711,743 blocks = 57,117 km2. Hansen forest share of the scored blocks: 86.2 %.

### (a) 9-date median forest map vs Hansen v1.13 forest
| | value |
|---|---|
| Overall accuracy | **0.926** |
| All-forest baseline | 0.862 (all-non-forest 0.138) |
| Cohen's kappa | 0.719 |
| Forest precision / recall | 0.977 / 0.936 |
| Non-forest precision / recall | 0.683 / 0.862 |

Confusion (rows = Hansen, columns = radar), blocks: Hansen forest: 4,605,038 forest, 315,960 non-forest; Hansen non-forest: 109,182 forest, 681,563 non-forest.
Pure-block subset (Hansen block fraction <= 10 % or >= 90 %, n = 5,415,191): OA 0.942, baseline 0.882, kappa 0.753, forest precision / recall 0.987 / 0.946, non-forest precision / recall 0.692 / 0.910.
Per date (OA / kappa; baseline 0.862 on every date): 06-26 0.905 / 0.655; 07-08 0.893 / 0.633; 07-20 0.907 / 0.661; 08-13 0.906 / 0.651; 08-25 0.883 / 0.611; 09-06 0.899 / 0.626; 09-18 0.875 / 0.585; 09-30 0.857 / 0.548; 10-12 0.826 / 0.492.
Reading, stated plainly: the median map beats the all-forest baseline (0.926 vs 0.862). Single dates are weaker, and 2026-10-12 (0.826) is below the all-forest baseline. Hansen is a 2000-2025 map, so some disagreement is real change since then, not radar error; this is agreement with a reference, not accuracy.

### (b) Lost blocks vs GLAD alerts (+/- 24 days, rule from PREREG_scale.md)
Lost blocks: 240,178 (4.20 % of scored blocks, 240,178 ha of class switch), of which 215,600 on Hansen forest. Stable-forest blocks available to the control: 3,093,834; control size 240,178 (seed 20261114).

| Source | | blocks | with alert | precision_like | reference blocks | hit | recall_like |
|---|---|---|---|---|---|---|---|
| GLAD-L | lost | 240,178 | 8,028 | 0.0334 | 64,101 | 7,253 | 0.1131 |
| GLAD-L | control | 240,178 | 312 | 0.0013 | 64,101 | 205 | 0.0032 |
| GLAD-S2 | lost | 240,178 | 10,303 | 0.0429 | 68,169 | 8,704 | 0.1277 |
| GLAD-S2 | control | 240,178 | 1,702 | 0.0071 | 68,169 | 1,442 | 0.0212 |

Recall_like restricted to Hansen-forest reference blocks: GLAD-L lost 0.4035 (5,471 of 13,559), control 0.0151; GLAD-S2 lost 0.1437 (6,639 of 46,201), control 0.0312.
Alert pixels read: GLAD-L 1,023,460, GLAD-S2 75,688,881.
Reading, stated plainly: lost blocks have an alert about 26 times (GLAD-L) and 6 times (GLAD-S2) as often as random stable-forest blocks, so the class switch is not random. But only 3.3 % (GLAD-L) and 4.3 % (GLAD-S2) of lost blocks carry an alert. The rest are **radar-only, unconfirmed**; we do not call them deforestation. Alerts are a reference, not ground truth.
## Credibility pack (descriptive, 60 km map)
Run 2026-11-14. No new threshold; nothing already scored was rescored. Command:
`python validation/credibility.py --big-dir web/data/explore/big --metrics validation/scale_metrics.json`
Adds `class_metrics`, `persistence`, `confidence`, `lost_categories` and `watch_priorities` to `web/data/explore/big/big.json` (no existing key changed), `category` to every patch in `lost.geojson` (nothing else changed), and writes `persistence.webp`. Built without the big stack (not on this machine): class metrics come from the counts in `scale_metrics.json`; per-block classes are decoded from the lossless `forest_<date>.webp` layers, and each display pixel is traced to its native 100 m block by warping block indices with the same `reproject` call as `make_big.py`. Checks built into the script (it stops if any fails): every patch rasterises back to its `n_blocks`; `lost.webp` traced back matches `lost.geojson` block for block; the scored lost blocks total 2,816; and the alert matching reproduces 244 (GLAD-L) and 406 (GLAD-S2) lost blocks with an alert, as in `scale_metrics.json`.

### 1. Class metrics (9-pass median map vs Hansen, scored blocks)
| | Hansen forest | Hansen non-forest |
|---|---|---|
| **Map forest** | 123,786 (tp) | 1,804 (fp) |
| **Map non-forest** | 5,465 (fn) | 27,865 (tn) |

| Class | precision | recall |
|---|---|---|
| Forest | tp / (tp + fp) = **0.9856** | tp / (tp + fn) = **0.9577** |
| Non-forest | tn / (tn + fn) = **0.8360** | tn / (tn + fp) = **0.9392** |

Overall agreement (tp + tn) / n = 0.9543, n = 158,920. Pure blocks (Hansen fraction <= 0.1 or >= 0.9, n = 150,660): forest 0.9934 / 0.9683, non-forest 0.8609 / 0.9683 (precision / recall). Reading: non-forest is the weaker class. 16.4 % of the blocks the map calls non-forest are Hansen forest (5,465 of 33,330), so 95.4 % is not just "mostly forest": non-forest recall is 93.9 %. Hansen is a reference, not ground truth.

### 2. Persistence (forest on how many of the 9 passes)
198,476 native blocks counted (whole 60 km map incl. the original window; blocks valid on all 9 passes that have a display pixel): forest on all 9 passes 121,140 (61.0 %), on none 40,260 (20.3 %), on 1 to 8 passes 37,076 (18.7 %). Counts per value in `big.json` `persistence`; map in `persistence.webp` (laterite 0 to canopy green 9). The "uncertain" class (9-pass median HV within +/-0.5 dB of T_db, a display choice) needs block HV values from `data/stack_big_t2f174.nc` and is **pending** (`confidence.status`). Run the script with `--stack` to add it.

### 3. Lost-patch categories
A patch is `alert_supported` if at least one of its blocks holds a GLAD-L or GLAD-S2 alert pixel dated 2026-06-26..11-05 (the PREREG_scale.md precision window, scale.py matching); otherwise `radar_only_unconfirmed`. Whole map (2,999 patches, 4,618 ha): **alert_supported 738 patches, 1,777 ha; radar_only_unconfirmed 2,261 patches, 2,841 ha** (61.5 % of flagged area). 1,887 of the 2,261 radar-only patches are a single 1 ha block. Scored blocks only: 485 of 2,816 lost blocks (17.2 %) have a GLAD-L or GLAD-S2 alert; 2,331 (82.8 %) have neither. Radar-only patches are unconfirmed radar change, not deforestation.

### 4. Watch priorities (top 20 by area)
The 20 largest lost patches (9 to 37 ha, 368 ha together) are in `big.json` `watch_priorities` (id, centroid, area, category, distance, first switch). All 20 are alert_supported. All 20 touch (100 m, adjacent blocks) land that was already non-forest at the start (non-forest on >= 2 of 06-26/07-08/07-20), i.e. they extend existing clearings rather than open new ones. 14 of the 20 lie in the original 20 km window (used to choose T; listed and flagged `in_original_window`, not excluded, since this is a list of places to check, not a score). First switch: 08-13 for 17, 08-25 for 1, 09-18 for 2. Distance is not a useful ranking key for these 20 because every one is adjacent; ranking is by area only.

Tests: `python -m pytest -q validation pipeline/load web/tools` -> 69 passed (after rebasing on the full-frame commits).
