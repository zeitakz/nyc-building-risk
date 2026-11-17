import random, statistics as st
from collapse_data import blocks

def feats(units, year, hpd, dob):
    u = max(units, 1)
    g = lambda d,*k: sum(d.get(x,0) for x in k)
    return {
      "HPD class C per unit":      g(hpd,"C")/u,
      "HPD A+B+C per unit":        g(hpd,"A","B","C")/u,
      "HPD registration failures (I)": g(hpd,"I"),
      "DOB construction/maint (C)": g(dob,"C"),
      "DOB emergency/unsafe (IMEGNCY,UB,EGNCY)": g(dob,"IMEGNCY","UB","EGNCY"),
      "DOB failed to certify hazard fix (AEUHAZ1)": g(dob,"AEUHAZ1"),
      "DOB boiler filing failures": g(dob,"LBLVIO","LL6291"),
      "DOB energy/benchmark filing failures": g(dob,"BENCH","EARCX","EGRADE","FISPNRF"),
      "Any DOB hazard-type (C,IMEGNCY,UB,EGNCY,AEUHAZ1)": g(dob,"C","IMEGNCY","UB","EGNCY","AEUHAZ1"),
      "Building age": 2025-year,
    }

def pct(v, others):
    lo = sum(o<v for o in others); eq = sum(o==v for o in others)
    return (lo + 0.5*eq)/len(others)

names = list(feats(1,1900,{},{}).keys())
F = {b:{lot:feats(*v) for lot,v in d["lots"].items()} for b,d in blocks.items()}

def mean_pct(choice):
    out = {n:[] for n in names}
    for b,d in blocks.items():
        c = choice[b]; ctrl=[l for l in F[b] if l!=c]
        for n in names:
            out[n].append(pct(F[b][c][n],[F[b][l][n] for l in ctrl]))
    return {n:st.mean(v) for n,v in out.items()}, out

obs, per = mean_pct({b:d["case"] for b,d in blocks.items()})
random.seed(1); N=20000; ge={n:0 for n in names}
for _ in range(N):
    m,_ = mean_pct({b:random.choice(list(F[b])) for b in blocks})
    for n in names: ge[n]+= m[n]>=obs[n]-1e-12
print(f"{'feature':52s} meanPct  p(one-sided)  per-case percentiles")
for n in sorted(names,key=lambda n:-obs[n]):
    print(f"{n:52s} {obs[n]:.2f}    {ge[n]/N:.3f}       {[round(x,2) for x in per[n]]}")
print("\nblocks:",list(blocks))
print("controls per block:",[len(d['lots'])-1 for d in blocks.values()])
