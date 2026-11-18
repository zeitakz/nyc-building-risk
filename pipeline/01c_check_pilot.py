"""Phase 1 check: reproduce the pilot fire result from the downloaded data.

    python pipeline/01c_check_pilot.py

The pilot (pilot/fire_data.py) hand-transcribed per-lot HPD violation counts for 7 blocks with a
Jan-Feb 2025 fire-damage vacate. This recomputes the same counts for the same lots from
data/processed/ (records before 2025-01-01; our download starts 2010-01-01), then the case's
percentile rank of HPD Class C per unit within its block, as in pilot/fire_analyze.py.

Writes outputs/tables/pilot_reproduction.csv (one row per block, aggregates only) and
outputs/tables/pilot_reproduction_summary.json.
"""
import json, pathlib, statistics as st, sys
import duckdb

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pilot"))
from fire_data import blocks  # noqa: E402

P = ROOT / "data" / "processed"
OUT = ROOT / "outputs" / "tables"
BORO = {"MN": 1, "BX": 2, "BK": 3, "QN": 4, "SI": 5}
CUTOFF = "2025-01-01"

def bbl(b, blk, lot): return b * 1_000_000_000 + blk * 10_000 + lot
def pct(v, o): return (sum(x < v for x in o) + 0.5 * sum(x == v for x in o)) / len(o)

def main():
    want = []
    for name, d in blocks.items():
        b, blk = name.split()[0].split("-")
        for lot in d["lots"]:
            want.append((name, bbl(BORO[b], int(blk), lot), lot, lot == d["case"]))
    con = duckdb.connect()
    con.execute("create temp table want(block_name varchar, bbl bigint, lot int, is_case bool)")
    con.executemany("insert into want values (?,?,?,?)", want)
    counts = con.execute(f"""
        with v as (
          select cast(boroid as bigint)*1000000000 + cast(block as bigint)*10000 + cast(lot as bigint) as bbl,
                 class, cast(inspectiondate as timestamp) as d
          from '{P}/hpd_violations.parquet'
          where try_cast(boroid as int) is not null and try_cast(block as int) is not null and try_cast(lot as int) is not null)
        select w.block_name, w.bbl, w.lot, w.is_case,
               count(v.class) filter (where v.class in ('A','B','C')) as abc,
               count(v.class) filter (where v.class = 'C') as c,
               count(v.class) filter (where v.class = 'I') as i
        from want w left join v on v.bbl = w.bbl and v.d < timestamp '{CUTOFF}'
        group by all""").df()
    units = con.execute(f"""
        select cast(cast(bbl as double) as bigint) as bbl, try_cast(unitsres as int) as units
        from '{P}/pluto.parquet'""").df().set_index("bbl")["units"]
    vac = con.execute(f"""
        select distinct try_cast(cast(bbl as double) as bigint) as bbl from '{P}/hpd_vacates.parquet'
        where primary_vacate_reason = 'Fire Damage'
          and cast(vacate_effective_date as timestamp) between '2025-01-01' and '2025-02-28T23:59:59'""").df()
    fire_bbls = set(vac["bbl"].dropna().astype("int64"))

    rows, ranks_new, ranks_pilot = [], [], []
    for name, d in blocks.items():
        g = counts[counts.block_name == name]
        def cpu_new(r):
            u = units.get(r.bbl)
            u = u if u and u > 0 else d["lots"][r.lot][0]  # fall back to pilot units if PLUTO missing
            return r.c / max(u, 1)
        new = {r.lot: cpu_new(r) for r in g.itertuples()}
        old = {lot: v[2] / max(v[0], 1) for lot, v in d["lots"].items()}
        case = d["case"]
        rn = pct(new[case], [x for l, x in new.items() if l != case])
        ro = pct(old[case], [x for l, x in old.items() if l != case])
        ranks_new.append(rn); ranks_pilot.append(ro)
        cg = g[g.lot == case].iloc[0]
        pv = d["lots"][case]
        rows.append({"block": name, "lots": len(g), "case_bbl_has_fire_vacate_jan_feb_2025": int(cg.bbl) in fire_bbls,
                     "case_c_pilot": pv[2], "case_c_downloaded": int(cg.c),
                     "case_abc_pilot": pv[1], "case_abc_downloaded": int(cg.abc),
                     "block_c_pilot": sum(v[2] for v in d["lots"].values()), "block_c_downloaded": int(g.c.sum()),
                     "pctile_pilot": round(ro, 3), "pctile_downloaded": round(rn, 3)})
    import pandas as pd
    OUT.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows); df.to_csv(OUT / "pilot_reproduction.csv", index=False)
    summary = {"cases": len(rows), "cutoff": CUTOFF, "data_starts": "2010-01-01",
               "mean_pctile_pilot": round(st.mean(ranks_pilot), 3),
               "mean_pctile_downloaded": round(st.mean(ranks_new), 3),
               "cases_confirmed_fire_vacate": int(df.case_bbl_has_fire_vacate_jan_feb_2025.sum())}
    (OUT / "pilot_reproduction_summary.json").write_text(json.dumps(summary, indent=2))
    print(df.to_string(index=False)); print(json.dumps(summary, indent=2))

if __name__ == "__main__":
    main()
