# CLAUDE.md — shared team memory

## Project
sars-deforest: detect forest clearing from NISAR L-band GCOV backscatter (HH/HV) with a JJ-FAST-style change method, score it against public alerts (GLAD/RADD), and show it on a static MapLibre web map. NASA Space Apps 2026, "Dancing with the SARs".

## Folder ownership rule
Only edit files in your own folder. Read CONTRACTS.md before writing outputs.

## Owners
| Folder | Role | Owner |
|---|---|---|
| pipeline/load | Pipeline A | Max #1 |
| pipeline/detect | Pipeline B | Max #2 |
| validation | Validation | Pro #1 |
| web | Front end | Pro #2 |
| submission | Story | Go |

## Confirmed facts (fill in as verified; leave blank until then)
- AOI / tile:
- Track / frame:
- Dates used:
- HDF5 layer path, HH:
- HDF5 layer path, HV:
- CRS:
- Pixel spacing:
- Threshold HH (dB):
- Threshold HV (dB):
- Min detection size (ha):

## Data access notes
- Product: `NISAR_L2_GCOV_PROVISIONAL_V1`, via `earthaccess`.
- Earthdata Login credentials live in `~/.netrc`. Never commit them.
- Stream with `earthaccess` + `fsspec` + `xarray.open_datatree(..., engine="h5netcdf")`.
- Inspect the datatree to find layer paths. Never guess them; record them above once confirmed.
- Files are ~5 GB each: stream small windows only, never download whole files.

## Hard rules
- No simulated/fake images in the final submission.
- All placeholder data must be named `placeholder_*` and deleted before submission.
- Cite every source (see submission/sources.md).
- Do NOT claim: that this stops deforestation, how much carbon it saved, or that it works everywhere.

## Known limits
- Rain / soil moisture change backscatter and cause false alarms.
- Fire: double-bounce changes can mimic or mask clearing.
- Flooded forest causes false alarms (backscatter shifts).
- Selective logging is not detected.
- Tested on one area only.
