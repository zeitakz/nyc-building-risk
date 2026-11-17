"""Shared scoring for the pilot studies, used by the scripts and the website.

Each case building is ranked against the comparison buildings on its own block
(percentile: share of neighbors with a lower value, ties count half). The mean
percentile across cases is tested with a permutation test: on each block pick a
random building as the "case" and see how often the mean is as high as observed.
"""
import random, statistics as st

FIRE_FEATURES = {
    "HPD Class C violations per apartment": lambda u,abc,c,i,sm,dc,hz,ae,bo: c/max(u,1),
    "HPD violations (A+B+C) per apartment": lambda u,abc,c,i,sm,dc,hz,ae,bo: abc/max(u,1),
    "HPD smoke/CO detector violations per apartment": lambda u,abc,c,i,sm,dc,hz,ae,bo: (sm/max(u,1) if sm >= 0 else None),
    "DOB maintenance/emergency violations": lambda u,abc,c,i,sm,dc,hz,ae,bo: dc+hz+ae,
    "HPD registration failures": lambda u,abc,c,i,sm,dc,hz,ae,bo: i,
    "DOB missed boiler filings": lambda u,abc,c,i,sm,dc,hz,ae,bo: bo,
}

def _g(d, *keys): return sum(d.get(k, 0) for k in keys)
COLLAPSE_FEATURES = {
    "DOB construction/maintenance violations": lambda u,y,h,d: _g(d,"C"),
    "DOB emergency or unsafe-building orders": lambda u,y,h,d: _g(d,"IMEGNCY","UB","EGNCY"),
    "HPD violations (A+B+C) per apartment": lambda u,y,h,d: _g(h,"A","B","C")/max(u,1),
    "HPD Class C violations per apartment": lambda u,y,h,d: _g(h,"C")/max(u,1),
    "DOB missed boiler filings": lambda u,y,h,d: _g(d,"LBLVIO","LL6291"),
    "Building age": lambda u,y,h,d: 2025-y,
}

def _pct(v, others):
    return (sum(o < v for o in others) + 0.5*sum(o == v for o in others)) / len(others)

def score(blocks, features, n_perm=20000, seed=1):
    """Return list of dicts: feature, mean_pct, p_value, per_case, n_cases."""
    F = {b: {lot: {n: f(*vals) for n, f in features.items()} for lot, vals in d["lots"].items()}
         for b, d in blocks.items()}
    def means(choice):
        out = {n: [] for n in features}
        for b in blocks:
            c = choice[b]; ot = [l for l in F[b] if l != c]
            for n in features:
                if F[b][c][n] is None: continue
                out[n].append(_pct(F[b][c][n], [F[b][l][n] for l in ot]))
        return out
    obs = means({b: d["case"] for b, d in blocks.items()})
    obs_m = {n: st.mean(v) for n, v in obs.items()}
    rng = random.Random(seed); ge = {n: 0 for n in features}
    for _ in range(n_perm):
        m = means({b: rng.choice(list(F[b])) for b in blocks})
        for n in features:
            ge[n] += st.mean(m[n]) >= obs_m[n] - 1e-12
    return sorted(({"feature": n, "mean_pct": obs_m[n], "p_value": ge[n]/n_perm,
                    "per_case": obs[n], "n_cases": len(obs[n])} for n in features),
                  key=lambda r: -r["mean_pct"])

def n_controls(blocks):
    return sum(len(d["lots"]) - 1 for d in blocks.values())
