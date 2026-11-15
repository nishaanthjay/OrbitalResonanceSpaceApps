# web — Front end (Pro #2)

**Owner:** Front end. One page: `explore.html` + `explore.js` (the radar explorer). Static site, no build step.
**Live site:** https://sars-deforest.vercel.app (Vercel Hobby; `vercel.json` serves `explore.html` at `/`). Deployed from this folder by `vercel deploy --prod`; Git auto-deploy is disconnected, so a push does not update the site.

```bash
cd web && npx http-server -p 8000   # open http://localhost:8000/explore.html (file:// cannot fetch data)
```

## What it reads
- Radar views 1 to 3: `data/explore/explore.json` and `data/explore/<id>/...` (per-date composite / HH / HV images, `series.bin` for the click time series).
- View 4 and Results (S Para only; hidden for Rondonia), all files already in `data/`:
  - `detections.geojson`: 157 patches (id, first_date, stage early/late, area_ha, split, hh_series_db, hv_series_db). Drawn from their `first_date` on, coloured by stage. Clicking one draws its 9-value HH/HV series (full precision, 5x5 multilook patch means) with the title "Detection <id>: <area_ha> ha, first seen <first_date>, <split> half" (`buffer` reads "buffer strip"); a detection click takes priority over the plain map click, which keeps the `series.bin` chart.
  - `reference_alerts.geojson`: GLAD-L event outlines, drawn from their `date` on.
  - `explore/spara/hansen_loss.webp` + `hansen_loss.json`: Hansen loss 2021 to 2025 as an image on the radar image's corners (same grid), legend colours from the json.
  - `metrics.json`: the failed first attempt (1 dB detector) in the Validation section (`#results`, rendered by `observatory.js`): agreement shown only if `agreement.split === "holdout"` (counts = precision_like x n_detections, recall_like x n_reference). The hand-check line (`#hand-check`, marked `HUMAN-RELABEL` in `explore.html`) is computed from `hand_labeled`: usable = n_sample - n_unsure, cleared = precision x usable; it names the AI labeller until an independent human re-label replaces it.
  - `explore/headline.json`: numbers that exist only in `validation/` (20 km holdout and Rondonia forest-map counts from `fnf_metrics.json`, `T_db`, tune blocks, the 92.5 % GLAD-L-on-prior-clearing row and detector diagnostics from `results_final.md`), each with its source file and field path. Never hand-type numbers into the HTML; add them here with their source.
  - Headline facts band (`#facts`), "The forest map at three scales" (`#scales`), validation tables (`#val-forest`, `#val-enrich`), limitations and the story (`#story`) are rendered by `observatory.js` from `headline.json`, `big/big.json`, `frame/frame.json`, `big/cloud.json` and `metrics.json` at load, independent of the map's `load` event. Non-forest precision / recall = tn/(tn+fn), tn/(tn+fp) from the confusion counts.
- If a file fails to load, only that item shows "pending" (its checkbox is disabled); everything else keeps working. File text is rendered as plain text, never HTML.
- Not read by the page: `summary.json`, `locations.json`, and the COGs in `data/<id>/`.

## Libraries (pinned, from unpkg)
MapLibre GL JS 5.9.0 (UMD build; MapLibre 6 is ESM-only). Basemap: OpenFreeMap `dark`, recoloured to the page palette, no API key. Fonts: Manrope + IBM Plex Mono (Google Fonts).

## Layout
The page opens on the radar itself: a full-screen hero over the tinted HV image, a pass rail (one tick per date) and a glass strip (cards, play). "Explore" or a map click switches to the explorer: tint off, map gestures on, controls panel slides in (location, layers, evidence overlays, click chart, 60 km results). Esc or "Intro" goes back. Below it: Compare, Detection, Analysis, Validation (`observatory.js`). Styles in `observatory.css`; motion respects `prefers-reduced-motion`.

## Cinematic layer (`cinema.js`, `cinema.css`)
Presentation only, on top of `explore.js` (it uses its globals; `explore.js` exposes two hooks: `state.cinema` pauses `fit()`, and the `explore:ready` event fires after the data loads, also on failure).
- **Globe fly-in:** globe projection, slow spin while the data loads, then Amazon, Pará, frontier; the radar fades in under the hero. "Skip intro", Esc, a click or a scroll skips it. Plays once per tab session; never with `prefers-reduced-motion` or when the page opens on a section link (`#compare` etc.).
- **3D** (map control "3D"): terrain from the free Mapzen / AWS Terrain Tiles (terrarium encoding, attributed on the map), pitch 62°. On the 60 km map the lost patches (`big/lost.geojson`) rise as columns: height = patch area, colour = `first_switch_date` (legend from `big.json` `first_switch.legend`).
- **Frontier clock** (`#frontier`): the 9 per-pass 60 km forest maps cross-fading, plus a forest-share sparkline. The shares are counted in the browser from the lossless `forest_<date>.webp` layers, over display pixels valid on all 9 passes; nothing new is stored.
- **Next-pass countdown:** last pass in `big.json` + 12-day steps, labelled "planned repeat cycle, not a confirmed acquisition". Day precision only (no acquisition time is known).
- **Optical vs radar** (`#optical-radar`): swipe between a Sentinel-2 image and the radar forest map for the same pass, plus a dual timeline from `big/cloud.json`. The images come from `data/explore/optical/` (Max B). Until that exists the page shows "pending" and the nearest scene's clear share from `cloud.json`. Expected `optical/optical.json`: `{"passes": [{"nisar_date": "2026-06-26", "scene_id": "...", "date": "2026-06-29", "cloud_pct": 13.9, "file": "optical_2026-06-26.webp"}, {"nisar_date": "...", "scene_id": null, "note": "no scene within 6 days"}]}`, images on the same EPSG:3857 grid as `big/forest_median.webp`. While the folder is missing, the browser logs one 404 for `optical.json`.
- **Threat board** (`#threats`): the FUNAI areas from `big/big_protected.json`, ranked by lost hectares, with the outside-all-areas rate for comparison. Also the 20 `watch_priorities` from `big.json`, each with a 3.2 km mini time-lapse cut from the per-pass forest maps (patch outlined) and fly-to.
- **Tour** (header button): about 60 s through the above for the screen recording. Captions take their numbers from the data files. Stop with the button or Esc.
- Location switcher: the panel's location menu and the hero cards list S Para 20 km, the 60 km map and the full frame. Each appears only when its files load.

- **Optical vs radar** (`#optical-radar`): if `explore/optical/optical.json` is missing (it is today; the 404 on that probe is expected), the Sentinel-2 image half and the two-satellite framing are hidden and only the cloud timeline shows, titled "Cloud over the same 60 km, June to October".

## Deploying
```bash
cd web
npx vercel login                      # browser approval; the token stays on your machine
npx vercel link --yes --project sars-deforest   # then run `npx vercel git disconnect --yes` (link connects the GitHub repo)
npx vercel deploy --prod --yes
```
`.vercel/` and `.env*` are gitignored (`web/.gitignore`); never commit them.

## Phase 2 environmental investigation

`environment.js`, `evidence-core.js` and `environment.css` add the Environmental Evidence section and a nonmodal patch investigation panel. The panel opens from real map/patch selections and the existing area-ranked watchlist example. It shows shipped radar values, dated Sentinel-2 crops, the existing alert-product category and environmental availability. The optical archive now contains nine dated images; older notes above about its absence describe the fallback, not the current data state.

`data/environment/access.json` contains an actual NASA access audit, not environmental measurements: IMERG and SMAP catalog discovery succeeded, but science-file requests returned HTTP 401. No FIRMS key was supplied. Charts and fire controls stay unavailable until quality-screened files are explicitly registered. No sample measurements are shipped. See [tools/ENVIRONMENT.md](tools/ENVIRONMENT.md) for account setup, schemas, quality notices, processing and registration.

The new map hooks are `evidence:selection` and `evidence:map-date`. Tour hooks reveal the investigation only during its evidence step and close it on completion. Existing cinematic features and frozen scientific rules remain in place. Run `node --test web/tools/test_evidence.cjs web/tools/test_environment_ui.cjs` from the repository root, plus `python -m unittest discover -s web/tools -p test_environment_data.py -v`.
