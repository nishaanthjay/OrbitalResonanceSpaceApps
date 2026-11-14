# CLAUDE.md — shared team memory

## Project
sars-deforest: detect forest clearing from NISAR L-band GCOV backscatter (HH/HV) with a JJ-FAST-style change method, score it against public alerts (GLAD/RADD), and show it on a static MapLibre web map. NASA Space Apps 2026, "Dancing with the SARs".

## Folder ownership rule
Only edit files in your own folder. Read CONTRACTS.md before writing outputs.

## Owners
| Folder | Role | Owner |
|---|---|---|
| pipeline/load | Pipeline A | Max #1 |
| pipeline/detect | Pipeline B | Max #2 |
| validation | Validation | Pro #1 |
| web | Front end | Pro #2 |
| submission | Story | Go |

## Confirmed facts (fill in as verified; leave blank until then)
### CURRENT AOI: S Para (Novo Progresso), switched 2026-11-14 ~15:50 ET (Rondonia dead: no alert-confirmed clearing >= 1 ha 08-29..10-16, per Pro #1)
Verified by Max #1 (scripts in pipeline/load/; QC by validation/stack_qc.py).
- Window (20x20 km): W S E N -54.7900 -8.2900 -54.6080 -8.1090 (EPSG:4326). Grid in stack: EPSG:32722 (UTM 22S), 20 m, x 82170..102430, y 9101870..9081650, 1012 x 1014 px.
- Track / frame / direction / mode: pathNumber 2, frameNumber 174, ASCENDING, rangeBandwidth "20+5", frameCoverage Full. Same grid on all dates (frame origin x0 12250, y0 9380150).
- Dates (all HH+HV, all used, none excluded): 2026-06-26, 07-08, 07-20, 08-13, 08-25, 09-06, 09-18, 09-30, 10-12. Max gap 24 days (07-20 to 08-13, one missed pass). Gate A: 5 dates before 08-26, 4 between 08-26 and 10-12.
- Per-date checks: HHHH mean_value attr 0.238-0.267 on all 9 (no outlier); window 100 % valid (1-2 NaN px on 06-26 and 08-25); HV median -10.7 to -10.9 dB, HH -5.8 to -6.2 dB.
- Gate B (validation/stack_qc.py --forest-mask, Hansen mask below): corr(HV, forest mask) +0.675, +0.686, +0.681, +0.677, +0.687, +0.655, +0.684, +0.736, +0.771 (06-26..10-12); all >= 0.5. FFT shift search vs 10-12 (5x5 multilook): peak at zero shift on every date, corr 0.93-0.98. Blocks (4,0) and (7,0) flagged identically on all dates (fixed feature at the window's west edge, not a bad date).
- Full stack: `data/stack_spara_t2f174.nc` (9 dates, 63.8 MB, sha256 0e8ab5dd37f8893017b146aa66380c0af06b38b3ee0fdc0e41420dd7ad4b267e). Too big for git; Google Drive: https://drive.google.com/file/d/1mPg7_Msq-7oKh3xMiqappdHFVl9K-RyC/view?usp=sharing Sample in git: `data/sample/stack_spara_t2f174_sample.nc` (08-25, 09-06, 14.3 MB).
- Build: `python pipeline/load/load.py --bbox -54.7900 -8.2900 -54.6080 -8.1090 --start 2026-06-17 --end 2026-10-23 --track 2 --frame 174 --direction ASCENDING --mode 20+5 --tile spara_t2f174` (4 min 17 s).
- Forest mask: `python pipeline/load/forest_mask.py --stack data/stack_spara_t2f174.nc --out data/forest_mask_spara_t2f174.tif` (Hansen GFC v1.13 tile 00N_060W; 66.0 % forest; 33.8 % of window had loss 2001-2025). validation/build_masks.py currently fails here ("a candidate does not cover the whole grid") because it hard-codes the Rondonia tiles (Hansen 00N_070W, WorldCover S09W063/S12W063); change request to Pro #1.
- Layer paths, units (gamma0), validity floor: same product as below (`/science/LSAR/GCOV/grids/frequencyA/HHHH`, `HVHV`).

### Rondonia (DEAD, kept for the record)
- Root cause of the 06-18 / 06-30 / 07-24 mismatch: **not a load.py indexing bug.** All five dates checked (06-18, 06-30, 07-24, 08-17, 08-29) have identical EPSG 32720, grid origin x0 464410 / y0 9159830, spacing 20 / -20 m, size 16632 x 16236, and the window maps to the same slice (y 8509-9510, x 2618-3618; x 516770..536750, y 8989650..8969650). identification says isGeocoded True, processingType Nominal, same track/frame, and boundingPolygon corners agree within ~0.01 deg. So the pixels at the same map coordinates show different ground on those dates: a geolocation/processing problem inside the provisional product. Cause beyond that UNKNOWN.
- AOI: Rondonia, BR (Porto Velho-Ariquemes). Search bbox W S E N: -63.5 -10.0 -62.5 -9.0.
- Analysis window (swath-valid on all 9 catalogue dates): centre lon -62.7564, lat -9.2306; 1000x1000 px freqA = 20x20 km; bbox W S E N: -62.8474 -9.3211 -62.6654 -9.1401. The swath covers only the NE of the search bbox on 2026-06-18 and 2026-07-24, so stay inside this window (or re-run pipeline/load/common_valid.py before moving it).
- Track / frame / direction / mode: pathNumber 60, frameNumber 173, ASCENDING, rangeBandwidth "20+5" (frequencyA 20 MHz + frequencyB 5 MHz). frameCoverage Full. All dates on the same grid (x 464410-797030, y 8835130-9159830).
- **Dates used: 2026-08-17, 08-29, 09-10, 10-04, 10-16 (5 dates, max gap 24 days: 09-10 to 10-04). Still passes the gate (>=5 dates, gap <=24), but with no margin.** The catalogue has 9 HH+HV dates (06-18, 06-30, 07-12, 07-24 + these 5); the first four are unusable in our window (see "Bad granules"). Product NISAR_L2_GCOV_PROVISIONAL_V1, crid P05023, pgeVersion R05.02.3.
- HDF5 layer path, HH: `/science/LSAR/GCOV/grids/frequencyA/HHHH`
- HDF5 layer path, HV: `/science/LSAR/GCOV/grids/frequencyA/HVHV`
  - Values are linear power (units "1", valid_min 0); 0 / tiny values (~1e-13) = outside swath, mask them. Same group also has `mask`, `numberOfLooks`, `rtcGammaToSigmaFactor` (suggests the HHHH/HVHV terms are RTC gamma0; multiply by this factor for sigma0 — TODO confirm in the GCOV product spec before relying on it). frequencyB = same layers at 80 m.
  - Coordinates: `xCoordinates`, `yCoordinates` in the same group; open with `xr.open_datatree(f, engine="h5netcdf", phony_dims="access")`.
- CRS: EPSG:32720 (WGS 84 / UTM zone 20S), from `.../frequencyA/projection` attr `epsg_code`.
- Pixel spacing: 20 m (frequencyA), 80 m (frequencyB). HDF5 chunks 512x512.
- Streaming: opening a granule ~20 s; a 1000x1000 freqA window ~3-7 s per polarization (from a home connection, no AWS). Median in window on the 5 good dates: HH -6.2 to -6.4 dB, HV -11.2 to -11.3 dB.
- Alert sources (no paid account, but need a free sign-up): Earth Engine assets RADD `projects/radar-wur/raddalert/v1`, GLAD-S2 `projects/glad/S2`, GLAD-L `projects/glad/alert/UpdResult`, GFW integrated `projects/forma-250/assets/gfw_integrated_alerts/default_latest`; or GFW Data API (free API key required; no-key requests are refused). Integrated layer has confidence only; per-system (RADD-only vs GLAD-only) needs the separate assets or API fields. RADD coverage likely includes the AOI except already-cleared land (visual check of GFW coverage tiles). No alert counts retrieved yet.
- Forest-mask options: Hansen GFC v1.13 (~30 m; tile 00N_070W; public GCS download or EE `UMD/hansen/global_forest_change_2025_v1_13`); ESA WorldCover 2021 v200 (10 m; public S3 `s3://esa-worldcover/v200/2021/map` --no-sign-request, or EE `ESA/WorldCover/v200`); JAXA PALSAR-2 FNF (25 m; email registration). Not chosen yet.
- Cloudiness tie-breaker: UNKNOWN (no AOI comparison found; Wilson & Jetz 2016 MODIS cloud frequency could settle it).
- Clearing event after the first ~3 dates: NOT YET VERIFIED (needs alerts, Pro #1).
- Backup AOI: S Para (Novo Progresso), track 2, frame 174, ASCENDING, 20+5, 9 dual-pol dates 2026-06-26..10-12, max gap 24. Also passing: Santa Cruz BO track 60 frames 169/170.
- **Bad granules (excluded with `load.py --exclude-dates 2026-06-18 2026-06-30 2026-07-12 2026-07-24`):**
  - 2026-07-12: mis-scaled in the source product. Its own HHHH `mean_value` attr is 576.8 vs ~0.22 on other dates (~+24 dB in our window).
  - 2026-06-18, 06-30, 07-24: do not show the same landscape as Aug-Oct. With 5x5 multilook, HV correlation with 08-17 is -0.29 / 0.35 / 0.04 at zero shift and at most 0.37 at any shift (FFT search), vs 0.96-0.99 among the Aug-Oct dates; spatial std 0.6-1.9 dB vs ~3.1 dB; no forest/non-forest HV contrast (-0.8 to +0.7 dB vs +5.8 to +6.7 dB on Aug-Oct, Hansen mask below); no shift within +-1.8 km restores it. Metadata (crid P05023, pge R05.02.3, orbitType MOE) is identical to the good dates; cause UNKNOWN (all four were processed in July 2026). Do not use them.
- Full stack: `data/stack_rondonia_t60f173.nc` (5 dates, 1001x1000, 34.7 MB, sha256 d256a920...64bd). Too big for git; shared via Google Drive (link: TODO). Sample in git: `data/sample/stack_rondonia_t60f173_sample.nc` (08-17, 08-29, 13.9 MB). Native 20 m, not multilooked (detect multilooks).
- Units: HHHH/HVHV are RTC gamma0; sigma0 = rtcGammaToSigmaFactor x gamma0 (an approximation per spec). Sources: https://nisar-docs.asf.alaska.edu/gcov/ and NISAR D-102274 Rev D (L2 GCOV Product Spec) p.17, p.20 sec 4.3.1. **Stack keeps gamma0**: measured over the window on all 9 dates (`pipeline/load/factor_db.py`), the factor changes between dates by |dB| p99 <= 0.04, max 0.70 per pixel, and max 0.01 dB after 5x5 multilook, so it cancels in dB differences.
- Validity floor: power <= 1e-6 -> NaN. Measured (`pipeline/load/check_units.py`): outside-swath pixels read ~1e-15 to 2e-13; all 9,009,000 window pixels per pol are >= 1e-3, so the window has no invalid pixels and the floor sits in the empty gap.
- **Forest mask (chosen, pending Max #2 OK): Hansen GFC v1.13**, forest = treecover2000 >= 30 % AND lossyear == 0 (no loss 2001-2025) AND datamask == 1. Built on the exact stack grid by `pipeline/load/forest_mask.py` -> `data/forest_mask_rondonia_t60f173.tif` (uint8, 28 KB, EPSG:32720, 20 m; 73.2 % forest; 21.3 % of the window had loss 2001-2025). Loads via detect.load_forest_mask; HV forest-minus-non-forest contrast peaks at zero shift (alignment OK). The 30 % threshold is a parameter (`--treecover-min`), not tuned. Citation: Hansen et al. 2013, Science 342:850-853; band encodings from EE catalog UMD/hansen/global_forest_change_2025_v1_13.
- Tune/holdout dates note for Max #2 / Pro #1: with 5 dates, baseline = earliest dates (e.g. 08-17, 08-29, 09-10) and detection on 10-04, 10-16 only.
- Threshold HH (dB):
- Threshold HV (dB):
- Min detection size (ha):

## Data access notes
- Product: `NISAR_L2_GCOV_PROVISIONAL_V1`, via `earthaccess`.
- Earthdata Login credentials live in `~/.netrc`. Never commit them.
- Stream with `earthaccess` + `fsspec` + `xarray.open_datatree(..., engine="h5netcdf")`.
- Inspect the datatree to find layer paths. Never guess them; record them above once confirmed.
- Files are ~5 GB each: stream small windows only, never download whole files.

## Hard rules
- No simulated/fake images in the final submission.
- All placeholder data must be named `placeholder_*` and deleted before submission.
- Cite every source (see submission/sources.md).
- Do NOT claim: that this stops deforestation, how much carbon it saved, or that it works everywhere.

## Known limits
- Rain / soil moisture change backscatter and cause false alarms.
- Fire: double-bounce changes can mimic or mask clearing.
- Flooded forest causes false alarms (backscatter shifts).
- Selective logging is not detected.
- Tested on one area only.
