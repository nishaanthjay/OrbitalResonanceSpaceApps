# web — Front end (Pro #2)

**Owner:** Front end. One page: `explore.html` + `explore.js` (the radar explorer). Static site, no build step.
**Live site:** https://sars-deforest.vercel.app (Vercel Hobby; `vercel.json` serves `explore.html` at `/`). Deployed from this folder by `vercel deploy --prod`; Git auto-deploy is disconnected, so a push does not update the site.

```bash
cd web && npx http-server -p 8000   # open http://localhost:8000/explore.html (file:// cannot fetch data)
```

## What it reads
`data/explore/explore.json` and `data/explore/<id>/...` (per-date composite / HH / HV images, `series.bin` for the click time series). See `explore.js` for the exact files.

## Data files kept in `data/` for the submission (not read by the page)
`detections.geojson`, `reference_alerts.geojson`, `metrics.json`, `summary.json` (CONTRACTS.md sections 2, 4, 5, 6), `locations.json`, and the COGs in `data/<id>/` (EPSG:3857, written by `tools/export_layers.py`). The earlier map page that drew them (accuracy and disturbance panels, detection polygons, known-limits box) was removed on request; it is in git history before the commit "web: explore only".

## Libraries (pinned, from unpkg)
MapLibre GL JS 5.9.0 (UMD build; MapLibre 6 is ESM-only). Basemap: OpenFreeMap `liberty`, no API key.

## Deploying
```bash
cd web
npx vercel login                      # browser approval; the token stays on your machine
npx vercel link --yes --project sars-deforest   # then run `npx vercel git disconnect --yes` (link connects the GitHub repo)
npx vercel deploy --prod --yes
```
`.vercel/` and `.env*` are gitignored (`web/.gitignore`); never commit them.
