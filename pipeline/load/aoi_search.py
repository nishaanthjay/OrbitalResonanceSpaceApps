"""AOI go/no-go: metadata-only NISAR GCOV search per candidate bbox (no downloads)."""
import sys, json
import asf_search as asf

CANDIDATES = {  # ~1x1 deg boxes: (W, S, E, N)
    "Rondonia (Porto Velho-Ariquemes)": (-63.5, -10.0, -62.5, -9.0),
    "N Mato Grosso (Sinop-Colider)": (-55.8, -11.5, -54.8, -10.5),
    "S Para (Novo Progresso)": (-55.8, -7.8, -54.8, -6.8),
    "Santa Cruz BO (Chiquitania)": (-61.5, -17.0, -60.5, -16.0),
    "Madre de Dios PE": (-70.0, -13.0, -69.0, -12.0),
}

def wkt(b):
    w, s, e, n = b
    return f"POLYGON(({w} {s},{e} {s},{e} {n},{w} {n},{w} {s}))"

def search(b, **kw):
    return asf.search(dataset="NISAR", processingLevel="GCOV", intersectsWith=wkt(b),
                      start="2026-06-17", end="2026-10-23", **kw)

if __name__ == "__main__":
    r = search(CANDIDATES["Rondonia (Porto Velho-Ariquemes)"])
    print("n results:", len(r))
    if r:
        print(json.dumps(r[0].properties, indent=1, default=str)[:4000])

def group_table(name, results, dual_only=True):
    from collections import defaultdict
    from datetime import datetime
    g = defaultdict(dict)
    for x in results:
        p = x.properties
        key = (p["pathNumber"], p["frameNumber"], p["flightDirection"], "/".join(p.get("rangeBandwidth") or []))
        d = p["startTime"][:10]
        pols = tuple(p.get("mainBandPolarization") or [])
        if dual_only and not {"HH", "HV"} <= set(pols):
            continue
        g[key][d] = (pols, p.get("frameCoverage"), p["sceneName"])
    rows = []
    for (trk, frm, dirn, mode), dates in g.items():
        ds = sorted(dates)
        dts = [datetime.fromisoformat(d) for d in ds]
        gap = max(((b - a).days for a, b in zip(dts, dts[1:])), default=0)
        pols = sorted({"+".join(v[0]) for v in dates.values()})
        cov = sorted({str(v[1]) for v in dates.values()})
        rows.append(dict(candidate=name, track=trk, frame=frm, direction=dirn, mode=mode,
                         n_dates=len(ds), first=ds[0], last=ds[-1], max_gap=gap,
                         pols=",".join(pols), coverage=",".join(cov), dates=ds))
    return sorted(rows, key=lambda r: -r["n_dates"])

def run_all(cands=CANDIDATES):
    out = []
    for name, b in cands.items():
        out += group_table(name, search(b))
    return out
