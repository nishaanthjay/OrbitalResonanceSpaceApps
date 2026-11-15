# Frame run log (full NISAR frame, track 2 frame 174)

## Summary (2026-11-14, overnight run)
**Finished:** PREREG_frame.md committed before streaming/scoring (be9cd05); frame streamed (9 tiles, 1569 s, no retries) and merged to data/stack_frame_t2f174.nc (3026 x 2819 blocks, sha256 in CLAUDE.md "Frame stack"); Hansen mask (80.4 % forest); GLAD-L/S2 rasters; scored ONCE (no crash rerun) -> validation/frame_metrics.json; results_final.md section "Forest map, full frame"; web layers in web/data/explore/frame/ (9.7 MB; web/data 66 MB); pytest 100 passed. Not deployed to Vercel.
**Headline numbers** (all from frame_metrics.json; T_db -11.25 fixed):
- Scored 5,711,743 blocks (57,117 km2) after excluding the 60 km box (contains the 20 km window); 69.3 % of the rectangle valid on all 9 dates.
- Median forest map vs Hansen: OA 0.926 vs all-forest baseline 0.862; kappa 0.719; forest precision/recall 0.977/0.936; non-forest precision/recall 0.683/0.862. Single dates 0.826-0.907 (2026-10-12, 0.826, is below the baseline).
- Lost blocks 240,178 (4.20 % of scored). GLAD-L: precision_like 0.0334 (control 0.0013), recall_like 0.113 (control 0.0032). GLAD-S2: precision_like 0.0429 (control 0.0071), recall_like 0.128 (control 0.0212). About 96 % of lost blocks have no alert: radar-only, unconfirmed, not called deforestation.
**Failed / caveats:** nothing failed. The web lost.geojson keeps only patches >= 3 ha (17,658 of 153,341; counts in frame.json). Hansen is a 2000-2025 map, so part of the disagreement is real change. Final `python validation/frame.py` printed a harmless "Error in sys.excepthook" at interpreter exit (rc 0, metrics written). Empty dir data/tiles_frame may remain (held by a shell).


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

## Agent E (checks)
- pytest `pipeline validation web/tools` together: 100 passed, no collection clash.
- web/data: 57M before frame; first measure 113M (lost.geojson 58.5 MB), final measure explore/frame 8.7M (lost.geojson 8.9 MB) so web/data ~66M. explore/big 1.9M, rondonia 7.8M, spara 15M.
- results_final.md "Forest map, full frame" numbers all match frame_metrics.json at printed precision; stack size/sha256 and valid-per-date match fresh computation. Caveat: window (40,284) is contained in the 60 km box (199,204); scored = 5,910,947 - 199,204.
- No "deforestation" used for radar-only blocks.

## Agent D (web layers)
- Built `web/tools/make_frame.py` (+ `test_make_frame.py`, synthetic only) -> `web/data/explore/frame/` (forest_median.webp, lost.webp, first_switch.webp, lost.geojson, frame.json). Reuses make_big (classes/rgba/save_webp), scale.lost_rule, frame.first_switch_index, frame.box60_mask, fetch_alerts_frame.read_saved, scale.block_index/alert_blocks. frame.run() not called; frame_metrics.json only read, 'scores' = json load/dump copy (checked equal).
- Check: derived lost over scored area (valid, minus 20 km window and 60 km box) = 240178 == frame_metrics loss_rule.lost_blocks, asserted before writing. Layers draw all valid lost blocks (244,796 incl. window/box).
- Grid: one EPSG:3857 grid 3034 x 2847 px (rasterio default transform, nearest, lossless RGBA webp), factor 1 (no downsampling needed: images total ~0.73 MB).
- Choice: patch hv_series_db = mean of block dB (as asked), not the linear-power mean make_big uses. Patches via ndimage.label (8-connected) + rasterio shapes (block outline, no smoothing), one pass over label image instead of per-patch loops (153k patches). Coordinates WGS84, 5 decimals.
- Choice: lost colour #ff2bd6 (magenta, distinct from forest/non-forest); first_switch legend = viridis 9 samples, one per date (lost blocks only use indices 2..7).
- Alert window for category: 2026-06-26..2026-11-05 (REF_START-24 d .. REF_END+24 d), GLAD-L or GLAD-S2, any block of patch.
- REDUCTION: full lost.geojson (153,341 patches: 5,584 alert_supported, 147,757 radar_only_unconfirmed) exceeded the 15 MB folder limit (>15 MB alone), so patches < 3 ha were dropped: 17,658 kept (1,560 alert_supported, 16,098 radar_only_unconfirmed), lost.geojson 8.9 MB. Images stay full-res; the dropped small patches are still visible in lost.webp / first_switch.webp. Recorded in frame.json counts.
- Sizes: folder 9.7 MB; `du -sh web/data` = 66M (was 57M).
