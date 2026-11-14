"""Blind sheet for the S Para hand-label check: 15 holdout + 15 tune detections + 15 stable-forest controls.

Reuses sample_points.py (one call per half), takes 8 controls from the holdout half and 7 from the tune half,
shuffles all 45 with make_blind. Writes validation/labels_blank.csv (point_id, lon, lat, label, notes) and the
key (id, sample_id, stratum, half, date, detection_id) to a gitignored path. Run from validation/ .
"""
import argparse
import json

from sample_points import make_blind, read_forest, sample_points, write_csv
from score import make_holdout

p = argparse.ArgumentParser()
p.add_argument("--detections", required=True)
p.add_argument("--stable-mask", required=True)
p.add_argument("--tune-bbox", type=float, nargs=4, required=True)
p.add_argument("--hold-bbox", type=float, nargs=4, required=True)
p.add_argument("--seed", type=int, required=True)
p.add_argument("--blank", required=True)
p.add_argument("--key", required=True)
a = p.parse_args()
det = json.load(open(a.detections, encoding="utf-8"))
rows = []
for half, bbox, n_ctrl in (("holdout", a.hold_bbox, 8), ("tune", a.tune_bbox, 7)):
    ho = make_holdout(bbox, None)
    forest, t, crs = read_forest(a.stable_mask, bbox)
    s = sample_points(det, forest, t, crs, 15, a.seed, ho)
    d = [r for r in s if r["stratum"] == "detection"]
    c = [r for r in s if r["stratum"] == "non_detection"][:n_ctrl]
    for r in d + c:
        r["id"] = f"{half[0].upper()}{r['id']}"
        r["half"] = half
    rows += d + c
sheet, key = make_blind(rows, "2026-06-26", "2026-10-12", a.seed)
by = {r["id"]: r["half"] for r in rows}
for k in key:
    k["half"] = by[k["sample_id"]]
write_csv(sheet, a.blank, ["id", "lon", "lat", "before_date", "after_date", "label", "notes"])
write_csv(key, a.key, ["id", "sample_id", "stratum", "half", "date", "detection_id"])
print(len(sheet), "points; seed", a.seed)
