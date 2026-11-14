# pipeline/load — Pipeline A (Max #1)

**Reads:** NISAR_L2_GCOV_PROVISIONAL_V1 via asf_search (metadata) + earthaccess (small streamed windows only). Needs `~/.netrc` with an Earthdata Login. Layer paths, AOI and window come from `CLAUDE.md` "Confirmed facts".
**Writes:** `data/stack_<tile>.nc` (CONTRACTS.md section 1): dims `(time, y, x)`, `hh_db` / `hv_db` float32 dB, native 20 m UTM grid, `attrs["crs"]` (also on each var, so `.rio.crs` works), `time` datetime64. **No multilook** here (`attrs["multilook"] = 1`); pipeline/detect multilooks in linear power. Pixels with power <= 1e-6 (outside swath) are NaN.

Python >= 3.13 (see requirements.txt).

```bash
# full Rondonia stack (9 dates, ~1000x1000 px, ~25 s per date)
python pipeline/load/load.py --bbox -62.8474 -9.3211 -62.6654 -9.1401 --start 2026-06-17 --end 2026-10-23 \
  --tile rondonia_t60f173 --track 60 --frame 173 --direction ASCENDING --mode 20+5
# small sample (first 2 dates)
python pipeline/load/load.py ... --tile rondonia_t60f173_sample --max-dates 2 --out-dir data/sample
python -m pytest pipeline/load   # in-memory tests only
```

Only one track / frame / direction / mode is combined, and every date must share the exact grid (it refuses otherwise; no resampling).

## AOI go/no-go scripts (metadata + small reads)
- `aoi_search.py`: per-candidate search, grouped by track/frame/direction/mode, dual-pol dates only.
- `inspect_granule.py URL`: truncated datatree of one granule.
- `time_window.py URL LON LAT`: CRS, spacing, and a timed 1000x1000 HH/HV read.
- `valid_map.py URL W S E N` / `common_valid.py`: where the swath has data in the bbox (one date / all dates).
