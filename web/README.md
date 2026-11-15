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
  - `metrics.json`: Results panel. Agreement is shown only if `agreement.split === "holdout"`, under the fixed caption "Agreement with GLAD-L alerts on the held-out south half: a reference, not ground truth." Shows precision_like, recall_like, n_detections, n_reference; `hand_labeled: null` shows "Hand-checked precision: pending". Missing or non-numeric fields are listed by name; a `reference_source` other than GLAD-L is flagged.
- If a file fails to load, only that item shows "pending" (its checkbox is disabled); everything else keeps working. File text is rendered as plain text, never HTML.
- Not read by the page: `summary.json`, `locations.json`, and the COGs in `data/<id>/`.

## Libraries (pinned, from unpkg)
MapLibre GL JS 5.9.0 (UMD build; MapLibre 6 is ESM-only). Basemap: OpenFreeMap `dark`, recoloured to the page palette, no API key. Fonts: Manrope + IBM Plex Mono (Google Fonts).

## Layout
The page opens on the radar itself: a full-screen hero over the tinted HV image, a pass rail (one tick per date) and a glass strip (cards, play). "Explore" or a map click switches to the explorer: tint off, map gestures on, controls panel slides in (location, layers, evidence overlays, click chart, 60 km results). Esc or "Intro" goes back. Below it: Compare, Detection, Analysis, Validation (`observatory.js`). Styles in `observatory.css`; motion respects `prefers-reduced-motion`.

## Deploying
```bash
cd web
npx vercel login                      # browser approval; the token stays on your machine
npx vercel link --yes --project sars-deforest   # then run `npx vercel git disconnect --yes` (link connects the GitHub repo)
npx vercel deploy --prod --yes
```
`.vercel/` and `.env*` are gitignored (`web/.gitignore`); never commit them.
