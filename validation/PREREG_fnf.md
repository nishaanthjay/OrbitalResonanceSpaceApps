# PREREG: forest / non-forest (FNF) accuracy from NISAR HV

Written and committed before `validation/fnf.py` is run on any stack. Started 2026-11-14 ~16:40 local; time-box 90 minutes.
If anything below has to change after the first run, the change goes in a "Deviations" section at the end of this file with the reason, never as an edit of the text above.

## Question
How well does a single threshold on multilooked NISAR L-band HV separate forest from non-forest, on ground the threshold was not tuned on, and on a different area with no re-tuning?

## Reference (labels)
- Hansen GFC v1.13 forest mask built by `pipeline/load/forest_mask.py`: forest = treecover2000 >= 30 % AND lossyear == 0 (no loss 2001-2025) AND datamask == 1. Everything else (including water, treecover < 30 %, and any loss pixel) = non-forest.
- This is the mask "at the first stack date" only in the sense that it is the latest Hansen year (2025). Loss between 2026-01-01 and the first stack date (S Para 2026-06-26, Rondonia 2026-08-17) is not in it. The mask is a reference, not ground truth; its own error is not measured here.
- Aggregation to the radar grid: the 20 m mask is coarsened with the same 5x5 blocks as the radar (100 m pixels); a block is forest if >= 50 % of its 25 pixels are forest.

## Feature
- Per date: 5x5 multilook of HV in linear power (`detect.multilook`, NaN skipped), converted to dB.
- Feature = per-pixel median over the dates, in dB.
- S Para: all 9 dates (2026-06-26 .. 10-12). Rondonia (transfer): the 5 good dates only (2026-08-17, 08-29, 09-10, 10-04, 10-16); 06-18, 06-30, 07-24 are excluded for the geolocation problem recorded in CLAUDE.md; 07-12 is not in the stack file.
- Blocks with a NaN feature are dropped from scoring.

## Rule
- Forest if feature >= T (HV is higher over forest).
- T is chosen on the TUNE half only, by **maximum Youden J** (J = TPR + TNR - 1, forest = positive) over a 0.05 dB grid of candidate thresholds (ties: lowest T). This is the only threshold that is scored.
- Otsu's threshold (256 bins, TUNE half only) is computed and reported as a tune-only diagnostic. It is not scored on the holdout and does not replace the primary threshold.
- T is then frozen.

## Split (S Para), same as `validation/run_chain.sh`
- Analysis window W S E N = -54.7900 -8.2900 -54.6080 -8.1090; centre latitude c = (S + N) / 2.
- Tune = block centres with latitude >= c + 0.0045 (north). Holdout = latitude <= c - 0.0045 (south). The 0.009 degree strip between them (~1 km) is a buffer and is used by neither.
- Block membership by block centre, via `detect.bbox_mask`.

## Scoring (holdout, once)
Reported on the S Para holdout, one run of `fnf.py`:
1. Overall accuracy, Cohen's kappa, forest precision, forest recall, the confusion counts.
2. Baseline: all-forest accuracy = forest fraction of the holdout (and the corresponding all-non-forest figure).
3. Per-date stability: the same frozen T applied to each date's single multilooked HV, OA and kappa on the same holdout. This is a diagnostic of the same single look, not a second selection; T is not changed by it.
4. Pure-block subset: the same prediction scored only on blocks whose forest fraction is <= 10 % or >= 90 % (mixed-pixel effect). Secondary, same single look.
5. Tune-half OA and kappa at T, for reference only (optimistic by construction).

## Transfer test (Rondonia), once
Frozen S Para T applied unchanged to the Rondonia 5-date median feature over the whole Rondonia window (nothing tuned there, so no split). Same metrics (1, 2, 4). No re-tuning, no second run, no per-date table choosing dates.
Rondonia sits on a different track/frame/incidence geometry and Amazon sub-region; a failure there is a result, not a reason to rerun.

## Interpretation, fixed in advance
- No pass/fail number is set. Results are read against the all-forest baseline: accuracy at or below the baseline means the rule adds nothing on that area, whatever the kappa.
- Pixels are spatially autocorrelated, so no confidence interval on pixel counts is reported as if pixels were independent. One holdout half of one area is one sample.
- Hansen's 2001-2025 loss mask also marks regrowth and old pasture as non-forest; HV cannot always separate degraded/secondary forest from forest. Errors of that type are expected and are not "fixed" by tuning.

## Outputs
`validation/fnf.py` (+ `test_fnf.py`); `data/fnf_metrics.json` (gitignored); results in `data/REPORT.md` section 14. A small copy of the metrics JSON goes to `validation/fnf_metrics.json` for the submission.

## Deviations
(none yet)
