# PREREG: the forest/non-forest rule on the full NISAR frame (track 2, frame 174)

Written and committed 2026-11-14 BEFORE the frame stack is streamed and before any score in this file is computed.
Changes after the first scoring run go in a "Deviations" section at the end, never as edits of the text above. Scored once; no rerun, no retuning.

## Question
Does the frozen forest/non-forest rule (HV >= T_db = -11.250146865844727 dB, `validation/fnf_metrics.json`, 100 m blocks) hold on the whole frame, away from the ground it was tuned and first tested on, and does the fixed class-switch rule flag blocks that independent optical alerts also flag? Same method as `PREREG_scale.md`, larger area. T_db is never refit.

## Acquisitions
Track 2, frame 174, ASCENDING, mode 20+5, the 9 dates 2026-06-26, 07-08, 07-20, 08-13, 08-25, 09-06, 09-18, 09-30, 10-12 (same granules as `PREREG_scale.md`; one per date, latest processing).

## AOI (from metadata only; no pixel or score was looked at)
- Footprint: `validation/frame_footprint.py` reads each granule's boundingPolygon (asf_search), projects to EPSG:32722 and intersects the 9 polygons: 60,378 km2, UTM bounds x 32283.5..335075.7, y 9072039.1..9354045.2 (`validation/frame_footprint.json`).
- Block grid: 100 m blocks = 5 x 5 frequencyA pixels, aligned with the big stack (block edges x = 60 mod 100, y = 80 mod 100). Streamed rectangle = the largest whole-block rectangle inside the intersection's bounding box: block edges x 32360..334960, y 9072080..9353980 = 3026 x 2819 blocks (15130 x 14095 freqA pixels; first pixel centre x0 = 32370, y0 = 9353970). About lon/lat W S E N -55.24 -8.39 -52.49 -5.83.
- Scored blocks ("AOI"): blocks of that rectangle with a finite HV value on all 9 dates (as `scale.py`), minus the exclusions below. Maps keep the rest as no data.
- **Excluded from every frame score**: (1) blocks whose centre is inside the original 20 km window W S E N -54.7900 -8.2900 -54.6080 -8.1090 (used to choose T); (2) blocks inside the 60 km box (freqA pixel centres x 62370..122350, y 9121770..9061790, i.e. block edges x 62360..122360, y 9061780..9121780; scored in `PREREG_scale.md`). Maps still draw both.
- Band: frequencyA, 5x5 linear block mean while streaming (`load_big.py --block 5`), as decided by the rule in `PREREG_scale.md` (median |B - A| 0.720 dB > 0.3 dB).

## Rule (unchanged from fnf.py / PREREG_scale.md)
- Per date: block HV in dB, forest if HV >= T_db (-11.25 dB, fixed).
- Median map: per-block median of the 9 dates' block HV in dB (`fnf.median_feature`), forest if >= T_db.
- Class-switch loss: a block is **lost** if forest on >= 2 of the first 3 passes (06-26, 07-08, 07-20) AND non-forest on BOTH of the last 2 passes (09-30, 10-12). Exactly `scale.lost_rule`. No other loss variant is computed.

## Scores (scoring area = AOI as above)
### (a) Forest map vs Hansen
- Reference: Hansen GFC v1.13 forest (`forest_mask.py`: treecover2000 >= 30 AND lossyear == 0 AND datamask == 1) on the native 20 m grid behind the blocks, block = forest if >= 50 % of its 25 pixels are forest. Tiles are merged if the frame crosses a 10-degree tile edge (it does not: all of it is inside 00N_060W).
- Primary: the 9-date median map. Reported: overall accuracy, Cohen's kappa, all-forest baseline (and all-non-forest), forest precision and recall, **non-forest precision and recall**, confusion matrix (`fnf.metrics` extended with the non-forest class, same blocks).
- Secondary, one look: the same per date (OA, kappa, baseline), and the pure-block subset (Hansen block forest fraction <= 10 % or >= 90 %).
- Read against the all-forest baseline; OA at or below it means the rule adds nothing here.

### (b) Lost blocks vs GLAD alerts
- Sources: GLAD-L (confidence 2 and 3; `alert26`/`alertDate26`) and GLAD-S2 (values 1..4) from `fetch_alerts.py`'s reader and encodings, as `scale.py`. A block "has an alert" when an alert pixel centre falls inside it.
- Reference blocks: alert dated 2026-07-20 .. 2026-10-12. precision_like = share of lost blocks with an alert dated 2026-06-26 .. 2026-11-05 (+/- 24 days). recall_like = share of reference blocks that are lost; also recall_like restricted to Hansen-forest reference blocks.
- **Control**: random sample, same size as the number of lost blocks, from stable-forest blocks (forest on all 9 dates AND Hansen forest AND not lost) in the AOI; `numpy.random.default_rng(20261114)`, without replacement; whole stable set if smaller. Same metrics as above.
- Alerts are a reference, not ground truth. Radar-only lost blocks (no alert) are not called deforestation anywhere: they are "radar-only, unconfirmed".

## Interpretation, fixed in advance
- No pass/fail number. Forest map judged against the all-forest baseline; loss rule against its control. Precision_like close to the control's means the class switch is no better than picking forest at random.
- Blocks are spatially autocorrelated: no confidence intervals as if independent.
- Frame-edge blocks (swath edges, partly invalid pixels averaged over the valid ones) are kept if finite; no further QC filter is added after the fact.

## Outputs
`data/stack_frame_t2f174.nc` (gitignored), `data/forest_mask_frame_t2f174.tif`, `data/final_frame/` alerts, `validation/frame.py` (+ test), `validation/frame_metrics.json`, results section "Forest map, full frame" in `validation/results_final.md`, `validation/frame_run_log.md`, web files in `web/data/explore/frame/`.

## Deviations
(none yet)
