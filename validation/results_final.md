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
