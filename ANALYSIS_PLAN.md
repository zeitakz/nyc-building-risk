# Analysis plan (pre-registered)

**Written 2026-11-17, before any Phase 2 output (cases, controls, features or models) existed.**
The git commit that adds this file is the timestamp. Changes after that date go in
[Deviations](#deviations) with a date and reason; the original text stays.

Question: can NYC public records flag privately owned multiple dwellings at higher risk of a
serious fire, and which patterns of conditions and owner behavior go with that risk?

## 1. Population, cases, controls

As in `CLAUDE.md` → Study design:

- **Population:** private multiple dwellings: PLUTO `unitsres >= 3`, not NYCHA, residential class
  (A, B, C, D, R, S), built before 2000.
- **Case:** first HPD vacate order with `primary_vacate_reason = 'Fire Damage'` per BBL,
  `vacate_effective_date` 2018-01-01 to 2025-12-31. Event date = `vacate_effective_date`.
- **Controls:** up to 10 per case from the same block (else census tract), population rules above,
  `unitsres` within 1/3×–3× of the case's, no fire vacate 2018–2025. Case + controls = one
  **match set**, identified by the case BBL.
- **Cutoff:** event date − 60 days. Every feature uses only records dated before the cutoff.
- **Event period:** flag cases before / on-or-after 2024-07-01 (vacate practice changed; see
  `CLAUDE.md` → Open questions).

## 2. Primary hypothesis (one test)

> Buildings that later receive a fire-damage vacate had more **HPD Class C violations per
> residential unit** in the **3 years before cutoff** than their matched controls.

- **Model:** conditional logistic regression grouped by match set.
- **Predictor:** log2(1 + Class C violations per unit, 3-year lookback), so the odds ratio is per
  doubling. Covariates: log(units), building age at event date.
- **Data:** all match sets (this test was specified before seeing data, so it doesn't use the
  discovery/confirmation split).
- **Supported if** both hold:
  1. the 95% CI for the odds ratio excludes 1, with OR > 1; and
  2. the same model with **Illegal Occupancy** vacates as the outcome (placebo; same matching
     rules) gives an OR whose point estimate is below the fire OR's 95% CI lower bound.
  If (1) holds but (2) fails, report it as "consistent with HPD attention, not specific to fire."
- **Sensitivity checks** (reported, they don't change the verdict): gaps of 180 and 365 days;
  lookbacks of 1 and 5 years and all prior history; cases before 2024-07-01 only; a period
  interaction term; HPD complaint count as a covariate; 3–5 units vs larger.

## 3. Secondary hypotheses (Holm-corrected; see Amendment 1, which adds a fifth)

Same model and data as the primary test. Each predictor is a per-unit count over a 3-year lookback
from HPD violations **and** HPD complaints, using the keyword/category rules in
`pipeline/hpd_categories.yml`. Those rules are written and committed **before** features are
computed against cases.

1. **Ignition sources:** electrical/wiring (including wiring run through dumbwaiter shafts or
   motorized dumbwaiters), gas, stove/range defects.
2. **Detection and spread (compartmentation):** smoke/CO detectors, self-closing doors, open or
   unsealed shafts and **dumbwaiter** doors/shafts, fire escapes/egress.
3. **Owner response:** share of the building's Class B+C violations still open 90 days after
   issue (buildings with no B/C violations: 0, plus a "no B/C violations" indicator).
4. **Building equipment and systems neglect:** DOB elevator violations (`E`, `EVCAT*`; not
   `EGRADE`, `EARCX` or `EGNCY`, which are energy and emergency codes), HPD violations mentioning
   elevators, DOB boiler filing violations (`LBLVIO`, `LL6291`). Because only buildings with
   elevators can get elevator violations, this model adds log(floors) and an "elevator building"
   indicator (any DOB `E`/`EVCAT*` record ever, or `numfloors >= 6`), so it tests neglected
   equipment rather than having equipment.

Holm correction across the four at α = 0.05. Dumbwaiter records are also reported on their own
as a descriptive count (cases vs controls), with no significance test, because they're rare
(about 390 buildings citywide since 2010 have dumbwaiter door/shaft violations; about 50 have
wiring in a dumbwaiter shaft).

## 4. Discovery and confirmation

To find signals we didn't think to guess, without being fooled by chance.

**Split rule, fixed now.** A match set goes to **confirmation** if

```
int(sha256(("nyc-building-risk:" + case_bbl).encode()).hexdigest(), 16) % 100 < 35
```

where `case_bbl` is the case's 10-digit BBL as a string; otherwise it goes to **discovery**.
That's about 35% confirmation, 65% discovery. Implemented in `pipeline/splits.py`. Controls follow
their match set. No one looks at confirmation-set features or outcomes until step 3 below.

1. **Discovery (65%).** Compute every candidate feature over the 3-year lookback:
   - each HPD violation category and each novdescription n-gram (1–3 words, with standard text and
     location boilerplate removed, e.g. "AT PUBLIC HALL, 3rd STORY"), appearing in at least
     20 discovery-set buildings;
   - each HPD complaint major/minor category and problem code;
   - each DOB violation type, ECB violation type/severity, and DOB complaint category;
   - each 311 complaint type/descriptor from the downloaded subset;
   - trends: change in counts between years 3–2 and the last year before cutoff.

   Rank features by within-match-set association: a univariate conditional logit per feature,
   with Benjamini–Hochberg FDR across all candidates. Exploratory LightGBM + SHAP on the same set
   looks for interactions; it can nominate candidates but not confirm them.
2. **Promotion.** Promote up to **10** features: those with BH q < 0.10, ordered by p-value; if
   fewer than 10 pass, promote only those. Group near-duplicates (e.g. n-grams from the same
   violation code) into one feature before promoting. The list is committed before step 3.
3. **Confirmation (35%).** Test each promoted feature with the same univariate conditional logit
   on the confirmation set. **Confirmed** = same direction as in discovery and Holm-adjusted
   p < 0.05 across the promoted set.
4. **Reporting.** All promoted features are published, confirmed or not. Discoveries are labeled
   exploratory unless confirmed. Each confirmed signal gets the placebo check and a short note on
   possible explanations (hazard, building-type marker, HPD-attention marker, aftermath leakage).

## 5. Prediction (separate from the tests above)

Temporal holdout as in `CLAUDE.md`: fit on events 2018–2023, evaluate ranking on 2024–2025 (AUC
within match sets, top-decile capture). Labeled as spanning the 2024–25 change in vacate practice.

## 6. Reporting rules

- Every result states its sample size and main caveat.
- Aggregates only; no named buildings or landlords (ground rule 4).
- Null and failed-confirmation results are reported as prominently as positive ones.

## Deviations

Format: date — what changed — why — whether results had been seen.

### Amendment 1 — 2026-11-17 (before any results)

**Results seen at the time: none.** No cases, controls or features had been built. The only data
looked at was citywide: which values exist in the HPD, 311 and DOB datasets, and FDNY Bureau of
Fire Investigations cause counts by season (no addresses, so they can't be linked to buildings).
Reason: ideas from a planning discussion on the same day as the original plan.

1. **New secondary hypothesis 5: heat and gas outages.** Outages push tenants to space heaters,
   ovens and hot plates. Predictor: per-unit count over the 3-year lookback of
   - HPD heat/hot water violations and complaints;
   - "no gas" records: HPD violations to "provide an adequate supply of gas" (§ 27-2070), and HPD
     complaints *range: no gas*, *no gas or electricity*, *pilot light out*;
   - 311 HPD `HEAT/HOT WATER` / `HEATING` reports.

   Holm correction now runs across **five** secondary hypotheses.
2. **Hypotheses 1 and 2 widened** (the definitions add items; the tests are unchanged):
   - H1 ignition adds appliance gas leaks (shut-off valve leaking, flex hose broken, gas fumes,
     gas leak), sparking outlets at appliances, and broken/missing stove knobs and knob covers.
   - H2 detection/spread adds air-conditioner units obstructing fire-escape windows or egress.
     Most HPD air-conditioner violations are of this kind, not electrical.
3. **Season as an effect modifier** (pre-specified, reported whatever the result, not pass/fail).
   Event season = cold (Nov–Mar) or warm (May–Sep); April and October are excluded from this
   analysis only. Two interaction terms: H5 outages × cold, and H1 electrical × warm. Background
   from the FDNY data: space heaters and candles are mostly winter causes; extension cords and
   lithium-ion batteries are more common in summer.
4. **Construction permits** on the lot and on adjacent lots in the year before cutoff are added to
   discovery as a feature family. DOB NOW permits (`rbx6-tga4`) start around 2016; earlier permits
   need the DOB BIS permit dataset (ID to verify).
5. **Keyword rules.** `pipeline/hpd_categories.yml` uses whole-word matching. For example, "range"
   must not match "arrange", which turned up in a sample stove violation about garbage collection.
   Each category is committed with a sample of matched and unmatched violation texts reviewed by
   the user, before any feature is computed against cases.
6. **No belief-based ranking of features.** We considered labeling features in advance as
   "direct / indirect / remote" fire hazards and decided against it. Instead, the discovery
   report shows the full distribution of associations. If many unrelated-looking features predict
   fire about equally, that is reported as evidence of a general neglect or attention signal,
   not a fire-specific one. Appliance-neglect signals (such as refrigerator door seals, a possible
   marker of old equipment) stay in discovery.
7. **Known blind spots, to state on the site:** clothes dryers (FDNY recorded about 220 dryer fires
   in multiple dwellings, but HPD has only about 450 dryer violations, because laundry rooms are
   rarely inspected); lithium-ion batteries and fans (almost no housing records). The discovery
   text and 311 features may pick up indirect traces.
