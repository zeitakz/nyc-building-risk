"""Convert downloaded CSVs to Parquet and check row counts against the Socrata API.

Usage:
    python pipeline/01b_to_parquet.py              # every dataset in data/raw/MANIFEST.csv
    python pipeline/01b_to_parquet.py pluto dob_ecb

For each dataset (latest MANIFEST entry):
  - data/raw/<name>.csv -> data/processed/<name>.parquet (all columns kept as text; typing and
    cleaning happen in later stages, so nothing is lost or guessed here)
  - compares MANIFEST rows, Parquet rows and the API's count(*) for the same $where
  - writes outputs/tables/download_check.csv (Phase 1 definition of done: within 1% of the API)
Raw files are never modified.
"""
import csv, pathlib, sys
import duckdb, requests

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW, PROC, TABLES = ROOT / "data" / "raw", ROOT / "data" / "processed", ROOT / "outputs" / "tables"
TOLERANCE = 0.01

def latest_manifest():
    with open(RAW / "MANIFEST.csv", newline="") as f:
        rows = list(csv.DictReader(f))
    return {r["dataset"]: r for r in rows}  # later rows overwrite earlier ones

def api_count(socrata_id, where):
    params = {"$select": "count(*) AS n"}
    if where: params["$where"] = where
    r = requests.get(f"https://data.cityofnewyork.us/resource/{socrata_id}.json", params=params, timeout=600)
    r.raise_for_status()
    return int(r.json()[0]["n"])

def main(names):
    man = latest_manifest()
    names = names or sorted(man)
    PROC.mkdir(parents=True, exist_ok=True); TABLES.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    results = []
    for name in names:
        m = man[name]
        src, dst = RAW / m["file"], PROC / f"{name}.parquet"
        con.execute(f"""COPY (SELECT * FROM read_csv('{src}', all_varchar=true, header=true, strict_mode=true))
                        TO '{dst}' (FORMAT parquet, COMPRESSION zstd)""")
        pq_rows = con.execute(f"SELECT count(*) FROM '{dst}'").fetchone()[0]
        api = api_count(m["socrata_id"], m["where"])
        diff = (api - pq_rows) / api if api else 0.0
        ok = int(m["rows"]) == pq_rows and abs(diff) <= TOLERANCE
        results.append(dict(dataset=name, socrata_id=m["socrata_id"], downloaded_utc=m["downloaded_utc"],
                            manifest_rows=int(m["rows"]), parquet_rows=pq_rows, api_count_now=api,
                            pct_diff=round(100 * diff, 3), csv_mb=round(src.stat().st_size / 1e6, 1),
                            parquet_mb=round(dst.stat().st_size / 1e6, 1), pass_=ok))
        r = results[-1]
        print(f"{name:26s} rows {pq_rows:>11,}  api {api:>11,}  diff {r['pct_diff']:+.3f}%  "
              f"{r['csv_mb']:>8} MB -> {r['parquet_mb']:>7} MB  {'PASS' if ok else 'FAIL'}")
    out = TABLES / "download_check.csv"
    prev = {}
    if out.exists():
        with open(out, newline="") as f:
            prev = {r["dataset"]: r for r in csv.DictReader(f)}
    for r in results:
        r["pass"] = r.pop("pass_"); prev[r["dataset"]] = r
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0].keys()) if results else [])
        w.writeheader(); w.writerows(sorted(prev.values(), key=lambda r: r["dataset"]))
    return all(r["pass"] in (True, "True") for r in results)

if __name__ == "__main__":
    sys.exit(0 if main(sys.argv[1:]) else 1)
