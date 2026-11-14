# web — Front end (Pro #2)

**Owner:** Front end.
**Reads (all from `web/data/`):** `detections.geojson`, `reference_alerts.geojson`, `change_hh_<date>.tif`, `change_hv_<date>.tif`, `metrics.json`, `summary.json`.
**Writes:** nothing. Static site, no build step.

```bash
cd web && python -m http.server 8000   # open http://localhost:8000 (file:// cannot fetch data)
```

## Libraries (pinned, from unpkg)
- MapLibre GL JS 5.9.0 (UMD build; MapLibre 6 is ESM-only).
- `@geomatico/maplibre-cog-protocol` 0.10.0 (MIT): a `cog://` protocol that reads Cloud-Optimized GeoTIFFs with HTTP range requests. Exposes the global `MaplibreCOGProtocol`; supports MapLibre 4.5, 5 and 6. The change layers are single-band float32 and are coloured by a custom colour function (blue = drop, red = rise, NaN transparent).
- Basemap: OpenFreeMap `liberty` style, no API key.
- COGs are read with HTTP range requests. `python -m http.server` ignores Range headers (checked: answers 200, not 206), so for the HH/HV change layers use a range-capable server, e.g. `cd web && npx http-server -p 8000` (checked: answers 206). The rest of the page works with either.
- Not yet verified: tile rendering of a real COG (no data exists yet). Checked: the layer is added or skipped correctly depending on whether the file exists.

## Config
`CONFIG` at the top of `app.js`: `center`, `zoom` (currently 0,0 / 2: the AOI is not set), `dataDir`, `changeRangeDb`.

## Missing files
Nothing is faked. Each missing file shows "data not loaded yet" in its own place (layer status, date label, accuracy panel, disturbance panel). A file that exists but is not valid JSON shows "<file> could not be read".

## Assumed file shapes (NOT in CONTRACTS.md yet: owners please confirm or correct)
CONTRACTS.md section 4 still lists the older flat `metrics.json` and has no `summary.json`. The panels were built to this shape:
```json
metrics.json: {"agreement": {"precision": 0, "recall": 0, "f1": 0, "n_detections": 0, "n_reference": 0},
               "hand_labeled": {"precision": 0, "n_sample": 0, "n_unsure": 0},   // or null -> "hand-labeled sample pending"
               "reference_source": "RADD", "dates": ["YYYY-MM-DD"], "notes": ""}
summary.json: {"n_detections": 0, "total_ha": 0, "early_ha": 0, "late_ha": 0,
               "by_date": [{"date": "YYYY-MM-DD", "early_ha": 0, "late_ha": 0}],
               "tuning_split": {"any": "keys", "shown": "as key/value rows"}}
```
Every field is optional; absent ones are skipped or shown as "?".

## Behaviour notes
- Date slider dates come from detections, `metrics.json` `dates` and `summary.json` `by_date`. Detections are shown up to the selected date; the HH/HV change layers show exactly that date's file.
- The accuracy caption is fixed: "Agreement with RADD/GLAD alerts, a reference, not ground truth."
