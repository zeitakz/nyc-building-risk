# NYC Building Risk Signals

Can New York City's public housing and building records flag residential buildings at higher risk
of a serious fire *before* it happens? This project tests which records, and which patterns of
owner neglect, show up more often in buildings that later burned than in similar buildings on the
same block.

**Status:** pilot complete, full-scale study in progress. See the [project site](https://zeitakz.github.io/nyc-building-risk/).

## Pilot result (small sample)

Seven NYC buildings that HPD vacated for fire damage in January 2025 were each compared with
similar residential buildings on their own block (137 in total), using only records from before 2025.

- Their HPD Class C ("immediately hazardous") violations per apartment ranked on average at the
  **87th percentile** of their block (permutation test p ≈ 0.001).
- Four of the seven had the highest Class C rate of any comparable building on the block.
- DOB violation history alone did not distinguish them.

Seven cases are a lead, not a finding. The full study scales this to every fire-damage vacate since 2018.

## Repo

| Path | What |
|---|---|
| `pilot/` | The original small-sample studies (fire and structural collapse) and their scripts |
| `pipeline/` | Numbered pipeline: download → cases → matched controls → features → models |
| `site/` | Quarto website, published to GitHub Pages |
| `CLAUDE.md` | Detailed spec: data sources, join keys, study design, definitions of done |

## Reproduce

```bash
pip install -r requirements.txt
python pilot/fire_analyze.py          # pilot result
python pipeline/01_download.py --list # available datasets
quarto preview site                   # local site
```

## Data

All data is public, from [NYC Open Data](https://opendata.cityofnewyork.us/): HPD violations and
vacate orders, DOB violations, complaints and permits, ECB violations, PLUTO, and 311. Raw data is
not stored in this repo; the pipeline downloads it.

## Responsible use

A risk signal is a reason to look more closely at a building, not proof that an owner caused a
fire. The site publishes aggregate patterns. It does not publish lists of individual buildings or
landlords.
