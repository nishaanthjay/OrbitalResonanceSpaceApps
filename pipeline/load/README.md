# pipeline/load — Pipeline A (Max #1)

**Reads:** NISAR_L2_GCOV_PROVISIONAL_V1 via earthaccess (small streamed windows only). Layer paths and AOI from `CLAUDE.md`.
**Writes:** `data/stack_<tile>.nc` (CONTRACTS.md section 1).

```bash
python pipeline/load/load.py --bbox W S E N --start YYYY-MM-DD --end YYYY-MM-DD --tile T01
```
Not implemented yet. Fill the confirmed HDF5 paths into CLAUDE.md as soon as you inspect the datatree.
