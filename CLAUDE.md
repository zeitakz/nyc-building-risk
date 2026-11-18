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
| 311 Service Requests 2020–present | `erm2-nwe9` | Tenant reports (heat, gas, electrical, smoke) | created_date, agency, complaint_type, descriptor, bbl, incident_address. Filter (HPD only, `upper()` match on type + descriptor) checked against real values 2026-11-16; see `NYC311_WHERE` in `01_download.py` |
| 311 Service Requests 2010–2019 | `76ig-c548` | Same, earlier years (split from `erm2-nwe9`) | Same columns. Complaint types renamed 2014-03-11 (`HEATING` → `HEAT/HOT WATER`, `NONCONST` → `SAFETY`) |
| HPD Complaints and Problems | `ygpa-z7cr` (verified) | Tenant complaints | received_date, problem_id, complaint_id, building_id, block, lot, bbl, bin, type, major_category, minor_category, problem_code, complaint_status |
| HPD Multiple Dwelling Registrations | `tesw-yqqr` (verified) | Owner info, portfolio linking | registrationid, buildingid, boroid, block, lot, bin, lastregistrationdate, registrationenddate |
| HPD Registration Contacts | `feu5-w2e2` (verified) | Owner/agent names, joined on registrationid | registrationid, type, corporationname, firstname, lastname, business address |
| FDNY Incidents Responded to by Fire Companies | `tm6d-hbzd` (verified) | Secondary fire outcome (all structural fires) | incident_type_desc (NFIRS `111 - Building fire` etc.), incident_date_time, street_highway, zip_code, borough_desc. **No BBL/BIN or house number**: street-level only, can't be joined to buildings reliably. Covers 2013-01 to 2025-09 only |

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
- **PLUTO** `bbl` comes back from the API as `1000010010.00000000`: cast via DOUBLE to BIGINT before joining.
- **PLUTO** uses borough letters (`MN BX BK QN SI`). Condo lots are `75xx`; map to the billing BBL
  if you need building-level counts.
- **DOB** is keyed by **BIN** (building), not BBL. One BBL can have several BINs and BINs change
  when buildings are demolished/rebuilt. Use PLUTO or the Property Address Directory to map.
- HPD `inspectiondate` is ISO timestamp; DOB `issue_date` is `YYYYMMDD` text. Parse both to dates.
- HPD vacate orders: the vacate date can lag the fire by days to weeks. Treat
  `vacate_effective_date` as the event date and rely on the gap (rule 1) to absorb the lag.

## Study design (fires)

**`ANALYSIS_PLAN.md` is the pre-registered plan** (primary and secondary hypotheses, the
discovery/confirmation split, pass/fail rules). Follow it. Any change goes under its
Deviations section with date and reason. Never look at confirmation-set results before the
promoted-feature list is committed. The split rule is in `pipeline/splits.py`; don't change it.

0. **Study population: private multiple dwellings.** Cases *and* controls must have PLUTO
   `unitsres >= 3` and not be NYCHA (`ownername` matching "HOUSING AUTHORITY"). Reason: the outcome
   only exists where HPD has jurisdiction. 2018–2025 fire-vacate rates per 100k units: NYCHA 0.6,
   1–2 units 3.8, 3–5 units 94, 6–19 units 139, 20+ units 79. Fires in 1–2 family homes and NYCHA
   are handled by other agencies, so including them would compare HPD-watched buildings with
   unwatched ones. State findings as "among privately owned multiple dwellings". Do **not** use
   `kj4p-ruqc` (Buildings Subject to HPD Jurisdiction) to define the population: one of its entry
   criteria is "HPD has received a complaint", so membership itself reflects HPD attention.
1. **Cases** (`pipeline/02_build_cases.py`): HPD vacates with `primary_vacate_reason = 'Fire Damage'`,
   2018-01-01 to 2025-12-31, in the study population, residential buildings (PLUTO class A, B, C, D,
   R, S) built before 2000. One case per BBL (first fire in window). Add an event-period flag
   (see Open questions). Output `data/processed/cases.parquet`.
2. **Controls** (`03_match_controls.py`): for each case, up to 10 buildings on the same block, else
   the same census tract, in the study population, with `unitsres` between 1/3× and 3× the case's
   (and >= 3), residential class, no fire vacate in the window. Keep a `match_set` id. Write a
   balance table (units, age, floors, class, program status; cases vs controls) to `outputs/tables/`.
   Output `matched.parquet`.
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
     (`LBLVIO`, `LL6291`), energy/benchmarking (`BENCH`, `EARCX`, `EGRADE`), elevator (`E`, `EVCAT*` only; a bare `E*` prefix would also catch `EGRADE`, `EARCX`, `EGNCY`)
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
5. **Bias checks** — HPD attention differs *within* the study population too, and both the
   predictors (violations) and the outcome (vacates) come from HPD:
   - rerun with HPD *complaint* counts as a covariate (inspection-intensity bias);
   - adjust for or stratify on enforcement/program status: rent stabilization, Alternative
     Enforcement Program (AEP), HPD-financed regulatory agreements (verify dataset IDs first);
   - **placebo outcome**: same pipeline with `primary_vacate_reason = 'Illegal Occupancy'`. If
     Class C/unit predicts it as strongly as fire, the signal is HPD attention, not fire risk;
   - split by building size (3–5 units vs larger); rerun with 180- and 365-day gaps.

## Open questions

- **Fire-vacate jump from FY2025 (cause unknown, revisit before Phase 2 and Phase 4).**
  Fire-damage vacates in `tb8q-a3ar` by fiscal year: FY24 287, FY25 436, FY26 578; entire-building
  vacates 35 → 51 → 114. HPD's FY2026 Mayor's Management Report confirms a 37% rise in
  Fire Department vacate orders after fire damage, with no stated reason. FDNY NFIRS "111 - Building
  fire" counts (`tm6d-hbzd`, Jan–Sep) were flat or falling (2024: 1,243; 2025: 1,268), so vacates per
  fire rose: likely a practice change (lower threshold, more inspections), not more fires. Unconfirmed.
  Until resolved: add an event-period flag (before/after 2024-07-01) to cases, report results by
  period, include a period term as a sensitivity check, and label the 2024–2025 temporal holdout as
  spanning the change. FDNY's own vacate list (`n5xc-7jfa`, 357 rows total) is too sparse to cross-check.

## Ideas for later (not in current scope)

Separate research questions, not limited to fire. Each would get its own question, outcome and
write-up; reuse the pipeline and data where it fits.

- **Small buildings (1–2 units, and 3–5): where are living conditions worst?** These buildings are
  largely outside HPD's view, so the signals come from elsewhere: 311 reports, DOB complaints
  (illegal conversion, basement/cellar occupancy), ECB violations, DOB vacates. First step is
  defining "worst conditions" in a way public records can measure, and checking how much each
  source under-counts small buildings.
- **Owner portfolios: can a landlord's track record flag buildings at risk of poor conditions or
  other harms?** Link buildings to common owners/agents via HPD Registration Contacts (`feu5-w2e2`:
  names, corporations, business addresses), as JustFix's "Who Owns What" does; ACRIS for dated
  ownership changes. Test whether patterns across an owner's *other* buildings (violations, vacates,
  litigation, harassment findings) predict outcomes in a given building. Ownership must be
  time-stamped as of each cutoff date to avoid leakage. Define "bad actor" only from objective public
  records (e.g. AEP, Public Advocate Worst Landlords list, court convictions), never by judgment.
  Ground rule 4 applies: results publish as aggregates; no named buildings or landlords unless the
  user explicitly asks and each entry is checked against source records.

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
ANALYSIS_PLAN.md     pre-registered hypotheses, split rule, pass/fail criteria
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
