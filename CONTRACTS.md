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
```json
{"type": "FeatureCollection", "features": [{"type": "Feature",
 "geometry": {"type": "Polygon", "coordinates": [[[-60.0, -3.0], [-59.99, -3.0], [-59.99, -3.01], [-60.0, -3.0]]]},
 "properties": {"id": 1, "date": "2025-11-14", "area_ha": 2.4, "d_hh": -3.1, "d_hv": -4.2, "stage": "early"}}]}
```

## 3. detect -> web: `web/data/change_hh_<YYYY-MM-DD>.tif`, `change_hv_<YYYY-MM-DD>.tif`
Cloud-Optimized GeoTIFF, EPSG:4326, float32 dB difference (date minus baseline), < 20 MB each.
```json
{"file": "web/data/change_hh_2025-11-14.tif", "driver": "COG", "crs": "EPSG:4326", "dtype": "float32", "unit": "dB"}
```

## 4. validation -> web: `web/data/metrics.json`
```json
{"precision": 0.0, "recall": 0.0, "f1": 0.0, "n_detections": 0, "n_reference": 0,
 "tile": "T01", "dates": ["2025-11-14"], "reference_source": "RADD", "notes": ""}
```

## 5. validation -> web: `web/data/reference_alerts.geojson`
Same CRS (EPSG:4326). Properties: `source`, `date`.
```json
{"type": "FeatureCollection", "features": [{"type": "Feature",
 "geometry": {"type": "Polygon", "coordinates": [[[-60.0, -3.0], [-59.99, -3.0], [-59.99, -3.01], [-60.0, -3.0]]]},
 "properties": {"source": "RADD", "date": "2025-11-10"}}]}
```
