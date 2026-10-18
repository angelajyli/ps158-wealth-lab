"""Compare SCF 2025 median net worth with the Census Bureau's SIPP 2024 tables.

The SIPP tables do not cross education with children or age, so the SCF
cell used in the figures (families with children, reference person aged
25-64, bachelor's degree or higher) has no direct SIPP counterpart. Instead,
this script rebuilds SCF medians on the SIPP's own published definitions:

* All households.
* Households with at least one member under 18 (SIPP "One or more children
  under 18"). In the SCF: any household-roster member (persons 3-12,
  X108/X110 ... X226/X228) aged under 18.
* Highest education in the household: bachelor's degree, and graduate or
  professional degree. SIPP uses every household member; the SCF only asks
  the reference person (X5931) and spouse/partner (X6111), so the SCF uses
  the higher of those two.

Differences that remain by construction: SIPP values are in 2024 dollars
for 2024, SCF values in 2025 dollars for 2025; SIPP's unit is the household,
the SCF's is the primary economic unit (usually the same household).

Writes data/processed/compare_scf_sipp.csv.
"""

from pathlib import Path

import pandas as pd

import standard_errors as se

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"
SIPP_FILE = RAW / "external" / "census_sipp" / "wealth_tables_dy2024.xlsx"

# Household roster, persons 3-12: (relationship, age) variable pairs.
ROSTER = [(f"x{r}", f"x{r + 2}") for r in (108, 114, 120, 126, 132, 202, 208, 214, 220, 226)]

SIPP_ROWS = {
    "all": "Total",
    "children_under_18": "One or more children under 18",
    "bachelors": "Bachelor's degree",
    "graduate": "Graduate or professional degree",
}


def sipp_medians():
    t1 = pd.read_excel(SIPP_FILE, sheet_name="Table 1", header=None)
    t1a = pd.read_excel(SIPP_FILE, sheet_name="Table 1A", header=None)
    if "2024" not in str(t1.iloc[1, 0]) or str(t1.iloc[2, 1]).strip() != "Net Worth":
        raise ValueError("SIPP Table 1 layout is not as expected")
    labels = t1[0].astype(str).str.strip()
    out = {}
    for key, label in SIPP_ROWS.items():
        row = labels.index[labels == label][0]  # first match: "Total" recurs lower down
        out[key] = (float(t1.iloc[row, 1]), float(t1a.iloc[row, 1]))
    return out


def scf_data(year=2025):
    ext, imp1 = se.load(year)
    cols = ["yy1", "y1", "x5931", "x6111"] + [v for pair in ROSTER for v in pair]
    full = se.read_stata_from_zip(RAW / "scf_full_public" / f"scf{year}s.zip", cols)
    # Person ages: 0 means no such person; ages are top/bottom-coded in the
    # public data but "under 18" is unaffected.
    has_child = pd.concat([(full[a] > 0) & (full[a] < 18) for _, a in ROSTER], axis=1).any(axis=1)
    full["any_under_18"] = has_child
    full["educ_max_couple"] = full[["x5931", "x6111"]].max(axis=1)  # x6111 = 0 if no spouse
    keep = ["y1", "any_under_18", "educ_max_couple"]
    ext = ext.merge(full[keep], on="y1", how="left", validate="one_to_one")
    imp1 = imp1.merge(full[keep], on="y1", how="left", validate="one_to_one")
    return ext, imp1


def main():
    sipp = sipp_medians()
    ext, imp1 = scf_data()
    subsets = {
        "all": lambda d: d.edcl > 0,
        "children_under_18": lambda d: d.any_under_18,
        "bachelors": lambda d: d.educ_max_couple == 12,
        "graduate": lambda d: d.educ_max_couple.isin([13, 14]),
    }
    scf = se.estimate(ext, imp1, subsets).set_index("statistic")

    rows = []
    for key, label in SIPP_ROWS.items():
        s = scf.loc[f"median_{key}"]
        sipp_med, sipp_se = sipp[key]
        rows.append({
            "group": label,
            "scf_2025_median_2025usd": s.estimate,
            "scf_se": s.se_total,
            "sipp_2024_median_2024usd": sipp_med,
            "sipp_se": sipp_se,
            "scf_over_sipp": s.estimate / sipp_med,
        })
    res = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    res.to_csv(OUT / "compare_scf_sipp.csv", index=False)
    print(res.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
