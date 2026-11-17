import random, statistics as st
from collapse_data import blocks
def f(units,year,hpd,dob):
    u=max(units,1)
    hc=hpd.get("C",0)/u; dh=sum(dob.get(k,0) for k in ("C","IMEGNCY","UB","EGNCY","AEUHAZ1"))
    return hc,dh,sum(hpd.values())>0
def run(choice):
    res={"HPD high & DOB any":[], "HPD high & no DOB":[], "DOB any only":[], "HPD present & DOB any":[]}
    for b,d in blocks.items():
        vals={l:f(*v) for l,v in d["lots"].items()}
        med=st.median([v[0] for v in vals.values()])
        def flags(v): return {"HPD high & DOB any":v[0]>med and v[1]>0,
            "HPD high & no DOB":v[0]>med and v[1]==0, "DOB any only":v[1]>0,
            "HPD present & DOB any":v[2] and v[1]>0}
        c=choice[b]; others=[l for l in vals if l!=c]
        for k in res:
            rate=st.mean(flags(vals[o])[k] for o in others)
            res[k].append((flags(vals[c])[k], rate))
    return res
obs=run({b:d["case"] for b,d in blocks.items()})
for k,v in obs.items():
    hits=sum(x for x,_ in v); exp=sum(r for _,r in v)
    print(f"{k:24s} cases flagged {hits}/9, expected by chance {exp:.1f}")
