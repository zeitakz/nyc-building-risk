# CLAUDE.md — NYC Building Risk Signals

Instructions for Claude Code working in this repo. Read this file fully before starting a task.

## What this project is

A public portfolio project asking: **can NYC's public housing and building records flag residential
buildings at higher risk of a serious fire before it happens, and which patterns of owner neglect drive
that risk?** Structural collapse and other harms come later, using the same pipeline.

The output is (1) a reproducible Python pipeline and (2) a Quarto website published to GitHub Pages
from `site/`. Anyone should be able to clone the repo and rebuild every number on the site.

Current state: a small pilot (in `pilot/`) found that buildings with HPD fire-damage vacate orders in
Jan 2025 had far more pre-2025 HPD Class C violations per unit than similar buildings on the same
block (mean percentile rank 0.87 across 7 cases, permutation p ≈ 0.001). DOB records alone added
little for fires, but mattered for structural collapse (9 cases). These are leads, not findings. The
job now is to test them at scale.

## Ground rules

1. **No leakage.** A predictor may only use records dated before `event_date - gap_days`
   (default gap 60 days; also report 180 and 365). Every feature function takes a cutoff date
   argument. Never compute features without one.
2. **Raw data is read-only.** Downloads go to `data/raw/` and are never edited in place. All
   cleaning writes new files to `data/processed/`. Both folders are git-ignored.
3. **Write results to files, not just stdout.** Tables → `outputs/tables/*.csv`; figures →
   `outputs/figures/*.png|svg`; model summaries → `outputs/models/*.txt|json`. The site reads from
   `outputs/`.
4. **The site publishes aggregates only.** No raw records, no unit numbers, no tenant-level detail.
   Do not publish a named list of "high-risk buildings" or named landlords unless the user
   explicitly asks and each entry has been checked against the source records. The 2625 Bedford Ave
   case study is the exception: it names addresses already in DOB's public violation text and the news.
5. **Record provenance.** Every downloaded file gets a line in `data/raw/MANIFEST.csv`:
   dataset id, query, download timestamp (UTC), row count.
6. **Prefer DuckDB** for joins and aggregation over large CSV/Parquet files. Use pandas for
   small frames and modeling. Convert large CSVs to Parquet once in `data/processed/`.
7. **Small, reviewable steps.** One pipeline stage per script in `pipeline/`, numbered, each
   runnable on its own (`python pipeline/02_build_cases.py`). Ask the user before long
   downloads (> 2 GB) or anything that takes more than ~20 minutes.

## Data

All from NYC Open Data (Socrata). Base URL: `https://data.cityofnewyork.us/resource/<id>.csv`
Use SoQL (`$select`, `$where`, `$limit`, `$offset`) to download only needed columns and years.
Page with `$limit=50000` + `$offset`; `$order` by a stable key so paging is deterministic.
An app token (env var `SOCRATA_APP_TOKEN`, optional) raises rate limits.

| Dataset | ID | Use | Key fields |
|---|---|---|---|
| HPD Order to Repair/Vacate Orders | `tb8q-a3ar` | **Fire outcome** (`primary_vacate_reason = 'Fire Damage'`) | bbl, vacate_effective_date, vacate_type, number_of_vacated_units |
| HPD Housing Maintenance Code Violations | `wvxf-dwi5` | Main predictor | boroid, block, lot, bbl, class, inspectiondate, novdescription, ordernumber, currentstatus, violationstatus |
| DOB Violations | `3h2n-5cm9` | Predictor; fire-damage cross-check | boro, block, lot, bin, issue_date, violation_type_code, description |
| DOB ECB Violations | `6bgk-3dad` | Predictor (severity, penalties, respondent) | bin, boro, block, lot, issue_date, severity, violation_type, violation_description |
| DOB Complaints Received | `eabe-havv` | Predictor (illegal conversion, work w/o permit) | bin, house_number, house_street, date_entered, complaint_category, disposition_code |
| DOB NOW Approved Permits | `rbx6-tga4` | Construction on lot / adjacent lots | bin, borough, block, lot, work_type, issued_date |
| PLUTO | `64uk-42ks` | Building traits, matching | bbl, borough, block, lot, bldgclass, yearbuilt, unitsres, numfloors, latitude, longitude |
| 311 Service Requests | `erm2-nwe9` | Tenant reports (heat, gas, electrical, smoke) | created_date, complaint_type, descriptor, bbl, incident_address. The `complaint_type` filter in `01_download.py` is a guess: check the real values first |
| HPD Complaints and Problems | verify ID on Open Data | Tenant complaints | — |
| HPD Registrations / Contacts | verify IDs | Owner info, portfolio linking | — |
| FDNY Incidents Responded to by Fire Companies | verify ID | Secondary fire outcome (all structural fires) | incident type, date, location (may need geocoding) |

**Verify before relying on any ID marked "verify"**: fetch `https://data.cityofnewyork.us/api/views/<id>.json`
and confirm the dataset name and columns.

Optional bulk alternative: [NYCDB](https://github.com/nycdb/nycdb) (`pip install nycdb`) loads most of
these plus ACRIS, tax lien sale lists, HPD AEP and rent-stabilization counts into Postgres. Use it if
the user has Postgres set up; otherwise stick with Socrata + DuckDB.

### Join keys and known quirks (learned in the pilot)

- **BBL** = 10 digits: borough (1 MN, 2 BX, 3 BK, 4 QN, 5 SI) + 5-digit block + 4-digit lot.
  Build it yourself from parts; don't trust a string column to be zero-padded.
- **HPD** uses `boroid` (1–5) and unpadded integer `block`/`lot`.
- **DOB Violations / ECB** use `boro` (1–5) and zero-padded strings: `block='05211'`, `lot='00074'`.
  Some rows have malformed lots (`'0031'`, `'0 137'`, empty): normalize by stripping non-digits
  and casting to int; log and drop unparseable rows.
- **PLUTO** uses borough letters (`MN BX BK QN SI`). Condo lots are `75xx`; map to the billing BBL
  if you need building-level counts.
- **DOB** is keyed by **BIN** (building), not BBL. One BBL can have several BINs and BINs change
  when buildings are demolished/rebuilt. Use PLUTO or the Property Address Directory to map.
- HPD `inspectiondate` is ISO timestamp; DOB `issue_date` is `YYYYMMDD` text. Parse both to dates.
- HPD vacate orders: the vacate date can lag the fire by days to weeks. Treat
  `vacate_effective_date` as the event date and rely on the gap (rule 1) to absorb the lag.

## Study design (fires)

1. **Cases** (`pipeline/02_build_cases.py`): HPD vacates with `primary_vacate_reason = 'Fire Damage'`,
   2018-01-01 to 2025-12-31, residential buildings (PLUTO class A, B, C, D, R, S) built before 2000.
   One case per BBL (first fire in window). Output `data/processed/cases.parquet`.
2. **Controls** (`03_match_controls.py`): for each case, up to 10 buildings on the same block, else
   the same census tract, with `unitsres` between 1/3× and 3× the case's, residential class, no
   fire vacate in the window. Keep a `match_set` id. Output `matched.parquet`.
3. **Features** (`04_features.py`): for every building in a match set, using the case's cutoff
   date (`event_date - gap_days`), compute over 1-, 3- and 5-year lookbacks:
   - HPD violations by class (A, B, C, I), per unit and raw
   - HPD violations by **category**, from `novdescription` keyword rules in
     `pipeline/hpd_categories.yml`: electrical/wiring, gas, heat/hot water, smoke/CO detectors,
     self-closing doors, fire escape/egress, window gates, leaks/water, pests, mold, lead, other
   - HPD owner response: share still open after 90 days; "no access" reinspections; false
     certification of repair (verify how this appears in the data)
   - DOB: violation type groups — maintenance/construction (`C`), emergency/unsafe
     (`IMEGNCY`, `UB`, `EGNCY`), failed-to-certify hazard (`AEUHAZ1`), boiler filings
     (`LBLVIO`, `LL6291`), energy/benchmarking (`BENCH`, `EARCX`, `EGRADE`), elevator (`E*`)
   - DOB complaints by category (illegal conversion, work without permit, etc.)
   - 311 heat/gas/electrical/smoke reports
   - Building traits: age, units, floors, building class
   Output `features.parquet`, one row per building per match set.
4. **Models** (`05_models.py`):
   - Conditional logistic regression (`statsmodels.discrete.conditional_models.ConditionalLogit`)
     grouped by `match_set`. Report odds ratios with 95% CIs.
   - Then LightGBM + SHAP for interactions (exploratory; label it so on the site).
   - **Temporal holdout**: fit on events 2018–2023, evaluate ranking on 2024–2025 (AUC within match
     sets, and top-decile capture).
5. **Bias checks**: rerun with HPD *complaint* counts as a covariate (inspection-intensity bias);
   split by building size (≤ 5 units vs larger); rerun with 180- and 365-day gaps.

## Definition of done per phase

- **Phase 1, data:** every dataset in the table above downloaded for 2010–present, row counts
  logged in MANIFEST and within 1% of the Socrata `$select=count(*)` for the same query.
  `pilot/` results reproduce from the downloaded data (same 7 fire cases → Class C/unit mean
  percentile ≈ 0.87).
- **Phase 2, cases/controls:** case count, control count, and match-rate table written to
  `outputs/tables/`. Spot-check 10 random cases by hand against Open Data.
- **Phase 3, features:** feature table with documented columns (`outputs/tables/feature_dictionary.csv`);
  no feature uses a date ≥ cutoff (add an assertion test in `tests/`).
- **Phase 4, models:** odds-ratio table, holdout performance, SHAP summary plot in `outputs/`.
- **Phase 5, site:** pages updated from `outputs/`, `quarto render site` succeeds with no errors.

## Repo layout

```
CLAUDE.md            this file
README.md            public-facing overview
requirements.txt
pilot/               the original small-sample study (hand-transcribed aggregates); keep as-is
pipeline/            numbered scripts, one stage each
  01_download.py     Socrata downloader with manifest (working)
  hpd_categories.yml keyword rules for violation categories (to write)
data/raw/            downloads (git-ignored)
data/processed/      cleaned Parquet (git-ignored)
outputs/             tables, figures, model summaries (committed; small files only)
tests/               leakage and join-key tests
site/                Quarto website (published to GitHub Pages)
```

## Site

- Quarto website in `site/`; `quarto render site` builds to `site/_site/`.
- Published by `.github/workflows/publish.yml` on push to `main` (Quarto's official action →
  `gh-pages` branch). The user must run `quarto publish gh-pages` locally once to create that
  branch, and the repo must be public on a free GitHub account.
- Pages read numbers from `outputs/` or `pilot/` via Python code cells; never hard-code a number
  that a script produces.
- Tone: plain, careful, no hype. Every finding states its sample size and its main caveat.

## Commands

```
pip install -r requirements.txt
python pipeline/01_download.py --dataset hpd_vacates --since 2018-01-01
python pilot/fire_analyze.py
quarto preview site
```
