
## Agent C (alerts)
- Fetched GLAD-L (alert26/alertDate26, plus alert25/alertDate25 since cheap) and GLAD-S2 windows for bbox -55.30 -8.45 -52.43 -5.78 (tile 060W_10S_050W_00N) via fetch_alerts.read_window; saved as deflate GeoTIFFs in data/final_frame/ (gitignored) with README.txt. Total ~103 MB, 119 s, no network retries needed.
- Choice: raster windows instead of row-JSON (S2 has 75.7M alert pixels). Reader: validation/fetch_alerts_frame.read_saved(source, dir); GLAD-L reads 2026 layers only, a>0 and d>0, as scale.read_alerts.
- Test (validation/test_fetch_alerts_frame.py): synthetic check plus identical output vs scale.read_alerts on the 20 km window (GLAD-L 45312 px, GLAD-S2 1087012 px).
- Counts: GLAD-L 2026 1,023,460 alert px (0 undated, 2026-01-01..2026-11-10, 606,163 dated 2026-07-20..10-12); GLAD-L 2025 466,902; GLAD-S2 75,688,881 (0 undated, 2019-01-02..2026-11-13, 1,376,177 in window).

## Agent B (Hansen)
- Built `data/forest_mask_frame_t2f174.tif` (3.65 MB, uint8 1 forest/0 not, nodata tag 255 as in forest_mask.py, deflate, EPSG:32722, 14095 x 15130 px at 20 m) with `python pipeline/load/forest_mask.py --grid-from 32410 9353930 3026 2819 --subdivide 5 --out data/forest_mask_frame_t2f174.tif`. Choice: new `--grid-from` / `build_grid()` (no stack needed), streamed in 1000-row strips, retry x5 on network errors, per-strip tile mosaic (max of layers) so multi-tile grids work; `build()` and the `--stack` CLI are unchanged. Reason: stack did not exist yet.
- Tile: 00N_060W only. Forest fraction 80.36 %, loss 2001-2025 18.45 %. 58 s.
- Grid check (scale.py condition) against computed block centres: shape == (ny*5, nx*5), x[2::5] and y[2::5] equal block centres: True. Not re-checked against the real stack (absent).
- Test: pipeline/load/test_forest_mask.py (synthetic only).

## Agent A (stream)
- Tiles: 3 x 3 grid, nx 5050,5050,5030, ny 4700,4700,4695 freqA px (all multiples of 5); x0 = 32370, 133370, 234370; y0 = 9353970, 9259970, 9165970 (all on the granule grid; load_big accepted every one). Names frame_t{row}_{col}, `--out-dir data/tiles_frame`. Smoke test: tile t0_0 alone, all 9 dates found (2026-06-26, 07-08, 07-20, 08-13, 08-25, 09-06, 09-18, 09-30, 10-12), 328 s. Then the other 8 with 3 processes at a time (xargs -P 3); the session was interrupted once mid-run, the running tile processes were left alone and finished.
- Per-tile wall time (s): t0_0 328, t0_1 365, t0_2 344, t1_0 399, t1_1 390, t1_2 391, t2_0 372, t2_1 464, t2_2 409. Total wall for all 9 tiles 1569 s (26 min). Retries: 0 (no 403, no memory deaths; each process peaked ~3 GB, 3 at a time was fine). So no reduction to 2 processes.
- Merge: `cd pipeline/load && python merge_tiles.py --tiles-dir ../../data/tiles_frame --out ../../data/stack_frame_t2f174.nc` (refuses on date mismatch, non-100 m spacing, gap/overlap; test_merge_tiles.py on synthetic arrays passes). Choice: window_first_pixel_xy / window_pixels_nx_ny recomputed from the merged block coordinates (block centre -/+ 40 m, blocks x 5); other attrs copied from the tiles.
- Result: data/stack_frame_t2f174.nc, 307,588,009 bytes, sha256 a6347a7e537aad74cd040f555f640504b4bd1fde9520822efa04a6786924e0de. Shape (9, 2819, 3026), float32, x[0]=32410, y[0]=9353930, x[-1]=334910, y[-1]=9072130, steps exactly 100 m, 9 dates exact. attrs: crs EPSG:32722, multilook 5, window_first_pixel_xy [32370, 9353970], window_pixels_nx_ny [15130, 14095], tile frame_t2f174.
- Valid (finite HV) per date 06-26..10-12: 70.2, 70.2, 72.1, 70.2, 70.2, 70.2, 70.2, 70.2, 70.2 %; valid on all 9 dates 69.3 % (5,910,947 of 8,530,294 blocks = 2819 x 3026).
- data/tiles_frame deleted after this verification.
