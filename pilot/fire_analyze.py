import random, statistics as st
from fire_data import blocks
def feats(u,abc,c,i,sm,dc,hz,ae,bo):
    u=max(u,1); dobany=dc+hz+ae
    return {"HPD all violations per unit":abc/u, "HPD class C per unit":c/u,
      "HPD smoke/CO detector per unit":(sm/u if sm>=0 else None), "HPD registration failures":i,
      "DOB maint/emergency/uncertified (C,UB,IMEGNCY,AEUHAZ1)":dobany,
      "DOB boiler filing failures":bo}
F={b:{l:feats(*v) for l,v in d["lots"].items()} for b,d in blocks.items()}
names=list(next(iter(F.values()))[next(iter(blocks.values()))["case"]].keys())
def pct(v,o): return (sum(x<v for x in o)+0.5*sum(x==v for x in o))/len(o)
def score(choice):
    out={n:[] for n in names}
    for b in blocks:
        c=choice[b]; ot=[l for l in F[b] if l!=c]
        for n in names:
            if F[b][c][n] is None: continue
            out[n].append(pct(F[b][c][n],[F[b][l][n] for l in ot]))
    return {n:st.mean(v) for n,v in out.items()}, out
obs,per=score({b:d["case"] for b,d in blocks.items()})
random.seed(2);N=20000;ge={n:0 for n in names}
for _ in range(N):
    m,_=score({b:random.choice(list(F[b])) for b in blocks})
    for n in names: ge[n]+=m[n]>=obs[n]-1e-12
for n in sorted(names,key=lambda n:-obs[n]):
    print(f"{n:55s} {obs[n]:.2f}  p={ge[n]/N:.3f}  {[round(x,2) for x in per[n]]}")
# combined flags
print()
for label,fn in [
  ("HPD C/unit in top third of block", lambda v,q: v["HPD class C per unit"]>=q["c67"]),
  ("HPD C/unit top third AND any DOB maint/emergency", lambda v,q: v["HPD class C per unit"]>=q["c67"] and v["DOB maint/emergency/uncertified (C,UB,IMEGNCY,AEUHAZ1)"]>0),
  ("HPD C/unit top third AND boiler failures above block median", lambda v,q: v["HPD class C per unit"]>=q["c67"] and v["DOB boiler filing failures"]>q["bmed"]),
  ("Any DOB maint/emergency", lambda v,q: v["DOB maint/emergency/uncertified (C,UB,IMEGNCY,AEUHAZ1)"]>0)]:
    hits=0;exp=0
    for b,d in blocks.items():
        vals=F[b]; cs=sorted(v["HPD class C per unit"] for v in vals.values())
        q={"c67":cs[int(len(cs)*2/3)],"bmed":st.median(v["DOB boiler filing failures"] for v in vals.values())}
        hits+=fn(vals[d["case"]],q); others=[l for l in vals if l!=d["case"]]
        exp+=st.mean(fn(vals[o],q) for o in others)
    print(f"{label:62s} cases {hits}/{len(blocks)}  expected {exp:.1f}")
print("controls:",[len(d['lots'])-1 for d in blocks.values()])
