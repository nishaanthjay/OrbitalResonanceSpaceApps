# sars-deforest

Detect forest clearing from NISAR L-band GCOV backscatter (HH/HV) with a JJ-FAST-style change method, score it against public alerts (GLAD/RADD), and show it on a static MapLibre web map. NASA Space Apps 2026, "Dancing with the SARs". Skeleton only: the science is not implemented yet.

## Quickstart
```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```
Earthdata Login: create an account at https://urs.earthdata.nasa.gov, then put this in `~/.netrc` (Windows: `~/_netrc`). Never commit it.
```
machine urs.earthdata.nasa.gov login YOUR_USER password YOUR_PASSWORD
```
View the map: `cd web && python -m http.server 8000`, open http://localhost:8000.

## Repo map
- `pipeline/load/` stream NISAR GCOV windows -> `data/stack_<tile>.nc`
- `pipeline/detect/` change detection -> `web/data/*`
- `validation/` score detections vs GLAD/RADD -> `web/data/metrics.json`
- `web/` static MapLibre map
- `submission/` write-up, video script, sources
- `CLAUDE.md` team memory; `CONTRACTS.md` handoff formats

## Team
| Folder | Role | Owner |
|---|---|---|
| pipeline/load | Pipeline A | Max #1 |
| pipeline/detect | Pipeline B | Max #2 |
| validation | Validation | Pro #1 |
| web | Front end | Pro #2 |
| submission | Story | Go |

## License
MIT, see LICENSE.

## Sources
- https://nisar-docs.asf.alaska.edu/earthaccess/
- https://nisar-docs.asf.alaska.edu/asf-search/
- https://www.eorc.jaxa.jp/ALOS/en/kyoto/jan2018_kc24/pdf/3-01_KC24_Watanabe_TDU.pdf
- https://www.eorc.jaxa.jp/ALOS/jp/activity/kyoto/pdf/3-01_KC25_Watanabe.pdf
- https://www.eorc.jaxa.jp/ALOS/en/kyoto/jan2017_kc23/pdf/2-07b_KC23_JJ-FAST_Watanabe.pdf
- https://www.eorc.jaxa.jp/ALOS/jp/activity/kyoto/pdf/1-07_PKC1_Watanabe.pdf
