"""Download NYC Open Data (Socrata) datasets to data/raw/ with a provenance manifest.

Usage:
    python pipeline/01_download.py --list
    python pipeline/01_download.py --dataset hpd_vacates --since 2018-01-01
    python pipeline/01_download.py --dataset hpd_violations --since 2010-01-01

Pages through the API with $limit/$offset, ordered by a stable key, and records
the query, UTC timestamp and row count in data/raw/MANIFEST.csv.
Set SOCRATA_APP_TOKEN to raise rate limits (optional), either in the environment or in a
git-ignored .env file at the repo root containing a line: SOCRATA_APP_TOKEN=...
"""
import argparse, csv, datetime as dt, io, os, pathlib, sys, time
import requests

ROOT = pathlib.Path(__file__).resolve().parents[1]
BASE = "https://data.cityofnewyork.us/resource/{id}.csv"
RAW = ROOT / "data" / "raw"
PAGE = 50_000

def _load_dotenv(path=ROOT / ".env"):
    """Read KEY=VALUE lines from .env into os.environ (existing env vars win)."""
    if not path.exists(): return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
_load_dotenv()

# id, date column used for --since, stable order key (must be unique; else :id), optional extra filter, columns (None = all)
DATASETS = {
    "hpd_vacates": dict(id="tb8q-a3ar", date="vacate_effective_date", order=":id", where=None, cols=None),
    "hpd_violations": dict(id="wvxf-dwi5", date="inspectiondate", order="violationid", where=None,
        cols="violationid,buildingid,boroid,block,lot,bbl,bin,apartment,story,class,inspectiondate,"
             "approveddate,novdescription,novissueddate,ordernumber,currentstatus,currentstatusdate,violationstatus"),
    "dob_violations": dict(id="3h2n-5cm9", date="issue_date", order=":id", where=None,
        cols="number,boro,block,lot,bin,issue_date,violation_type_code,violation_category,description,disposition_date"),
    "dob_ecb": dict(id="6bgk-3dad", date="issue_date", order=":id", where=None,
        cols="isn_dob_bis_extract,ecb_violation_number,ecb_violation_status,dob_violation_number,bin,boro,block,lot,"
             "issue_date,served_date,hearing_date,hearing_status,severity,violation_type,violation_description,"
             "infraction_code1,section_law_description1,aggravated_level,penality_imposed,amount_paid,balance_due,"
             "certification_status,respondent_name"),
    "dob_complaints": dict(id="eabe-havv", date="date_entered", order=":id", where=None, cols=None),
    "dob_now_permits": dict(id="rbx6-tga4", date="issued_date", order=":id", where=None,
        cols="job_filing_number,work_permit,sequence_number,filing_reason,borough,block,lot,bin,bbl,work_on_floor,"
             "work_type,approved_date,issued_date,expired_date,job_description,estimated_job_costs,permit_status,"
             "owner_business_name,owner_name"),
    "pluto": dict(id="64uk-42ks", date=None, order="bbl", where=None,
        cols="bbl,borough,block,lot,address,bldgclass,landuse,yearbuilt,unitsres,unitstotal,numfloors,"
             "lotarea,bldgarea,ownername,zipcode,bct2020,latitude,longitude"),
    # 311 is split across two datasets: erm2-nwe9 (2020-present) and 76ig-c548 (2010-2019).
    "nyc311_housing": dict(id="erm2-nwe9", date="created_date", order="unique_key",
        where=None, cols=None),  # where/cols filled from NYC311_* below
    "nyc311_housing_2010_2019": dict(id="76ig-c548", date="created_date", order="unique_key",
        where=None, cols=None),
    # Verified 2026-11-16 against https://data.cityofnewyork.us/api/views/<id>.json
    "hpd_complaints": dict(id="ygpa-z7cr", date="received_date", order="problem_id", where=None,
        cols="problem_id,complaint_id,building_id,borough,block,lot,bbl,bin,received_date,type,major_category,"
             "minor_category,problem_code,complaint_status,complaint_status_date,problem_status,problem_status_date,"
             "unit_type,space_type"),
    "hpd_registrations": dict(id="tesw-yqqr", date=None, order=":id", where=None, cols=None),
    "hpd_contacts": dict(id="feu5-w2e2", date=None, order=":id", where=None, cols=None),
    # FDNY NFIRS incidents: no BBL/BIN or house number (street, zip, borough only); 2013 to 2025-09.
    "fdny_incidents": dict(id="tm6d-hbzd", date="incident_date_time", order=":id",
        where="starts_with(incident_type_desc, '1')", cols=None),  # NFIRS 1xx = fires
}

# HPD tenant reports via 311 relevant to fire risk. Checked against the real values on 2026-11-16:
# - there is no complaint_type 'GAS'; gas, smoke/CO detectors and fire escapes are descriptors
#   (e.g. GENERAL/COOKING GAS, SAFETY/SMOKE DETECTOR, NONCONST/CARBON MONOXIDE before 2014)
# - complaint types were renamed on 2014-03-11 (HEATING -> HEAT/HOT WATER, NONCONST/GENERAL
#   CONSTRUCTION -> SAFETY/GENERAL), and some periods use mixed case ('Heat/Hot Water'), so compare upper()
# - 'UNSANITARY CONDITION' (pests, garbage, mold) is dropped: not a fire-risk report
NYC311_WHERE = (
    "agency = 'HPD' AND ("
    "upper(complaint_type) IN ('HEAT/HOT WATER','HEATING','ELECTRIC','SAFETY') "
    "OR upper(descriptor) IN ('COOKING GAS','GAS','ELECTRIC/GAS RANGE','ELECTRIC/GAS-RANGE',"
    "'SMOKE DETECTOR','SMOKE-DETECTOR','SMOKE-FUMES','CARBON MONOXIDE','CARBON MONOXIDE DETECTOR',"
    "'FIRE ESCAPE','FIRE-ESCAPE'))"
)
NYC311_COLS = "unique_key,created_date,agency,complaint_type,descriptor,bbl,incident_address,borough,status"
for _k in ("nyc311_housing", "nyc311_housing_2010_2019"):
    DATASETS[_k].update(where=NYC311_WHERE, cols=NYC311_COLS)

def socrata_date(col, since, dataset):
    # DOB violations and ECB store dates as YYYYMMDD text; others are floating timestamps
    if dataset in ("dob_violations", "dob_ecb"):
        return f"{col} >= '{since.replace('-', '')}'"
    if dataset == "dob_complaints":
        return None  # MM/DD/YYYY text; filter after download
    return f"{col} >= '{since}T00:00:00'"

def get_page(url, params, headers, attempts=8):
    """GET one page, retrying network errors and non-200s with backoff (up to ~4 min total)."""
    for attempt in range(attempts):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=300)
            if r.status_code == 200: return r
            err = f"HTTP {r.status_code}"
        except requests.RequestException as e:
            err = repr(e)
        wait = min(2 ** attempt, 60)
        print(f"  retry {attempt + 1}/{attempts} at offset {params['$offset']} in {wait}s: {err}", file=sys.stderr)
        time.sleep(wait)
    raise RuntimeError(f"giving up at offset {params['$offset']}: {err}")

def download(name, since=None, max_rows=None):
    spec = DATASETS[name]
    where = [w for w in [spec["where"], socrata_date(spec["date"], since, name) if (since and spec["date"]) else None] if w]
    params = {"$order": spec["order"], "$limit": min(PAGE, max_rows) if max_rows else PAGE}
    if spec["cols"]: params["$select"] = spec["cols"]
    if where: params["$where"] = " AND ".join(where)
    headers = {"X-App-Token": os.environ["SOCRATA_APP_TOKEN"]} if os.environ.get("SOCRATA_APP_TOKEN") else {}
    RAW.mkdir(parents=True, exist_ok=True)
    out = RAW / f"{name}.csv"
    part = out.with_suffix(".csv.part")  # renamed to .csv only when the download completes
    total, offset, wrote_header = 0, 0, False
    with open(part, "w", newline="") as f:
        while True:
            params["$offset"] = offset
            r = get_page(BASE.format(id=spec["id"]), params, headers)
            text = r.text
            lines = text.splitlines(keepends=True)
            if len(lines) <= 1: break
            f.write("".join(lines if not wrote_header else lines[1:]))
            wrote_header = True
            n = len(list(csv.reader(io.StringIO(text)))) - 1
            total += n; offset += PAGE
            print(f"  {name}: {total:,} rows", file=sys.stderr)
            if n < params["$limit"] or (max_rows and total >= max_rows): break
    part.replace(out)
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
