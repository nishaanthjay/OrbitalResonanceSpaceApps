# validation — Validation (Pro #1)

**Reads:** `web/data/detections.geojson` (CONTRACTS.md section 2), reference alerts (RADD / GLAD-L / GLAD-S2 / GFW integrated), the forest-mask GeoTIFF used by pipeline/detect.
**Writes:** `web/data/reference_alerts.geojson` (section 5), `web/data/metrics.json` (section 4), the hand-labeling CSV, optionally a lag-table CSV.

The numbers are **agreement** with another alert product. Alerts are a reference, not ground truth; never call them accuracy.

```bash
export GFW_API_KEY=...          # free key, see "Getting a GFW API key"; never commit it
# 1. agreement on the HOLDOUT split only (same split as pipeline/detect; refuses to run without one)
python validation/score.py --source RADD --holdout-dates D3 D4 --bbox W S E N \
  --tolerance-days N --overlap-threshold 0 --tile T01 [--min-confidence high] [--lag-table validation/lag.csv]
python validation/score.py --source RADD --holdout-bbox W S E N --tolerance-days N --overlap-threshold 0 --tile T01
# 2. hand-labeling sample (15 detections + 15 non-detected forest points by default)
python validation/sample_points.py --forest-mask forest.tif --seed 1 --holdout-dates D3 D4 --out validation/sample_points.csv
#    ... label the CSV (steps below) ...
python validation/compute_sample_precision.py --csv validation/sample_points.csv   # fills metrics.json hand_labeled
python -m pytest validation      # tiny hand-made polygons in the test files only; no network
```

## Reference alerts: how to get them without a paid account
Checked 2026-11-14 against the live GFW Data API (`GET /dataset/<id>/latest`, `/fields`) and the current Earth Engine docs. All four products are **CC BY 4.0**.

| Source (`--source`) | GFW dataset id | Earth Engine asset | Resolution | Coverage | Updates |
|---|---|---|---|---|---|
| `RADD` (WUR, Sentinel-1 radar) | `wur_radd_alerts` | `projects/radar-wur/raddalert/v1` (ImageCollection) | 10 m | Primary humid tropical forest of South America, Central America, sub-Saharan Africa, Southeast Asia; from Jan 2019 (Africa) / Jan 2020 (others) | weekly; S1 revisit 6–12 days |
| `GLAD-L` (UMD, Landsat) | `umd_glad_landsat_alerts` | `projects/glad/alert/UpdResult` | 30 m | 30°N–30°S (plus southern Brazil) | daily; revisit 8 days |
| `GLAD-S2` (UMD, Sentinel-2) | `umd_glad_sentinel2_alerts` | `projects/glad/S2alert` | 10 m | Amazon basin (primary humid tropical forest) | daily; revisit 5 days |
| `GFW-INTEGRATED` (GLAD-L + GLAD-S2 + RADD) | `gfw_integrated_alerts` | `projects/forma-250/assets/gfw_integrated_alerts/default_latest` | 10 m (GLAD-L upsampled) | 30°N–30°S | daily |

Latest versions on 2026-11-14: RADD `v20261108`, GLAD-L `v20261113`, GLAD-S2 `v20261113`, integrated `v20261114`. Raster grids (from each dataset's `Raster tile set` asset path): `epsg-4326/10/100000` = 1e-4° pixels for RADD, GLAD-S2 and integrated; `epsg-4326/10/40000` = 2.5e-4° for GLAD-L. `score.py` reads the grid from this metadata at run time.

### 1. GFW Data API (what `score.py` uses)
- **Auth:** free GFW account + API key. Metadata endpoints (`/dataset/...`, `/fields`) work without a key; `/query` does not (checked: HTTP 403 "Request is missing valid API key").
- **Getting a GFW API key** (from the GFW developer how-to, last updated 2025-07-03):
  1. `POST https://data-api.globalforestwatch.org/auth/sign-up` with JSON `{"name": ..., "email": ...}`, then confirm the email and set a password.
  2. `POST /auth/token`, form-encoded `username=<email>&password=<password>` → `access_token` (expires; repeat when needed).
  3. `POST /auth/apikey` with `Authorization: Bearer <access_token>` and JSON `{"alias", "email", "organization", "domains"}` → `api_key`. Keys are valid for one year by default. With no `domains` the key gets the lowest rate-limit tier; with domains, requests must send a matching `Origin` header (`score.py --origin`).
- **Query used:** `POST /dataset/<id>/latest/query/json` with header `x-api-key`, body `{"sql": "SELECT longitude, latitude, area__ha, <id>__date, <id>__confidence FROM results WHERE <id>__date >= 'start' AND <id>__date <= 'end'", "geometry": <bbox polygon>}`. A raster query needs a geometry. Each row is one alert pixel (centre lon/lat). Confidence values: `nominal`, `high`, `highest`.
- **Limits:** the exact rate limits and maximum rows per answer are **not stated** in the docs read. `score.py` also runs `SELECT SUM(area__ha)` over the same query and stops if the rows it got do not add up to it (a truncated answer); then use a smaller bbox or date window.
- **Not yet tested with a real key** (none available while writing this): the API path is unit-tested against a fake that returns the documented response shape. Run it once on a small bbox and compare with the GFW map before trusting it.
- `--reference-file rows.json` reads rows saved earlier from the same query (a list, or the API's `{"data": [...]}` answer), so teammates without a key can reuse one download.

### 2. Google Earth Engine (free noncommercial)
- **Auth:** a Google Cloud project registered for noncommercial Earth Engine use; the registration includes a noncommercial-eligibility questionnaire (required for all noncommercial projects since 2025-09-26).
- **Limits:** noncommercial projects default to the **Community Tier, 150 EECU-hours per month** (Contributor tier: 1,000/month). Per project: 40 concurrent requests, 100 requests/s, 2 concurrent batch tasks on average, 10 MB per request payload.
- **Access:** RADD: WUR's GEE scripts (access, and export as GeoTIFF to Google Drive) are linked from the WUR RADD page; the community catalog's snippet filters `projects/radar-wur/raddalert/v1` by `layer` (`alert`, `forest_baseline`) and `geography` (e.g. `sa`) and shows an `Alert` band with values 2–3. GLAD-L / GLAD-S2: example scripts are linked from the UMD GLAD page.
- **Not used by `score.py`:** the pixel encodings of these assets (date and confidence bands) were **not verified** here. If you export from GEE, decode them from the asset's own documentation or script, then save rows as `{longitude, latitude, <id>__date}` for `--reference-file`.

### 3. Manual download (no API, no GEE)
- GFW Open Data Portal: `https://data.globalforestwatch.org/datasets/gfw::integrated-deforestation-alerts/about` and `.../gfw::deforestation-alerts-radd/about` (raster tiles). These pages need JavaScript and could not be read from here: check their download format and value encoding before use.
- GLAD viewers with download: GLAD-L `https://glad-forest-alert.appspot.com/`, GLAD-S2 `https://glad.earthengine.app/view/s2-forest-alerts`.
- Any manual download must be converted to the rows format above for `--reference-file`. Do not hand-edit alert data.

### Cautions from the data providers (GFW metadata)
- Alerts mark tree-cover **disturbance**, not only human deforestation; GLAD-L can flag plantation harvest.
- Not for area estimates or trend comparisons. Recent low-confidence alerts can later be removed.
- GLAD-L alert dates are first *detection* dates; persistent cloud can put them weeks after the loss. RADD dates are the date of the first S1 image that triggered the alert (WUR).
- RADD and GLAD-S2 only map inside **primary humid tropical forest**: our detections outside that mask can never agree with them.
- RADD minimum mapping unit is 0.1 ha; RADD confidence: low > 85 %, high > 97.5 % disturbance probability (WUR).

Cite: Reiche et al. 2021 (RADD); Hansen et al. 2016 (GLAD-L); Pickens et al. 2020 (GLAD-S2); "Integrated Deforestation Alerts", UMD/GLAD and WUR, accessed through Global Nature Watch on <date>. Add the access date to submission/sources.md.

## Holdout rule
`score.py` scores only the holdout split that pipeline/detect used (`--holdout-bbox` or `--holdout-dates`, exactly one) and refuses to run without it. Thresholds were chosen on the tune split only (pipeline/detect `--sweep-*`).
- **bbox split:** detections and reference patches whose representative point lies in the holdout box. Alerts are loaded for that box (or `--bbox`).
- **dates split:** detections dated on a holdout date; alerts loaded for `--bbox` (required).
- The alert date window is `[first scored date − tolerance, last scored date + tolerance]`.

## Matching rule (patch level)
- A **patch** is one detection polygon, or one connected group of same-date reference alert pixels.
- A detection D and a reference patch R are **compatible** if `|date(D) − date(R)| <= --tolerance-days`.
- D **agrees** if the union of compatible R covers at least `--overlap-threshold` of D's area (and more than zero). R agrees the same way with the union of compatible D. `--overlap-threshold 0` = any overlap; patches that only touch at an edge never agree.
- Areas are geodesic on WGS84.
- `precision_like` = agreeing detections / detections; `recall_like` = agreeing reference patches / reference patches; `f1_like` = their harmonic mean. A ratio with nothing to divide by is `null`.
- `metrics.json` (section 4): `agreement.level = "patch"`, `agreement.split = "holdout"`; `hand_labeled` stays `null` until `compute_sample_precision.py` runs (an existing block is kept when `score.py` re-runs). `notes` states the tolerance, threshold and counts.
- Known bias: alert patches smaller than our minimum detectable size (see pipeline/detect README: multilook and `--min-ha`) count as misses.

## Hand labeling (Sentinel-2)
`sample_points.py` draws a stratified random sample: N detections (one uniform random point inside each randomly chosen detection polygon) and N forest pixels (pixel centres of the forest mask) that are not inside any detection, both within the holdout if given. Columns: `id, stratum, lon, lat, date, detection_id, label, notes`. Record the `--seed`.

For each row, using the Copernicus Browser (`https://browser.dataspace.copernicus.eu/`) or any Sentinel-2 L2A viewer:
1. **Dates to compare.**
   - *Before:* the most recent clear-sky Sentinel-2 image **on or before the first stack date** (the start of the baseline; the stack dates are in pipeline/detect's log `data/detect_log_<tile>.json`, `dates.<date>.baseline_dates[0]`).
   - *After:* the first clear-sky Sentinel-2 image **on or after the row's `date`**, within 60 days.
   - Use true colour (B4, B3, B2) and, if it helps, false colour (B8, B4, B3).
2. **Clear-sky rule.** Both images must be free of cloud, cloud shadow, cirrus and haze over the point and about 100 m around it. If the scene classification layer (SCL) is used: classes 3 (cloud shadows), 8 (cloud medium probability), 9 (cloud high probability) and 10 (cirrus) are not clear. If no clear pair exists in the windows, the row is `unsure`.
3. **Label** (column `label`, exactly one of):
   - `clearing`: canopy present in the before image and removed (bare soil, burned or cleared ground) in the after image at the point.
   - `no_clearing`: canopy unchanged, or the point was already non-forest in the before image.
   - `unsure`: no clear-sky pair, the point is on a clearing edge, or the change is ambiguous (seasonal flooding, burn scar with standing trees, thin selective logging). Write the reason in `notes`.
4. Label without looking at the alert layers or our change maps. If two people label, label independently and discuss disagreements; record unresolved ones as `unsure`.

`compute_sample_precision.py` refuses empty or unknown labels. It excludes `unsure` and reports `n_unsure`:
- `hand_labeled = {n_sample, precision, n_unsure}` for the detection stratum, where `precision = clearing / (clearing + no_clearing)`.
- It also prints the non-detection stratum's clearing fraction and 95 % Wilson intervals. With n = 15 these intervals are wide; report them with any number.

## Lag table (optional)
`score.py --lag-table out.csv`: one row per agreeing detection with `first_hh_date`, `first_hv_date` (optional detection properties, CONTRACTS.md section 2) and the earliest compatible alert date, plus `hh_lead_days` / `hv_lead_days` (alert date minus first date; positive = radar fired first). Rows with any of the three dates missing are skipped. Only meaningful for the few detections it lists; it is not a timeliness claim.
