# sars-deforest

Forest-clearing detection from NISAR L-band radar (HH/HV), checked against public deforestation alerts, shown on a web map. NASA Space Apps 2026, "Dancing with the SARs".

- Live map: https://sars-deforest.vercel.app
- Repo: https://github.com/nishaanthjay/OrbitalResonanceSpaceApps
- Video: [BLANK]

## What we built
1. **Load** (`pipeline/load`): streams a 20 x 20 km window of NISAR L2 GCOV HH and HV from each date into one stack (`hh_db`, `hv_db`, dB).
2. **Detect** (`pipeline/detect`): a JJ-FAST-style change method. Each date is compared with the mean of the earlier dates; an HH rise (early stage) or an HV drop (late stage) past a threshold, inside a forest mask and above a minimum patch size, becomes a detection polygon.
3. **Validate** (`validation`): thresholds are chosen on one half of the window (north) and scored once on the other half (south), with a 1 km buffer between. Results are reported as agreement with reference alerts, not as accuracy.
4. **Map** (`web`): static MapLibre page showing detections, reference alerts, and per-date HH/HV change layers.

We also test a simpler question, how well HV alone separates forest from non-forest (section "Results").

## How to run
```bash
pip install -r requirements.txt
# load (needs an Earthdata Login in ~/.netrc; never commit it)
python pipeline/load/load.py --bbox -54.7900 -8.2900 -54.6080 -8.1090 --start 2026-06-17 --end 2026-10-23 \
  --track 2 --frame 174 --direction ASCENDING --mode 20+5 --tile spara_t2f174
python pipeline/load/forest_mask.py --stack data/stack_spara_t2f174.nc --out data/forest_mask_spara_t2f174.tif
# detect and score: see pipeline/detect/README.md and validation/README.md (validation/run_chain.sh runs the chain)
# forest / non-forest test (rules fixed beforehand in validation/PREREG_fnf.md)
python validation/fnf.py --out data/fnf_metrics.json
python -m pytest validation pipeline/detect
# map
cd web && npx http-server -p 8000
```
The full S Para stack (63.8 MB, sha256 `0e8ab5dd...b267e`) is too big for git: [Google Drive](https://drive.google.com/file/d/1mPg7_Msq-7oKh3xMiqappdHFVl9K-RyC/view?usp=sharing). A two-date sample is in `data/sample/`.

## Data and methods
- **Radar:** NISAR L2 GCOV, provisional product (`NISAR_L2_GCOV_PROVISIONAL_V1`), via NASA Earthdata/ASF. HHHH and HVHV are gamma-0 power; the ASF documentation describes GCOV as radiometrically and terrain corrected (https://nisar-docs.asf.alaska.edu/gcov/). NISAR is a joint NASA-ISRO mission launched on 2025-07-30 (https://www.eoportal.org/satellite-missions/nisar). The catalogue entry says provisional products are meant for exploration and process studies that do not need rigorous validation (https://www.earthdata.nasa.gov/data/catalog/asf-nisar-l2-gcov-provisional-v1-1).
- **Area:** S Para, Brazil (Novo Progresso), 20 x 20 km, W S E N -54.7900 -8.2900 -54.6080 -8.1090, track 2, frame 174, ascending, 20+5 MHz mode. 9 dates, all HH+HV: 2026-06-26, 07-08, 07-20, 08-13, 08-25, 09-06, 09-18, 09-30, 10-12 (longest gap 24 days). One area only. A second area (Rondonia, track 60 frame 173) was dropped for detection; see limitations. It is used once, unchanged, in the forest / non-forest transfer test.
- **Forest mask:** Hansen/UMD Global Forest Change v1.13: forest = tree cover in 2000 >= 30 %, no loss 2001-2025, land (Hansen et al. 2013, Science 342:850-853). 66.0 % of the S Para window is forest in this mask.
- **Method:** 5 x 5 multilook in linear power (100 m blocks), change in dB against the mean of earlier dates, per-date normalisation by the median change over stable forest, thresholds, forest mask, minimum patch size. HH rise = early stage, HV drop = late stage. The approach follows JJ-FAST, JAXA/JICA's L-band alert system, which uses two PALSAR-2 images from before and after the clearing (https://www.eorc.jaxa.jp/ALOS/en/kyoto/jan2017_kc23/pdf/2-07b_KC23_JJ-FAST_Watanabe.pdf). Thresholds: HH [BLANK] dB, HV [BLANK] dB, minimum [BLANK] ha (chosen on the north half only; see CLAUDE.md "Threshold" lines).
- **Reference alerts:** GLAD-L (Landsat), GLAD-S2 (Sentinel-2) and RADD (Sentinel-1) via the Global Forest Watch data API, all CC BY 4.0 (details and caveats in `validation/README.md`). RADD and GLAD-S2 only map inside primary humid tropical forest. Alerts mark tree-cover disturbance, not only human deforestation.
- **Scoring rule:** patch level, a detection agrees if it overlaps an alert patch dated within the tolerance window; precision_like = agreeing detections / detections, recall_like = agreeing alert patches / alert patches. Holdout split only.

## Results
**Forest / non-forest from HV alone** (pre-registered in `validation/PREREG_fnf.md`, committed before the run; `validation/fnf_metrics.json`). Rule: forest if the median over dates of multilooked HV >= T. T = -11.25 dB, chosen on the north half only (max Youden J), then frozen. Reference is the Hansen mask, so these numbers measure agreement with that mask.

| Scored on | Blocks (100 m) | Accuracy | Kappa | Forest precision | Forest recall | All-forest baseline |
|---|---|---|---|---|---|---|
| S Para holdout (south half), 9 dates | 19,368 | 0.831 | 0.662 | 0.844 | 0.832 | 0.524 |
| S Para holdout, blocks that are <= 10 % or >= 90 % forest | 15,028 | 0.894 | 0.788 | 0.897 | 0.906 | 0.532 |
| Rondonia, same T unchanged, 5 good dates | 40,000 | 0.956 | 0.890 | 0.969 | 0.971 | 0.727 |

On single dates (same T, S Para holdout) accuracy is 0.81-0.84 and kappa 0.62-0.67. The tune half scored 0.950 and is not a result (T was chosen on it). The holdout is 52 % forest and the tune half 81 %, so the two are not directly comparable. No confidence intervals are given: neighbouring blocks are not independent, and each number comes from one half of one area (Rondonia: one area).

**Clearing detection agreement with alerts (holdout, patch level):** precision_like [BLANK] | recall_like [BLANK] | F1_like [BLANK] | detections [BLANK] | reference patches [BLANK] | source [BLANK] | tolerance [BLANK] days. [BLANK: take from `web/data/metrics.json` after the final run; `web/data/` is empty in the repo at the time of writing.]
Hand-labelled precision (Sentinel-2, 15 + 15 sample, `validation/sample_points.py`): [BLANK].

## Limitations
- **Provisional data.** The NISAR product is provisional and the catalogue says it is not rigorously validated (link above). We found problems in it ourselves (next two points).
- **Bad granule, Rondonia 2026-07-12.** Its own HHHH `mean_value` attribute is 576.8 against about 0.22 on other dates (about +24 dB in our window). Excluded.
- **Geolocation problem, early Rondonia dates (06-18, 06-30, 07-24).** On a common grid they do not show the same landscape as August-October (HV correlation with 08-17 of -0.29, 0.35, 0.04, against 0.96-0.99 among the later dates). Grid, projection and metadata are identical to the good dates, so the fault is inside the provisional product; the cause is unknown. Excluded. This left Rondonia with 5 usable dates and no alert-confirmed clearing >= 1 ha in 08-29 to 10-16, so we switched to S Para.
- **One area per location.** One 20 x 20 km window in S Para and one in Rondonia. Nothing here shows it works elsewhere.
- **Alerts are a reference, not ground truth.** They have their own errors, mark disturbance rather than only deforestation, miss patches under their minimum size, and the providers say not to use them for area estimates (`validation/README.md`). Disagreement is not proof of an error on either side.
- **Most 2026 alerts in S Para were re-clearing of land already cleared.** [BLANK: figure and where it comes from, e.g. validation/clearing_check.py or diagnose.py output; no number is claimed here.]
- **The radar responds late.** [BLANK: lag in days between alert date and first HH/HV crossing, from `score.py --lag-table`; none is claimed here.] The lag table covers only the few agreeing detections and is not a timeliness claim.
- **Short record.** 9 dates over about 3.5 months. Detection dates are scored with a tolerance, and each scored date needs at least 2 earlier dates as baseline (`validation/run_chain.sh`).
- **Forest mask.** Hansen ends at 2025 while the stack starts in mid-2026, so clearing in early 2026 is in neither. The forest / non-forest score depends on the mask's own errors, and secondary or degraded forest is a likely source of confusion; we did not measure that.
- **Method limits.** Rain and soil moisture change backscatter and cause false alarms; fire can mimic or mask clearing through double-bounce changes; flooded forest causes false alarms; selective logging is not detected (CLAUDE.md "Known limits").
- **Labels and window choice.** [BLANK: say whether any labels were AI-assisted; if so, which.] The S Para window was chosen after Rondonia failed for lack of alert-confirmed clearing. [BLANK: say whether the S Para window position was chosen for alert density.]
- **No claims about impact.** We do not claim this stops deforestation, any carbon saved, or that it works everywhere.

## Sources
See `submission/sources.md`.

## Licence
See `LICENSE`.
