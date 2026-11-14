# web/tools — layer export (Pro 2, Web)

`export_layers.py` turns a load stack into the per-date radar layers the map shows.

**Reads:** `data/stack_<tile>.nc` (CONTRACTS.md section 1) and the forest mask on the same grid (`data/forest_mask_<tile>.tif`, from `pipeline/load/forest_mask.py`).
**Writes:** `web/data/<id>/composite_<date>.tif` (RGB: R = HH, G = HV, B = HH - HV in dB), `hh_<date>.tif`, `hv_<date>.tif` (grayscale), and merges an entry into `web/data/locations.json`.

```bash
python web/tools/export_layers.py --stack data/stack_spara_t2f174.nc --forest-mask data/forest_mask_spara_t2f174.tif \
  --id spara --name "S Para, BR (Novo Progresso)" --compress JPEG --out-dir web/data --notes "..."
# subset of dates (e.g. only the good Rondonia dates from CLAUDE.md):
python web/tools/export_layers.py ... --id rondonia --dates 2026-08-17 2026-08-29 2026-09-10 2026-10-04 2026-10-16
```

## Format
- **Cloud-Optimized GeoTIFF in EPSG:3857**, Google Maps tiling scheme, 256 px blocks, overviews. CONTRACTS.md section 3 says EPSG:4326 for the detect change COGs, but `maplibre-cog-protocol` (the viewer) does not reproject and rejects any CRS other than 3857 (its README, "COG generation tips"), so these layers are 3857.
- uint8, 0 = no data (swath edges and padding are transparent), valid values 1..255.
- `--compress JPEG` (default quality 85) is lossy but about 3x smaller than DEFLATE for speckled radar (S Para: 21 MB vs about 63 MB for 9 dates). Transparency is stored as a lossless mask band. Grayscale layers are stored as three identical bands because GDAL drops the mask on a 1-band JPEG source. `--compress DEFLATE` is lossless.
- Coordinates in the stack are treated as pixel centres (the rioxarray convention used by the rest of the pipeline).

## One fixed stretch
Per channel, the lo/hi dB are percentiles (default 2 and 98) of the stable-forest pixels (forest mask) pooled over every exported date, so brightness is comparable across dates. The values are written to `locations.json` under `stretch` for the legend. The stretch depends on which dates are exported (excluded dates never influence it).

## Size budget
All of `web/data/` must stay under 60 MB (Vercel Hobby limit is 100 MB for a CLI upload). The script prints the size of every file and the total.

Known cosmetic issue: on this machine Python 3.14 prints "Error in sys.excepthook" at interpreter exit after a successful run (exit code 0, all files written); cause not investigated.
