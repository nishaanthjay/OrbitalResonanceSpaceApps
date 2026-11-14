"""Precision of the hand-labeled sample: reads the filled CSV from sample_points.py, updates metrics.json.

Labels: clearing | no_clearing | unsure (see validation/README.md). "unsure" rows are excluded and counted.
Writes metrics.json "hand_labeled" = {n_sample, precision, n_unsure} (CONTRACTS.md section 4) for the detection
stratum; the non-detection stratum is printed only (it is not part of the contract).
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os

LABELS = ("clearing", "no_clearing", "unsure")


def read_rows(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def join_key(sheet: list[dict], key: list[dict]) -> list[dict]:
    """Blind sheet (sample_points.py --blind) + its key -> rows with a stratum. The ids must match one to one."""
    sheet = [{**r, "id": r.get("id") or r["point_id"]} for r in sheet]  # labels_blank.csv names it point_id
    by_id = {k["id"]: k for k in key}
    if set(by_id) != {r["id"] for r in sheet} or len(by_id) != len(sheet):
        raise ValueError("sheet and key ids do not match one to one; wrong key file?")
    return [{**r, "stratum": by_id[r["id"]]["stratum"], "half": by_id[r["id"]].get("half", "")} for r in sheet]


def _stratum(rows: list[dict]) -> dict:
    labels = [r["label"] for r in rows]
    yes, no, unsure = labels.count("clearing"), labels.count("no_clearing"), labels.count("unsure")
    return {"n": len(rows), "clearing": yes, "no_clearing": no, "n_unsure": unsure,
            "fraction_clearing": yes / (yes + no) if yes + no else None}


def wilson_95(k: int, n: int) -> tuple[float, float] | None:
    """95 % Wilson score interval for k successes in n (z = 1.96); None if n = 0."""
    if n == 0:
        return None
    z, p = 1.96, k / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, c - h), min(1.0, c + h)


def compute_sample_precision(rows: list[dict]) -> dict:
    """Detection stratum: precision = clearing / (clearing + no_clearing), unsure excluded and counted.

    Every row must carry a label from LABELS (case and surrounding spaces ignored); empty or unknown labels
    raise ValueError listing the row ids, so a half-labeled file is never scored.
    """
    bad = []
    for r in rows:
        r["label"] = {"cleared": "clearing", "not_cleared": "no_clearing"}.get(
            (r.get("label") or "").strip().lower(), (r.get("label") or "").strip().lower())
        if r["label"] not in LABELS:
            bad.append(r.get("id"))
    if bad:
        raise ValueError(f"rows without a valid label ({', '.join(LABELS)}): {bad}")
    det = _stratum([r for r in rows if r["stratum"] == "detection"])
    non = _stratum([r for r in rows if r["stratum"] == "non_detection"])
    return {
        "hand_labeled": {"n_sample": det["n"], "precision": det["fraction_clearing"], "n_unsure": det["n_unsure"]},
        "detection": {**det, "wilson_95": wilson_95(det["clearing"], det["clearing"] + det["no_clearing"])},
        "non_detection": {**non, "wilson_95": wilson_95(non["clearing"], non["clearing"] + non["no_clearing"])},
    }


def write_hand_labeled(metrics_path: str, hand_labeled: dict) -> None:
    """Set only the "hand_labeled" block of an existing metrics.json (score.py writes the rest)."""
    with open(metrics_path, encoding="utf-8") as f:
        m = json.load(f)
    m["hand_labeled"] = hand_labeled
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(m, f, indent=1)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--csv", required=True, help="filled CSV from sample_points.py")
    p.add_argument("--key", help="key CSV, when --csv is a blind sheet from sample_points.py --blind")
    p.add_argument("--metrics", default="web/data/metrics.json")
    p.add_argument("--half", help="keep detections of this half (holdout|tune) plus all controls; needs the key's half column")
    a = p.parse_args()
    try:
        rows = read_rows(a.csv)
        rows = join_key(rows, read_rows(a.key)) if a.key else rows
        if a.half:
            rows = [r for r in rows if r["stratum"] == "non_detection" or r["half"] == a.half]
        res = compute_sample_precision(rows)
    except ValueError as e:
        p.error(str(e))
    for k in ("detection", "non_detection"):
        s = res[k]
        print(f"{k}: n={s['n']} clearing={s['clearing']} no_clearing={s['no_clearing']} n_unsure={s['n_unsure']} "
              f"fraction_clearing={s['fraction_clearing']} wilson_95={s['wilson_95']}")
    if not os.path.exists(a.metrics):
        p.error(f"{a.metrics} not found: run score.py first, then re-run this")
    write_hand_labeled(a.metrics, res["hand_labeled"])
    print(f"hand_labeled -> {a.metrics}: {res['hand_labeled']}")


if __name__ == "__main__":
    main()
