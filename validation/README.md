# validation — Validation (Pro #1)

**Reads:** `web/data/detections.geojson` (section 2) and GLAD/RADD alerts.
**Writes:** `web/data/reference_alerts.geojson` (section 5), `web/data/metrics.json` (section 4).

```bash
python validation/score.py --source RADD --bbox W S E N --dates YYYY-MM-DD --tolerance-days N --tile T01
```
Not implemented yet. Document the matching rule and cite the alert source.
