"""Build a human review file for pipeline/hpd_categories.yml (ANALYSIS_PLAN.md Amendment 1, item 5).

    python pipeline/review_categories.py

Pulls a sample of real HPD violations from three years via the API, applies the rules, and writes
data/processed/review/category_review.md (git-ignored: contains raw violation text) with, per
category: how much it catches, which violation codes, random matched examples, and "near misses"
(unmatched texts that share a key word, to spot rules that are too narrow). Also lists every HPD
complaint code with its assigned categories.
"""
import collections, json, pathlib, random, re, sys
import requests
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from categorize import Categorizer

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "processed" / "review"
API = "https://data.cityofnewyork.us/resource/{}.json"
SAMPLE_YEARS, PER_YEAR, N_SHOW = (2013, 2019, 2025), 40_000, 12

# words that suggest a category, used only to find near misses
HINTS = {
    "electrical_wiring": r"ELECTR|WIR|OUTLET|SWITCH", "electrical_sparking": r"SPARK",
    "appliance_gas_leak": r"\bGAS\b", "stove_controls": r"KNOB", "unlawful_cooking_space": r"COOKING|HOT ?PLATE",
    "smoke_detector": r"SMOKE", "co_detector": r"CARBON|MONOXIDE", "self_closing_doors": r"CLOS",
    "vertical_openings": r"SHAFT|CHUTE|DUMB", "fire_escape_egress": r"ESCAPE|EGRESS|LADDER|EXIT",
    "egress_obstruction": r"LOCK|GATE|BARS|AIR[- ]?COND", "sprinkler": r"SPRINK",
    "elevator_hpd": r"ELEVAT", "boiler_heat_plant": r"BOILER|BURNER|PLANT", "heat_outage": r"\bHEAT",
    "hot_water_outage": r"HOT WATER", "gas_outage": r"\bGAS\b", "dumbwaiter": r"DUMB",
    "space_heater": r"HEATER", "electric_outage": r"ELECTRIC", "appliance_other": r"RANGE|STOVE|OVEN|REFRIG",
    "illegal_conversion": r"ILLEGAL|ROOMING|CELLAR|DISCONTINUE", "window_guards": r"WINDOW GUARD",
    "water_leaks": r"LEAK", "mold": r"MOLD", "pests": r"ROACH|MICE|RAT|VERMIN|BEDBUG", "lead_paint": r"LEAD",
    "admin_paperwork": r"POST|REGISTRATION|FILE",
}
BOILER = re.compile(r"^\s*(§|SECTION)[^A-Z]*(?:[A-Z.\- ]*(?:CODE|LAW|MDL|HMC|RCNY)[^A-Z]*)*:?\s*", re.I)

def fetch_violations():
    rows = []
    for y in SAMPLE_YEARS:
        r = requests.get(API.format("wvxf-dwi5"), params={
            "$select": "violationid,ordernumber,class,novdescription",
            "$where": f"inspectiondate between '{y}-01-01' and '{y}-12-31T23:59:59'",
            "$order": "violationid", "$limit": PER_YEAR}, timeout=900)
        r.raise_for_status(); rows += r.json()
    return rows

def fetch_complaint_codes():
    r = requests.get(API.format("ygpa-z7cr"), params={
        "$select": "major_category,minor_category,problem_code,count(*) as n",
        "$group": "major_category,minor_category,problem_code", "$order": "n DESC", "$limit": 5000}, timeout=900)
    r.raise_for_status(); return r.json()

def short(t, n=190):
    t = re.sub(r"\s+", " ", BOILER.sub("", t or "")).strip()
    return t[:n] + ("…" if len(t) > n else "")

def main():
    cat, rnd = Categorizer(), random.Random(17)
    viols = fetch_violations()
    for v in viols: v["cats"] = cat.violation(v.get("ordernumber"), v.get("novdescription"))
    N = len(viols)
    L = [f"# Category review — {N:,} HPD violations sampled from {', '.join(map(str, SAMPLE_YEARS))}\n",
         "For each category: share of sampled violations caught, the violation codes it catches, random",
         "matched examples (do these belong?) and near misses (unmatched texts sharing a key word — should",
         "any of these be in?). Mark anything wrong; rules are in `pipeline/hpd_categories.yml`.\n"]
    other = sum(1 for v in viols if not v["cats"])
    L.append(f"Violations in no category (\"other\"): {other:,} ({100*other/N:.1f}%)\n")
    for name in cat.names:
        m = [v for v in viols if name in v["cats"]]
        hint = re.compile(HINTS.get(name, r"$^"), re.I)
        miss = [v for v in viols if name not in v["cats"] and hint.search(v.get("novdescription") or "")]
        codes = collections.Counter(v.get("ordernumber") for v in m).most_common(8)
        L += [f"\n## {name}  ·  {cat.meta[name]['hypothesis']}",
              f"{cat.meta[name]['description'].strip()}" if cat.meta[name]["description"] else "",
              f"\n**Caught:** {len(m):,} ({100*len(m)/N:.2f}%) · **codes:** " + ", ".join(f"{c} ({n:,})" for c, n in codes),
              "\n**Matched examples**"]
        L += [f"- `{v.get('ordernumber')}` [{v.get('class')}] {short(v.get('novdescription'))}" for v in rnd.sample(m, min(N_SHOW, len(m)))] or ["- (none in sample)"]
        L += [f"\n**Near misses** ({len(miss):,} unmatched with a hint word)"]
        if miss:
            by_code = collections.Counter(v.get("ordernumber") for v in miss).most_common(5)
            L.append("Most common codes among near misses: " + ", ".join(f"{c} ({n:,})" for c, n in by_code))
        L += [f"- `{v.get('ordernumber')}` [{v.get('class')}] {short(v.get('novdescription'))}" for v in rnd.sample(miss, min(8, len(miss)))] or ["- (none)"]
    comp = fetch_complaint_codes()
    L += ["\n\n# Every HPD complaint code and its categories\n", "| count | major / minor / problem | categories |", "|---:|---|---|"]
    unassigned = 0
    for c in comp:
        s = sorted(cat.complaint(c.get("major_category"), c.get("minor_category"), c.get("problem_code")))
        if not s: unassigned += int(c["n"])
        L.append(f"| {int(c['n']):,} | {c.get('major_category')} / {c.get('minor_category')} / {c.get('problem_code')} | {', '.join(s) or '—'} |")
    tot = sum(int(c["n"]) for c in comp)
    L.insert(4, f"Complaint problems in no category: {unassigned:,} of {tot:,} ({100*unassigned/tot:.1f}%)\n")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "category_review.md").write_text("\n".join(L))
    summary = {n: sum(1 for v in viols if n in v["cats"]) for n in cat.names}
    print(json.dumps({"sample": N, "other": other, **summary}, indent=0))

if __name__ == "__main__":
    main()
