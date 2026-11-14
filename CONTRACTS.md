# CONTRACTS — exact handoff formats

Change a format only by agreeing with every consumer first. All example values are illustrative.

## 1. load -> detect: `data/stack_<tile>.nc`
xarray Dataset. Dims `(time, y, x)`. Vars `hh_db`, `hv_db` (float32, dB). CRS in attrs (`attrs["crs"]`). `time` is `datetime64`.
```json
{"dims": {"time": 6, "y": 512, "x": 512}, "data_vars": ["hh_db", "hv_db"], "dtype": "float32",
 "attrs": {"crs": "EPSG:32722", "tile": "T01"}, "time": ["2025-11-02", "2025-11-14"]}
```

## 2. detect -> validation/web: `web/data/detections.geojson`
Polygon features, EPSG:4326. Properties: `id:int`, `date:"YYYY-MM-DD"`, `area_ha:float`, `d_hh:float`, `d_hv:float`, `stage:"early"|"late"`.
Optional (nullable) properties: `first_hh_date:"YYYY-MM-DD"|null` (first date HH crossed its threshold), `first_hv_date:"YYYY-MM-DD"|null` (first date HV crossed its threshold). Consumers must handle them missing or `null`.
```json
{"type": "FeatureCollection", "features": [{"type": "Feature",
 "geometry": {"type": "Polygon", "coordinates": [[[-60.0, -3.0], [-59.99, -3.0], [-59.99, -3.01], [-60.0, -3.0]]]},
 "properties": {"id": 1, "date": "2025-11-14", "area_ha": 2.4, "d_hh": -3.1, "d_hv": -4.2, "stage": "early",
                "first_hh_date": "2025-11-02", "first_hv_date": null}}]}
```

## 3. detect -> web: `web/data/change_hh_<YYYY-MM-DD>.tif`, `change_hv_<YYYY-MM-DD>.tif`
Cloud-Optimized GeoTIFF, EPSG:4326, float32 dB difference (date minus baseline), < 20 MB each.
```json
{"file": "web/data/change_hh_2025-11-14.tif", "driver": "COG", "crs": "EPSG:4326", "dtype": "float32", "unit": "dB"}
```

## 4. validation -> web: `web/data/metrics.json`
`agreement` is patch-level agreement with the reference alerts, computed on the **holdout** split only. Alerts are a reference, not ground truth, hence the `_like` suffix. `precision` appears only under `hand_labeled` (n_unsure = labels marked unsure and excluded).
```json
{"agreement": {"precision_like": 0.0, "recall_like": 0.0, "f1_like": 0.0, "level": "patch", "split": "holdout"},
 "hand_labeled": {"n_sample": 0, "precision": 0.0, "n_unsure": 0},
 "n_detections": 0, "n_reference": 0,
 "tile": "T01", "dates": ["2025-11-14"], "reference_source": "RADD", "notes": ""}
```

## 5. validation -> web: `web/data/reference_alerts.geojson`
Same CRS (EPSG:4326). Properties: `source`, `date`.
```json
{"type": "FeatureCollection", "features": [{"type": "Feature",
 "geometry": {"type": "Polygon", "coordinates": [[[-60.0, -3.0], [-59.99, -3.0], [-59.99, -3.01], [-60.0, -3.0]]]},
 "properties": {"source": "RADD", "date": "2025-11-10"}}]}
```

## 6. detect -> web: `web/data/summary.json`
Per-date totals for the analysis panel. `tuning.split` describes how thresholds were chosen (tune vs holdout area/dates).
```json
{"dates": ["2025-11-02", "2025-11-14"],
 "per_date": [{"date": "2025-11-14", "n_detections": 12, "total_area_ha": 30.5, "early_ha": 20.1, "late_ha": 10.4}],
 "tuning": {"split": "tune: west half; holdout: east half", "hh_thresh": 2.0, "hv_thresh": 4.0}}
```
