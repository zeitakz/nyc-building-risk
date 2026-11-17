"""Download NYC Open Data (Socrata) datasets to data/raw/ with a provenance manifest.

Usage:
    python pipeline/01_download.py --list
    python pipeline/01_download.py --dataset hpd_vacates --since 2018-01-01
    python pipeline/01_download.py --dataset hpd_violations --since 2010-01-01

Pages through the API with $limit/$offset, ordered by a stable key, and records
the query, UTC timestamp and row count in data/raw/MANIFEST.csv.
Set SOCRATA_APP_TOKEN to raise rate limits (optional).
"""
import argparse, csv, datetime as dt, io, os, pathlib, sys, time
import requests

BASE = "https://data.cityofnewyork.us/resource/{id}.csv"
RAW = pathlib.Path(__file__).resolve().parents[1] / "data" / "raw"
PAGE = 50_000

# id, date column used for --since, stable order key, optional extra filter, columns (None = all)
DATASETS = {
    "hpd_vacates": dict(id="tb8q-a3ar", date="vacate_effective_date", order=":id", where=None, cols=None),
    "hpd_violations": dict(id="wvxf-dwi5", date="inspectiondate", order="violationid", where=None,
        cols="violationid,buildingid,boroid,block,lot,bbl,bin,apartment,story,class,inspectiondate,"
             "approveddate,novdescription,novissueddate,ordernumber,currentstatus,currentstatusdate,violationstatus"),
    "dob_violations": dict(id="3h2n-5cm9", date="issue_date", order="number", where=None,
        cols="number,boro,block,lot,bin,issue_date,violation_type_code,violation_category,description,disposition_date"),
    "dob_ecb": dict(id="6bgk-3dad", date="issue_date", order=":id", where=None, cols=None),
    "dob_complaints": dict(id="eabe-havv", date="date_entered", order=":id", where=None, cols=None),
    "dob_now_permits": dict(id="rbx6-tga4", date="issued_date", order=":id", where=None, cols=None),
    "pluto": dict(id="64uk-42ks", date=None, order="bbl", where=None,
        cols="bbl,borough,block,lot,address,bldgclass,landuse,yearbuilt,unitsres,unitstotal,numfloors,"
             "lotarea,bldgarea,ownername,zipcode,bct2020,latitude,longitude"),
    "nyc311_housing": dict(id="erm2-nwe9", date="created_date", order="unique_key",
        where="complaint_type in('HEAT/HOT WATER','ELECTRIC','GAS','SAFETY','UNSANITARY CONDITION')",
        cols="unique_key,created_date,complaint_type,descriptor,bbl,incident_address,borough,status"),
}

def socrata_date(col, since, dataset):
    # DOB violations and ECB store dates as YYYYMMDD text; others are floating timestamps
    if dataset in ("dob_violations", "dob_ecb"):
        return f"{col} >= '{since.replace('-', '')}'"
    if dataset == "dob_complaints":
        return None  # MM/DD/YYYY text; filter after download
    return f"{col} >= '{since}T00:00:00'"

def download(name, since=None, max_rows=None):
    spec = DATASETS[name]
    where = [w for w in [spec["where"], socrata_date(spec["date"], since, name) if (since and spec["date"]) else None] if w]
    params = {"$order": spec["order"], "$limit": PAGE}
    if spec["cols"]: params["$select"] = spec["cols"]
    if where: params["$where"] = " AND ".join(where)
    headers = {"X-App-Token": os.environ["SOCRATA_APP_TOKEN"]} if os.environ.get("SOCRATA_APP_TOKEN") else {}
    RAW.mkdir(parents=True, exist_ok=True)
    out = RAW / f"{name}.csv"
    total, offset, wrote_header = 0, 0, False
    with open(out, "w", newline="") as f:
        while True:
            params["$offset"] = offset
            for attempt in range(5):
                r = requests.get(BASE.format(id=spec["id"]), params=params, headers=headers, timeout=120)
                if r.status_code == 200: break
                time.sleep(2 ** attempt)
            r.raise_for_status()
            text = r.text
            lines = text.splitlines(keepends=True)
            if len(lines) <= 1: break
            f.write("".join(lines if not wrote_header else lines[1:]))
            wrote_header = True
            n = len(list(csv.reader(io.StringIO(text)))) - 1
            total += n; offset += PAGE
            print(f"  {name}: {total:,} rows", file=sys.stderr)
            if n < PAGE or (max_rows and total >= max_rows): break
    manifest = RAW / "MANIFEST.csv"
    new = not manifest.exists()
    with open(manifest, "a", newline="") as m:
        w = csv.writer(m)
        if new: w.writerow(["dataset", "socrata_id", "where", "downloaded_utc", "rows", "file"])
        w.writerow([name, spec["id"], params.get("$where", ""), dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), total, out.name])
    return out, total

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", choices=sorted(DATASETS))
    ap.add_argument("--since", help="YYYY-MM-DD")
    ap.add_argument("--max-rows", type=int, help="stop early (for testing)")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if a.list or not a.dataset:
        for k, v in DATASETS.items(): print(f"{k:18s} {v['id']}")
        sys.exit(0)
    path, n = download(a.dataset, a.since, a.max_rows)
    print(f"wrote {n:,} rows to {path}")
