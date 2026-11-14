# pipeline/detect — Pipeline B (Max #2)

**Reads:** `data/stack_<tile>.nc` (CONTRACTS.md section 1), optional binary forest-mask GeoTIFF.
**Writes:** `web/data/detections.geojson` (features for the same date are replaced, other dates kept), `web/data/change_hh_<date>.tif`, `web/data/change_hv_<date>.tif` (CONTRACTS.md sections 2 and 3).

```bash
python pipeline/detect/detect.py --stack data/stack_T01.nc --date YYYY-MM-DD \
  --hh-thresh DB --hv-thresh DB --min-ha HA --forest-mask forest.tif
python -m pytest pipeline/detect     # synthetic in-memory tests only; needs: pip install pytest
```
Thresholds are positive dB magnitudes: HH rise >= `--hh-thresh` (early stage), HV drop >= `--hv-thresh` (late stage). Record the chosen values and min size in CLAUDE.md. Omitting `--forest-mask` prints a warning and skips masking (debug only).

## What the JJ-FAST papers say (and don't)
- Latest image vs the average of past images; early stage = HH increase (mean +1.2 dB in their example), late stage = HV decrease (mean -3.2 dB) (KC23).
- Thresholds were for ALOS-2 ScanSAR and are marked "Parameter is under adjusting" (KC25), so none are hardcoded.
- The papers do **not** say whether the average is in dB or linear power. We default to linear power (`--average linear`); `--average db` is the alternative.

## Open decisions for the team
1. **Baseline averaging domain** (linear vs dB): confirm on real data.
2. **Forest mask source** (not chosen here). Free candidates, verify current access/versions before use:
   - Hansen/UMD Global Forest Change (30 m treecover2000 + lossyear): Google Earth Engine asset or GeoTIFF tiles from the project page. Threshold tree cover and drop pixels already lost before the baseline.
   - ESA WorldCover (10 m, class 10 = tree cover): open AWS bucket `esa-worldcover` (anonymous), 2020/2021 epochs only.
   - JAXA PALSAR/PALSAR-2 global forest/non-forest map (25 m, yearly): free download from JAXA EORC (registration). Same L-band family JJ-FAST uses.
3. Thresholds (HH, HV) and `--min-ha`.

## Notes
- Detection area uses the real pixel spacing/CRS (geodesic area if the stack is in degrees).
- Tests use tiny synthetic arrays that live only in `test_detect.py`. They are never saved as data, never used in demos, and prove nothing about accuracy.
