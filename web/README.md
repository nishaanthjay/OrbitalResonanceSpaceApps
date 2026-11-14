# web — Front end (Pro #2)

**Reads:** `web/data/detections.geojson`, `change_hh_<date>.tif`, `change_hv_<date>.tif`, `metrics.json`, `reference_alerts.geojson`.
**Writes:** nothing; static site (MapLibre GL JS 5.9.0 from unpkg, OpenFreeMap basemap, no API key).

```bash
cd web && python -m http.server 8000   # open http://localhost:8000
```
Missing data files show a "data not loaded yet" message; do not add fake data.

TODO: GeoTIFF change layers need a COG renderer (e.g. a maplibre-cog protocol plugin) and the date list. Both are left as stubs in app.js.
