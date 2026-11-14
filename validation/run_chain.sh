#!/bin/zsh
# Validation chain on one stack, rules as written in data/REPORT.md before any sweep (Pro #1):
#   split   north / south halves of the window, 1 km buffer strip on the centre latitude (tune = north)
#   rule    per channel, smallest threshold in {1,1.5,2,2.5,3,3.5,4,5,6} dB with <= 1 % of TUNE-half stable forest
#           firing, pooled over the scored dates (validation/noise_floor.py); holdout never used to choose
#   detect  5x5 multilook, --min-ha 2, sweep on tune (record only), one --final run
#   score   holdout only, each source once: tolerance 24 d, any overlap; primary --merge-dates --min-ref-ha 1,
#           secondary = contract-default patches; blind label sheet (15 + 15) with a separate key
#
# usage: validation/run_chain.sh STACK "W S E N" "D1 D2 ..." OUT_DIR TILE
#   STACK: stack NetCDF; "W S E N": the analysis window; dates: the scored dates (each needs >= 2 earlier dates);
#   OUT_DIR: holds alerts_glad_{l,s2}.json, forest_mask.tif, stable_forest.tif (fetch_alerts.py, build_masks.py)
#   and receives every output; TILE: tile name for metrics.json. Run from the repo root.
set -e
PY=${PY:-~/code/nasa/.venv/bin/python}
STACK=$1; BBOX=(${=2}); DATES=(${=3}); OUT=$4; TILE=$5
read -r -A TUNE <<< "$($PY -c "w,s,e,n=$BBOX[1],$BBOX[2],$BBOX[3],$BBOX[4]; c=(s+n)/2; print(w, round(c+0.0045,4), e, n)")"
read -r -A HOLD <<< "$($PY -c "w,s,e,n=$BBOX[1],$BBOX[2],$BBOX[3],$BBOX[4]; c=(s+n)/2; print(w, s, e, round(c-0.0045,4))")"
echo "tune $TUNE | holdout $HOLD | dates $DATES"
MASKS=(--forest-mask $OUT/forest_mask.tif --stable-mask $OUT/stable_forest.tif)
SPLIT=(--tune-bbox $TUNE --holdout-bbox $HOLD)
LOG=$OUT/detect_log_$TILE.json

echo "== 1. noise floor (tune half chooses; holdout half printed as a diagnostic only)"
$PY validation/noise_floor.py --stack $STACK --stable-mask $OUT/stable_forest.tif --region-bbox $TUNE --date $DATES \
  --out $OUT/noise_floor_tune.json 2>/dev/null | tee $OUT/noise_floor_tune.txt
$PY validation/noise_floor.py --stack $STACK --stable-mask $OUT/stable_forest.tif --region-bbox $HOLD --date $DATES \
  --out $OUT/noise_floor_holdout.json 2>/dev/null > $OUT/noise_floor_holdout.txt
HH=$($PY -c "import json; print(json.load(open('$OUT/noise_floor_tune.json'))['cfar']['hh_thresh'])")
HV=$($PY -c "import json; print(json.load(open('$OUT/noise_floor_tune.json'))['cfar']['hv_thresh'])")
# detect.py accepts a non-positive threshold and then fires almost everywhere (data/REPORT.md section 6)
$PY -c "import sys; v=[float(x) for x in ('$HH','$HV')]; sys.exit(0 if all(x > 0 for x in v) else 'threshold must be > 0 dB')"
echo "rule picks HH=$HH HV=$HV dB"

echo "== 2. sweep on the tune half (record only)"
$PY -W ignore pipeline/detect/detect.py --stack $STACK --date $DATES --min-ha 2 $MASKS $SPLIT \
  --sweep-hh 1 1.5 2 2.5 3 3.5 4 5 6 --sweep-hv 1 1.5 2 2.5 3 3.5 4 5 6 --log $LOG > $OUT/sweep_tune.txt
echo "== 3. one --final run (both halves; only the holdout half is scored)"
$PY -W ignore pipeline/detect/detect.py --stack $STACK --date $DATES --hh-thresh $HH --hv-thresh $HV --min-ha 2 \
  $MASKS $SPLIT --final --out-dir $OUT/final --log $LOG | tee $OUT/final_run.txt
$PY -m pytest -q pipeline/detect validation 2>&1 | tail -1 | tee $OUT/tests.txt

echo "== 4. score the holdout half, once per source"
for SRC in GLAD-L GLAD-S2; do
  f=${${SRC:l}/-/_}
  mkdir -p $OUT/score_$f $OUT/score_${f}_secondary
  $PY -W ignore validation/score.py --detections $OUT/final/detections.geojson --source $SRC \
    --reference-file $OUT/alerts_$f.json --holdout-bbox $HOLD --tolerance-days 24 --overlap-threshold 0 \
    --merge-dates --min-ref-ha 1 --tile $TILE --lag-table $OUT/score_$f/lag.csv --out-dir $OUT/score_$f \
    | tee $OUT/score_$f/stdout.txt
  $PY -W ignore validation/score.py --detections $OUT/final/detections.geojson --source $SRC \
    --reference-file $OUT/alerts_$f.json --holdout-bbox $HOLD --tolerance-days 24 --overlap-threshold 0 \
    --tile $TILE --out-dir $OUT/score_${f}_secondary | tee $OUT/score_${f}_secondary/stdout.txt
done

echo "== 5. blind label sheet (holdout half)"
FIRST=$($PY -c "import xarray as xr, numpy as np; print(str(np.datetime64(xr.open_dataset('$STACK').time.values[0], 'D')))")
$PY -W ignore validation/sample_points.py --detections $OUT/final/detections.geojson --forest-mask $OUT/forest_mask.tif \
  --seed 20261114 --holdout-bbox $HOLD --blind $FIRST $DATES[-1] --out $OUT/label_sheet.csv --key $OUT/label_key.csv
