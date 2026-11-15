# PREREG: the forest/non-forest rule at scale (out-of-sample, S Para 60 x 60 km)

Written and committed 2026-11-14 BEFORE the big stack is built and before any score in this file is computed.
If anything below has to change after the first run, the change goes in a "Deviations" section at the end, with the reason, never as an edit of the text above. Scored once; no rerun, no retuning.

## Question
Does the frozen forest/non-forest rule from `validation/PREREG_fnf.md` (HV >= T_db = -11.250146865844727 dB from `validation/fnf_metrics.json`, 100 m blocks) hold on ~3,200 km2 of new ground around the S Para window, and does a fixed class-switch rule flag blocks that independent optical alerts also flag?

## Area
- Same acquisitions as the S Para stack: track 2, frame 174, ASCENDING, mode 20+5, the same 9 dates 2026-06-26, 07-08, 07-20, 08-13, 08-25, 09-06, 09-18, 09-30, 10-12 (granule names in `data/stack_spara_t2f174.nc` attrs; one granule per date, latest processing date).
- Big AOI: 60 x 60 km in the granules' own grid (EPSG:32722) centred on lon -54.699, lat -8.1995 (UTM x 92300, y 9091768). frequencyA pixel centres x 62370 .. 122350, y 9121770 .. 9061790 (3000 x 3000 px). x is shifted 60 m from the exact centre so the 100 m blocks align with the blocks of the original window (x 82170.., y 9101870..), which keeps the exclusion below clean. Approx. lon/lat W S E N: -54.973 -8.473 -54.425 -7.926.
- Clip: only blocks with a finite HV value on all 9 dates are used for anything (maps keep the rest as no data).
- **Original window excluded**: every block whose centre (lon/lat) is inside W S E N -54.7900 -8.2900 -54.6080 -8.1090 is excluded from every score in this file (it was used to choose T). Maps still draw it.

## Band choice (decided by a fixed rule, before the big stack is streamed)
- On the original window, all 9 dates: frequencyB HVHV (80 m) vs frequencyA HVHV averaged in linear power over the 4 x 4 frequencyA pixels that make up each frequencyB pixel (frequencyB pixel centres sit 30 m inside the frequencyA grid; checked: freqA x0 12250, freqB x0 12280, same EPSG). Both in dB; blocks finite in both.
- If the median absolute difference over all dates pooled is <= 0.3 dB, the big AOI uses frequencyB and a block = one 80 m frequencyB pixel (Hansen aggregated to the same 80 m pixel, >= 50 % rule). Otherwise frequencyA, averaged in linear power over 5 x 5 pixels (100 m) while streaming. Per-date medians and the pooled median go in CLAUDE.md either way.
- T_db is not changed in either case.

## Rule (unchanged from fnf.py)
- Per date: block HV (linear-power mean of the native pixels, NaN skipped, as `detect.multilook`) in dB; forest if HV >= T_db.
- Median map: per-block median of the 9 dates' block HV in dB (`fnf.median_feature`), forest if >= T_db.

## Class-switch loss rule (fixed now, the only variant)
A block is **lost** if it is forest on >= 2 of the first 3 passes (06-26, 07-08, 07-20) AND non-forest on BOTH of the last 2 passes (09-30, 10-12). Blocks must be valid on all 9 dates (above). No other loss variant is computed or tested.

## Scores (scoring area = big AOI, valid on all 9 dates, minus the original window)
### (a) Forest map vs Hansen
- Reference: Hansen GFC v1.13 forest mask from `pipeline/load/forest_mask.py` (treecover2000 >= 30 AND lossyear == 0 AND datamask == 1), built on the native 20 m grid of the big AOI (tile 00N_060W; the neighbouring tile is added only if the AOI crosses it), aggregated to the block with the `PREREG_fnf.md` rule: block = forest if >= 50 % of its pixels are forest.
- Primary: the 9-date median map. Reported: overall accuracy, Cohen's kappa, forest precision and recall, confusion counts, all-forest baseline (and all-non-forest), using `fnf.metrics`.
- Secondary (same single look, no selection): the same metrics per date; and the pure-block subset (Hansen block forest fraction <= 10 % or >= 90 %).
- Read against the all-forest baseline, as in `PREREG_fnf.md`: OA at or below the baseline means the rule adds nothing here.

### (b) Lost blocks vs GLAD alerts
- Sources: GLAD-L and GLAD-S2 pixels from `validation/fetch_alerts.py` (public UMD GeoTIFFs; GLAD-L confidence 2 and 3; GLAD-S2 all values 1..4 since its classes are undocumented). A block "has an alert" when at least one alert pixel centre falls inside the block footprint.
- Reference blocks: blocks in the scoring area with an alert dated 2026-07-20 .. 2026-10-12 (inclusive).
- precision_like = share of lost blocks with an alert dated within +/- 24 days of that period, i.e. 2026-06-26 .. 2026-11-05 inclusive.
- recall_like = share of reference blocks that are lost (a lost block's class switch happens between 07-20 and 09-30, inside the +/- 24 day tolerance of every reference date).
- Also reported (fixed now, not a variant of the rule): recall_like restricted to reference blocks that are Hansen forest (block fraction >= 0.5).
- **Control**: a random sample, the same size as the number of lost blocks, from "stable forest" blocks = forest on all 9 dates by the rule AND Hansen forest AND not lost, in the scoring area; numpy `default_rng(20261114)`, sampled without replacement. Its precision_like and recall_like are computed exactly as above. If lost blocks outnumber stable-forest blocks, the whole stable set is used and that is reported.
- Each source scored once. Alerts are a reference, not ground truth: these are agreement numbers, not accuracy.

## Interpretation, fixed in advance
- No pass/fail number. The forest map is judged against the all-forest baseline; the loss rule is judged against its control. Lost-block precision_like close to the control's means the class switch is no better than picking forest at random.
- Blocks are spatially autocorrelated; no confidence intervals are reported as if blocks were independent.
- GLAD-L in this window sits mostly on land Hansen already mapped as cleared before 2026 (`results_final.md`: 96.1 % in the scored period), so low recall against GLAD-L is expected and is reported, not explained away.

## Outputs
`pipeline/load/load_big.py` (stack), `data/stack_big_t2f174.nc` (gitignored), `data/forest_mask_big_t2f174.tif`, `validation/scale.py` (+ test), `validation/scale_metrics.json`, results section "Forest map at scale" in `validation/results_final.md`, web files in `web/data/explore/big/`.

## Deviations
- Implementation detail recorded after the single run (no change to any rule): alerts were read with `fetch_alerts.py`'s reader, tile naming and date encodings directly from the rasters inside `validation/scale.py` (writing GLAD-S2 rows as JSON for 60 km would be gigabytes). GLAD-L was read from `alert26` / `alertDate26` only: `alert25` holds 2025 dates, all outside both date windows.
