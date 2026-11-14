# pipeline/detect — Pipeline B (Max #2)

**Reads:** `data/stack_<tile>.nc` (CONTRACTS.md section 1).
**Writes:** `web/data/detections.geojson`, `web/data/change_hh_<date>.tif`, `web/data/change_hv_<date>.tif` (sections 2 and 3).

```bash
python pipeline/detect/detect.py --stack data/stack_T01.nc --date YYYY-MM-DD --hh-thresh DB --hv-thresh DB --min-ha HA
```
Not implemented yet. Record chosen thresholds and min size in CLAUDE.md.
