# Environmental evidence: access, processing and scientific scope

The extension supplements the frozen detector and existing evaluation. It does not fit a new model. Existing globe, terrain, clock, optical imagery, threat board and tour remain in place.

## What was retrieved

`data/environment/access.json` records actual November 15, 2026 catalog queries, bounds, example granules and HTTP responses. CMR returned matching IMERG and SMAP records, but the advertised science-file downloads returned HTTP 401. The PPS IMERG GIS directory also returned 401. No numerical environmental measurements were downloaded. FIRMS requires a MAP_KEY; none was supplied. Missing data is never interpreted as zero rainfall or no fires.

Reproduce the access audit without overwriting it:

```powershell
python web/tools/environment_data.py probe --out web/data/environment/access-new.json
```

## Set up your NASA accounts

1. Create a free [Earthdata Login](https://urs.earthdata.nasa.gov/users/new). Sign in yourself. Never put passwords or keys in chat, source files, Git or a handoff ZIP.
2. Open [Earthdata Search](https://search.earthdata.nasa.gov/) and find `GPM_3IMERGDL`, Version 07. Follow NASA's prompts to authorize GES DISC data access. Use the actual Earthdata Cloud links returned by the catalog. [GPM directory](https://gpm.nasa.gov/data/directory), [GES DISC help](https://disc.gsfc.nasa.gov/help).
3. Open [NSIDC SPL4SMGP v8](https://nsidc.org/data/spl4smgp/versions/8), follow its Earthdata Search link, log in, and select the region and dates. Use “Customize with Harmony” where offered. [NSIDC download steps](https://nsidc.org/data/user-resources/help-center/downloading-nsidc-daac-earthdata-cloud-data-using-web-browser).
4. At the [FIRMS Area API](https://firms.modaps.eosdis.nasa.gov/api/area/), choose “Get MAP_KEY” and register your email. Keep the key local. Check the historical source in the API's data-availability endpoint; use archive ordering if that source is unavailable. Never replace 2026 history with today's NRT observations.

Copy the exact `bbox_wsen` from the audit: southern Pará's exported 60 km box, EPSG:4326. Rainfall/moisture context spans June 12–October 12, including 14 antecedent days. FIRMS acquisition extends through October 19 for the last pass's retrospective ±7-day check. Context outside this box is unavailable, including most of the full frame.

## Product and quality rules

- IMERG Late Run uses a roughly 0.1° grid. Final Run can lag by months. Daily input must represent complete UTC days, normalized to `mm/day`; daily amounts sum to millimeters. Integrate actual intervals if starting with subdaily rates. Exclude provider fill/QC failures before a documented regional aggregation. Do not sum rates without time integration.
- SMAP L4 is a 9 km, 3-hourly modeled assimilation product, not local 100 m moisture. Use accepted daily regional values in `m3/m3`. The nearest value within ±3 days is shown with its date. NSIDC reports a geolocation issue for May 14–July 28, 2026; affected L4 values are withheld unless replacement/reprocessing is verified. Dense-forest and model limitations still apply.
- FIRMS VIIRS anomalies have nominal 375 m footprints. Preserve acquisition UTC time, provider confidence code, FRP in MW, instrument, satellite, version and day/night. An anomaly is not a burned-area measurement or a probability of clearing.

## Reproducible imports

`environment_data.py` uses the standard library and refuses to overwrite outputs. `environment_native.py` now provides native readers; their actual authenticated run must finish and be reviewed before its daily values are installed. The CSV import remains available for genuine quality-screened regional exports with columns `date,value,quality`, one row per day. Only rows explicitly marked `accepted` are retained. Missing/rejected days stay missing.

Provenance JSON must contain actual `source_url`, `product`, `version`, `unit`, `native_crs`, `spatial_resolution`, `quality_screening`, `spatial_aggregation`, `bbox_wsen`, `retrieved_at_utc`. SMAP affected dates require boolean `geolocation_reprocessing_verified: true` plus documented replacement details. Do not invent provenance.

```powershell
python web/tools/environment_data.py import imerg --csv PATH_TO_REAL_CSV --provenance PATH_TO_REAL_PROVENANCE --out web/data/environment/imerg.json
python web/tools/environment_data.py import smap --csv PATH_TO_REAL_CSV --provenance PATH_TO_REAL_PROVENANCE --out web/data/environment/smap.json
python web/tools/environment_data.py firms --prompt-key --out web/data/environment/firms.geojson
```

The FIRMS prompt hides the key and does not save it. Alternatively use your own local `FIRMS_MAP_KEY` secret workflow. Failures abort acquisition without writing a partial observation set.

Register only generated files. For example, with IMERG only:

```powershell
python web/tools/environment_data.py register --imerg web/data/environment/imerg.json --out web/data/environment/access-ready.json
```

Add `--smap` or `--firms` only when those files exist. Set the HTML body's `data-environment-registry` attribute to `data/environment/access-ready.json`. Keep the original audit. The frontend requests only registered files and validates their contents. Use new output paths for reruns and review any replacement before publishing.

## Explicit evidence interpretation

- Existing `alert_supported` class-switch patches retain their GLAD-L/GLAD-S2 overlap category and pre-registered June 26–November 5 window. That is product agreement, not field confirmation or calibrated probability. The failed original detector does not automatically inherit this category.
- Other patches remain insufficient evidence for confirmation. A clear image does not automatically assign optical support. Images are nearest strictly-before and on/after the first-change date, within 30 days. Their dates, scene IDs, regional clear fraction and radar outline are shown. The 3.2 km projected crops are resampled to about 100 m; local cloud fraction and visual labels are unknown.
- Rainfall totals use previous complete UTC days `[D-N,D)`, N=3,7,14. Any gap invalidates that window. Same-day rain is excluded because radar acquisition times are not known here.
- Fire proximity is great-circle distance within 5 km of the patch centroid and ±7 days retrospectively, not polygon intersection or causation. Complete date coverage is required to interpret zero matches.
- No unusually wet/dry classification is assigned without an independent climatology. Moisture remains a possible confounder. No new accuracy statistic is computed.

## Blinded review proposal

`review_sample.py` generates 30 blank rows: ten alert-supported patches, ten radar-only patches and ten stable-radar display pixels. Sampling within each stratum is random with seed 20261115; points are sampled inside selected polygons. The original 20 km development window is excluded. The wider 60 km region was already evaluated, so this is not a new held-out region.

```powershell
python web/tools/review_sample.py --out PATH_OUTSIDE_WEB
```

Pillow and Shapely are development dependencies already used by the repository. Keep `PRIVATE-review-key.json` away from blinded reviewers and outside the public web folder. Patch and control-pixel sampling units differ. Do not compute naive population recall or overall accuracy from this case-control sheet. The validation owner must approve the frame, weights and scoring before changing results. No teammate-owned scientific files are changed.

## Native regional acquisition (2026-11-15)

`environment_native.py` adds authenticated native readers without changing the detection pipeline. Login is interactive with `persist=False`. Each run writes a new directory outside the website; review its `status.json`, provenance and actual observations before installing JSON files. The native reader needs earthaccess, NumPy and h5py. Credentials never enter frontend files.

SMAP uses the inspected `Geophysical_Data/sm_surface`, `cell_lat`, and `cell_lon` fields. It averages equal-area native cell centers inside the exported 60 km bbox, screens native fill/range limits, soil temperature above 273.15 K, and snow fraction at most 1e-6 (numerical-zero tolerance). All regional cells and all eight UTC three-hour intervals are required for each daily mean. Only the six radar acquisition dates after July 28 are requested. Earlier passes remain unavailable under NSIDC's geolocation notice. This contextual model output is not independently validated local moisture; dense-forest limitations remain. [NSIDC Version 8 user guide](https://nsidc.org/sites/default/files/documents/user-guide/multi_spl4smau-v008-userguide.pdf).

IMERG first attempts authenticated range streaming of the official CMR science link, then authenticated HTTPS. It inspects variable names and requires explicit daily `mm/day` units before calculating a cos(latitude)-weighted regional mean. Missing, negative, nonfinite or incomplete regional fields are rejected. The initial authenticated retry returned HTTP 403 on three consecutive dates. This establishes access refusal, not the precise account/service cause. Cloud, legacy GES DISC and PPS anonymous probes returned HTTP 401. PPS uses separate registration; the PMM viewer only supplies recent history and is not a complete replacement for June–October. [NASA GPM access directory](https://gpm.nasa.gov/data/directory).

## Checks

```powershell
node --check web/environment.js
node --check web/evidence-core.js
node --test web/tools/test_evidence.cjs web/tools/test_environment_ui.cjs
python -m unittest discover -s web/tools -p test_environment_data.py -v
```

Synthetic observations exist only in tests and temporary directories. The DOM fixture is not visual browser testing.
