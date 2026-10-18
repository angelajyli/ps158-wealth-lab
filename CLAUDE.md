# ps158-wealth-lab

How family net worth differs by education in the Federal Reserve's Survey of
Consumer Finances (SCF), 1989–2025.

## Pipeline

Run from the repo root with the project virtualenv:

```bash
.venv/bin/python get_data.py          # download + verify raw files (idempotent)
.venv/bin/python process_data.py      # processed tables + check against Fed Table 4
.venv/bin/python standard_errors.py   # 2025 standard errors (Fed MEANIT method)
.venv/bin/python compare_sources.py   # SCF vs Census SIPP comparison
.venv/bin/python plot.py              # figures/*.png
.venv/bin/python make_readme.py       # README.md, numbers recomputed from raw data
```

## Data rules

- Use official sources only (federalreserve.gov, census.gov). Never invent data, variables, or URLs.
- `data/raw/` is read-only: `get_data.py` keeps intact files and never silently overwrites them.
  Add new sources to `get_data.py` so they stay reproducible and appear in `MANIFEST.csv`.
- Use relative paths that resolve from the script's own location.
- Never clean, analyze, or plot before the user approves the data findings.

## Measurement rules (approved by the user)

- **Parents' education** (X6032 mother, X6033 father of the reference person) exists only in 2016, 2019, 2022 and 2025.
  - College group: at least one parent has a bachelor's degree or higher.
  - High school or less group: neither parent went past a high school diploma.
  - Some college or associate degree: kept in the data, not plotted.
- **Own education** (EDCL) is a different measure, used only for the separate 1989–2025 chart.
  - Never splice it onto the parents' series.
  - Never substitute one measure for the other without explicit approval.
- **Sample:** families with children (Fed `KIDS` ≥ 1, any age) whose reference person is aged 25–64.
- **Dollars:** `NETWORTH` in the Summary Extract is already in 2025 dollars (CPI-U-RS). Do not re-deflate it.
- **Weights:** pool all five implicates weighted by `WGT`, which equals X42001 / 5.
  - Cast the ID variables `y1`/`yy1` to int64 before arithmetic, because they overflow otherwise.
- **Validation:** medians and means must reproduce Fed Table 4. `process_data.py` aborts above 0.5% difference.
- **Standard errors:** follow the Fed's MEANIT method, sqrt(1.2 × imputation variance + replicate variance).
  - Use 999 replicate weights × multiplicity, on implicate 1 only.

## Figure and writing rules

- Every figure states:
  - source;
  - price base (2025 dollars);
  - units;
  - sample;
  - that it's descriptive, not causal.
- Say "reference person", not "head", and name whose education it is (theirs or their parents').
- "College" means a bachelor's degree or higher, not "went to college".
- Before calling a figure done, check every printed number against `data/processed/`.
- Never type numbers into the README or other docs by hand, and never read them off a figure.
  They must be computed from the original source by a script (`make_readme.py`).
- Report margins of error with any claim about change over time.
- Medians describe the typical family. Means are driven by the top 10%, so label them clearly.
