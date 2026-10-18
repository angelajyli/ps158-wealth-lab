"""Build processed SCF datasets on family net worth by education.

Two analyses, kept separate because they measure different things:

  A. Parents' education (the adults' own mothers and fathers), 2016-2025 --
     the only years the SCF asked about it.
  B. The reference person's own education, 1989-2025. In this sample of
     families with children, that is the education of a parent of those
     children. It is NOT the same measure as A and is never spliced onto it.

Reads the raw zips saved by get_data.py (never modifies them) and writes:

    data/processed/scf_parent_educ_microdata.csv
        One row per family x implicate, all families: weight, net worth, age,
        number of children, parents' education codes, derived groups, and an
        in_sample flag for the analysis sample.
    data/processed/median_networth_by_parent_educ.csv
        Weighted median and mean net worth by group and year, gap, and ratio.
    data/processed/scf_own_educ_microdata.csv
        One row per family x implicate, all families, 1989-2025: weight, net
        worth, age, number of children, EDCL, own-education group, in_sample.
    data/processed/median_networth_by_own_educ.csv
        Weighted median and mean net worth by own-education group and year,
        1989-2025 (the file name predates the means).
    data/processed/benchmark_fed_table4.csv
        Our medians vs the Fed's published Table 4 (all families and by
        education of reference person), every year 1989-2025 (sanity check).

Method
------
* Sample: families whose reference person is aged 25-64 and that have at
  least one child (the Fed's KIDS variable: own, step-, or foster children of
  the reference person or spouse/partner living in the household, any age).
  The benchmark check uses all families, to match the Fed's published table.
* Net worth: NETWORTH from the Fed's Summary Extract, already expressed in
  2025 dollars (CPI-U-RS) by the Fed.
* Parents' education: X6032 (mother) and X6033 (father) of the reference
  person, from the full public file; spouse/partner's parents are X6132/X6133.
  Public codes: -1 or 1 = less than high school diploma, 8 = high school
  graduate, 9 = some college or associate degree, 12 = bachelor's or higher.
* Grouping (primary, "reference person" definition): take the higher of the
  two parents' education.
      college     = at least one parent has a bachelor's degree or higher
      hs_or_less  = neither parent went beyond a high school diploma
      some_college = highest-educated parent has some college / associate
  The some_college group is kept in the data but is not part of the
  two-group comparison.
* Sensitivity ("couple" definition): the same rule applied to all parents of
  the reference person and, if present, the spouse/partner (up to 4 parents).
* Weights and implicates: the extract weight WGT equals X42001 / 5, so the
  five implicates are pooled and weighted by WGT. This is how the Fed computes
  its published medians; the benchmark file checks that we reproduce them.
  We also report the range of medians across the five implicates separately,
  which shows how much imputation alone moves the estimate.
* Own education (analysis B): the Fed's EDCL variable from the Summary
  Extract (1 = no high school diploma/GED, 2 = high school diploma/GED,
  3 = some college or associate degree, 4 = bachelor's degree or higher).
  The Fed maps the pre-2016 years-of-schooling question (X5901-X5905) and the
  2016+ highest-degree question (X5931-X5933) onto the same four classes.
      college    = EDCL 4
      hs_or_less = EDCL 1 or 2
      some_college (EDCL 3) is kept in the data but not compared.
* No sampling standard errors: those need the replicate-weight files, which
  were not downloaded.
"""

import io
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"

YEARS = [2016, 2019, 2022, 2025]  # parents' education available
ALL_YEARS = [1989, 1992, 1995, 1998, 2001, 2004, 2007, 2010, 2013, 2016, 2019, 2022, 2025]
FULL_VARS = ["yy1", "y1", "x6032", "x6033", "x6132", "x6133"]
EXTRACT_VARS = ["yy1", "y1", "wgt", "networth", "age", "kids", "edcl"]

# Analysis sample: reference person aged 25-64, family has children.
AGE_MIN, AGE_MAX = 25, 64

# Fed published median net worth, thousands of 2025 dollars
# (Table 4 of scf2025_tables_public_real_historical.xlsx, read below).
BENCHMARK_FILE = RAW / "docs" / "scf2025_tables_public_real_historical.xlsx"
# Table 4 row label -> rows of our data it covers (None = all families).
BENCHMARK_ROWS = {"All families": None, "No high school diploma": [1],
                  "High school diploma": [2], "Some college": [3], "College degree": [4]}

PARENT_EDUC_LABELS = {-1: "less than high school", 1: "less than high school",
                      8: "high school diploma", 9: "some college or associate",
                      12: "bachelor's or higher"}
GROUP_LABELS = {"college": "At least one parent has a bachelor's degree or higher",
                "some_college": "Highest-educated parent has some college or an associate degree",
                "hs_or_less": "Neither parent has more than a high school diploma"}


def read_stata_from_zip(path, columns):
    with zipfile.ZipFile(path) as z:
        (member,) = [m for m in z.namelist() if m.lower().endswith(".dta")]
        buf = io.BytesIO(z.read(member))
    return pd.read_stata(buf, columns=columns, convert_categoricals=False)


def classify(highest):
    """Map the highest parental education code to an analysis group."""
    return pd.Series(
        np.select([highest >= 12, highest == 9, highest <= 8],
                  ["college", "some_college", "hs_or_less"], default=None),
        index=highest.index,
    )


def load_extract(year):
    """Summary Extract for one year. The 1989 file names its case IDs x1/xx1."""
    path = RAW / "scf_summary_extract" / f"scfp{year}s.zip"
    ids = {"y1": "x1", "yy1": "xx1"} if year == 1989 else {}
    ext = read_stata_from_zip(path, [ids.get(c, c) for c in EXTRACT_VARS])
    ext = ext.rename(columns={v: k for k, v in ids.items()})
    if not ext["edcl"].isin([1, 2, 3, 4]).all():
        raise ValueError(f"{year}: unexpected EDCL codes: {sorted(ext['edcl'].unique())}")
    ext["year"] = year
    ext["implicate"] = ext["y1"] % 10
    ext["own_educ_group"] = ext["edcl"].map({1: "hs_or_less", 2: "hs_or_less",
                                             3: "some_college", 4: "college"})
    ext["in_sample"] = ext["age"].between(AGE_MIN, AGE_MAX) & (ext["kids"] >= 1)
    return ext


def load_year(year):
    full = read_stata_from_zip(RAW / "scf_full_public" / f"scf{year}s.zip", FULL_VARS)
    ext = load_extract(year).drop(columns=["year", "implicate", "in_sample"])
    df = ext.merge(full, on=["yy1", "y1"], how="inner", validate="one_to_one")
    if len(df) != len(ext) or len(df) != len(full):
        raise ValueError(f"{year}: extract and full file do not match one-to-one")

    for v in ["x6032", "x6033"]:
        if not df[v].isin(PARENT_EDUC_LABELS).all():
            raise ValueError(f"{year}: unexpected codes in {v}: {sorted(df[v].unique())}")
    # Spouse/partner parents: 0 means no spouse/partner, not an education level.
    for v in ["x6132", "x6133"]:
        if not df[v].isin([0, *PARENT_EDUC_LABELS]).all():
            raise ValueError(f"{year}: unexpected codes in {v}: {sorted(df[v].unique())}")
        df[v] = df[v].where(df[v] != 0)

    df["year"] = year
    df["implicate"] = df["y1"] % 10
    df["parent_educ_max_ref"] = df[["x6032", "x6033"]].max(axis=1)
    df["parent_educ_max_couple"] = df[["x6032", "x6033", "x6132", "x6133"]].max(axis=1)
    df["group_ref"] = classify(df["parent_educ_max_ref"])
    df["group_couple"] = classify(df["parent_educ_max_couple"])
    df["in_sample"] = df["age"].between(AGE_MIN, AGE_MAX) & (df["kids"] >= 1)
    return df


def weighted_median(values, weights):
    """Smallest value at which the cumulative weight reaches half the total."""
    order = np.argsort(values, kind="mergesort")
    v, w = np.asarray(values)[order], np.asarray(weights)[order]
    cum = np.cumsum(w)
    return float(v[np.searchsorted(cum, 0.5 * cum[-1])])


def summarize(df, definitions):
    """definitions maps a definition name to the column holding its groups."""
    rows = []
    for definition, gcol in definitions.items():
        for (year, group), g in df.groupby(["year", gcol]):
            per_imp = [weighted_median(i.networth, i.wgt) for _, i in g.groupby("implicate")]
            rows.append({
                "year": year,
                "definition": definition,
                "group": group,
                "median_networth": weighted_median(g.networth, g.wgt),
                "mean_networth": float(np.average(g.networth, weights=g.wgt)),
                "median_min_implicate": min(per_imp),
                "median_max_implicate": max(per_imp),
                # Average rows per implicate: imputed education can move a
                # few cases between groups from one implicate to another.
                "n_families_sample": len(g) / 5,
                "median_age": weighted_median(g.age, g.wgt),
                "share_of_families_pct": 100 * g.wgt.sum() / df.loc[df.year == year, "wgt"].sum(),
            })
    long = pd.DataFrame(rows)

    wide = long.pivot_table(index=["year", "definition"], columns="group",
                            values=["median_networth", "mean_networth", "n_families_sample",
                                    "share_of_families_pct", "median_age"])
    wide.columns = [f"{stat}_{group}" for stat, group in wide.columns]
    wide = wide.reset_index()
    wide["gap_college_minus_hs"] = wide["median_networth_college"] - wide["median_networth_hs_or_less"]
    wide["ratio_college_to_hs"] = wide["median_networth_college"] / wide["median_networth_hs_or_less"]
    wide["mean_gap_college_minus_hs"] = wide["mean_networth_college"] - wide["mean_networth_hs_or_less"]
    wide["mean_ratio_college_to_hs"] = wide["mean_networth_college"] / wide["mean_networth_hs_or_less"]
    return long, wide


def published_values():
    """Read Fed Table 4 as {(statistic, row label, year): dollars}."""
    t4 = pd.read_excel(BENCHMARK_FILE, sheet_name="Table 4", header=None)
    years_row, stat_row = t4.iloc[2], t4.iloc[3]
    labels = t4[0].astype(str).str.strip()
    out = {}
    for label in BENCHMARK_ROWS:
        row = t4[labels == label].iloc[0]  # first match: the education block
        col_year = None
        for c in t4.columns[1:]:
            if pd.notna(years_row[c]):
                col_year = int(years_row[c])
            stat = str(stat_row[c]).strip().lower()
            if stat in ("median", "mean"):
                out[(stat, label, col_year)] = float(row[c]) * 1000
    return out


def benchmark(ext):
    published = published_values()
    rows = []
    for year in ALL_YEARS:
        y = ext[ext.year == year]
        for label, codes in BENCHMARK_ROWS.items():
            g = y if codes is None else y[y.edcl.isin(codes)]
            ours = {"median": weighted_median(g.networth, g.wgt),
                    "mean": float(np.average(g.networth, weights=g.wgt))}
            for stat, value in ours.items():
                fed = published[(stat, label, year)]
                rows.append({"year": year, "statistic": stat, "category": label, "ours": value,
                             "fed_published": fed, "pct_diff": 100 * (value / fed - 1)})
    return pd.DataFrame(rows)


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    # Check our method against every published Table 4 median, 1989-2025.
    ext = pd.concat([load_extract(y) for y in ALL_YEARS], ignore_index=True)
    bench = benchmark(ext)
    bench.to_csv(OUT / "benchmark_fed_table4.csv", index=False)
    worst = bench.loc[bench.pct_diff.abs().idxmax()]
    print(f"Benchmark vs Fed Table 4: {len(bench)} medians and means checked, largest difference "
          f"{worst.pct_diff:+.3f}% ({worst.statistic}, {worst.category}, {int(worst.year)})")
    if (bench.pct_diff.abs() > 0.5).any():
        print(bench[bench.pct_diff.abs() > 0.5].to_string(index=False))
        raise SystemExit("ERROR: medians do not reproduce the Fed's published figures")

    sample_msg = f"reference person aged {AGE_MIN}-{AGE_MAX}, family has children"

    # A. Parents' education, 2016-2025.
    df = pd.concat([load_year(y) for y in YEARS], ignore_index=True)
    cols = ["year", "yy1", "y1", "implicate", "wgt", "networth", "age", "kids", "in_sample",
            "x6032", "x6033", "x6132", "x6133",
            "parent_educ_max_ref", "parent_educ_max_couple", "group_ref", "group_couple"]
    df[cols].to_csv(OUT / "scf_parent_educ_microdata.csv", index=False)
    long, wide = summarize(df[df["in_sample"]], {"ref": "group_ref", "couple": "group_couple"})
    long.to_csv(OUT / "median_networth_by_parent_educ_long.csv", index=False)
    wide.to_csv(OUT / "median_networth_by_parent_educ.csv", index=False)

    # B. Reference person's own education, 1989-2025.
    cols = ["year", "yy1", "y1", "implicate", "wgt", "networth", "age", "kids", "edcl",
            "own_educ_group", "in_sample"]
    ext[cols].to_csv(OUT / "scf_own_educ_microdata.csv", index=False)
    own_long, own_wide = summarize(ext[ext["in_sample"]], {"own": "own_educ_group"})
    own_long.to_csv(OUT / "median_networth_by_own_educ_long.csv", index=False)
    own_wide.to_csv(OUT / "median_networth_by_own_educ.csv", index=False)

    show = ["year", "definition", "median_networth_college", "median_networth_hs_or_less",
            "ratio_college_to_hs", "mean_networth_college", "mean_networth_hs_or_less",
            "mean_ratio_college_to_hs"]
    print(f"\nSample: {sample_msg}. All dollars are 2025 dollars.")
    print("\nA. Median and mean net worth by PARENTS' education, 2016-2025:")
    print(wide[show].round(2).to_string(index=False))
    print("\nB. Median and mean net worth by reference person's OWN education, 1989-2025:")
    print(own_wide[show].round(2).to_string(index=False))
    print(f"\nWrote processed files to {OUT.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
