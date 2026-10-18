"""Standard errors for SCF medians and means, following the Fed's MEANIT macro.

MEANIT is published in the SCF codebook (section "SAMPLING ERROR"; see
data/raw/codebooks/codebk2025.txt). This is a direct port for medians and
means (the macro computes both):

* Imputation variance: the variance (n-1 denominator) of the weighted median
  computed separately in each of the 5 implicates, using X42001 (= 5 * WGT).
* Sampling variance: the variance (n-1 denominator) of the weighted median
  across the 999 bootstrap replicates, using implicate 1 only, with each
  replicate weight WT1Bk multiplied by its multiplicity MMk (negative or
  missing values set to 0, as in the macro).
* Total standard error = sqrt((6/5) * imputation variance + sampling variance).

The point estimate is the median pooled over all implicates (as in the
macro's PROC UNIVARIATE step and in process_data.py). The same replicate
machinery gives errors for the college/high-school gap and ratio.

Writes data/processed/standard_errors_<year>.csv.
"""

import argparse
import io
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"

AGE_MIN, AGE_MAX = 25, 64
N_REP = 999


def read_stata_from_zip(path, columns=None):
    with zipfile.ZipFile(path) as z:
        (member,) = [m for m in z.namelist() if m.lower().endswith(".dta")]
        buf = io.BytesIO(z.read(member))
    return pd.read_stata(buf, columns=columns, convert_categoricals=False)


def weighted_median(values, weights):
    """Smallest value at which the cumulative weight reaches half the total."""
    order = np.argsort(values, kind="mergesort")
    v, w = np.asarray(values)[order], np.asarray(weights)[order]
    cum = np.cumsum(w)
    return float(v[np.searchsorted(cum, 0.5 * cum[-1])])


def replicate_medians(values, rep_weights):
    """Weighted median of values under each column of rep_weights (n x R)."""
    order = np.argsort(values, kind="mergesort")
    v, w = values[order], rep_weights[order]
    cum = np.cumsum(w, axis=0)
    idx = (cum >= 0.5 * cum[-1]).argmax(axis=0)
    return v[idx]


def load(year):
    ext = read_stata_from_zip(RAW / "scf_summary_extract" / f"scfp{year}s.zip",
                              ["yy1", "y1", "wgt", "networth", "age", "kids", "edcl"])
    # Cast first: the IDs are stored as small integers and 10 * yy1 overflows.
    ext["implicate"] = ext["y1"].astype("int64") - 10 * ext["yy1"].astype("int64")
    if not ext["implicate"].isin([1, 2, 3, 4, 5]).all():
        raise ValueError("implicate numbers outside 1-5")
    ext["wgt0"] = ext["wgt"] * 5  # X42001, the weight the macro uses
    rw = read_stata_from_zip(RAW / "scf_replicate_weights" / f"scf{year}rw1s.zip")
    rw.columns = [c.lower() for c in rw.columns]
    wt = rw[[f"wt1b{k}" for k in range(1, N_REP + 1)]].fillna(0).clip(lower=0).to_numpy()
    mm = rw[[f"mm{k}" for k in range(1, N_REP + 1)]].fillna(0).clip(lower=0).to_numpy()
    rep = pd.DataFrame(wt * mm, columns=[f"r{k}" for k in range(1, N_REP + 1)])
    rep["y1"] = rw["y1"].to_numpy()
    imp1 = ext[ext.implicate == 1].merge(rep, on="y1", how="left", validate="one_to_one")
    if imp1["r1"].isna().any():
        raise ValueError("some implicate-1 cases have no replicate weights")
    return ext, imp1


def replicate_means(values, rep_weights):
    # Explicit sum rather than `@`: numpy 2.0's macOS matmul emits spurious
    # overflow warnings on this data.
    return (rep_weights * values[:, None]).sum(axis=0) / rep_weights.sum(axis=0)


STATS = {
    "median": (weighted_median, replicate_medians),
    "mean": (lambda v, w: float(np.average(v, weights=w)), replicate_means),
}


def estimate(ext, imp1, subsets, stats=("median",)):
    """Point estimates and SEs for each statistic of each subset, plus gap and ratio."""
    rep_cols = [f"r{k}" for k in range(1, N_REP + 1)]
    rows = []
    for stat in stats:
        rows += _estimate_stat(ext, imp1, subsets, stat, rep_cols)
    return pd.DataFrame(rows)


def _estimate_stat(ext, imp1, subsets, stat, rep_cols):
    point_fn, rep_fn = STATS[stat]
    point, by_imp, by_rep = {}, {}, {}
    for name, cond in subsets.items():
        d = ext[cond(ext)]
        point[name] = point_fn(d.networth, d.wgt)
        by_imp[name] = np.array([point_fn(g.networth, g.wgt0) for _, g in d.groupby("implicate")])
        r = imp1[cond(imp1)]
        by_rep[name] = rep_fn(r.networth.to_numpy(dtype=float), r[rep_cols].to_numpy())

    rows = []

    def add(stat, est, imp, rep):
        iv, rv = np.var(imp, ddof=1), np.var(rep, ddof=1)
        se = np.sqrt(1.2 * iv + rv)
        rows.append({"statistic": stat, "estimate": est, "se_total": se,
                     "se_imputation": np.sqrt(iv), "se_sampling": np.sqrt(rv),
                     "ci95_low": est - 1.96 * se, "ci95_high": est + 1.96 * se})

    prefix = "" if stat == "median" else f"{stat}_"
    for name in subsets:
        add(f"{stat}_{name}", point[name], by_imp[name], by_rep[name])
    if {"college", "hs_or_less"} <= set(subsets):
        add(f"{prefix}gap_college_minus_hs", point["college"] - point["hs_or_less"],
            by_imp["college"] - by_imp["hs_or_less"], by_rep["college"] - by_rep["hs_or_less"])
        add(f"{prefix}ratio_college_to_hs", point["college"] / point["hs_or_less"],
            by_imp["college"] / by_imp["hs_or_less"], by_rep["college"] / by_rep["hs_or_less"])
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--year", type=int, default=2025)
    year = parser.parse_args().year

    ext, imp1 = load(year)
    sample = lambda d: d.age.between(AGE_MIN, AGE_MAX) & (d.kids >= 1)
    subsets = {
        "college": lambda d: sample(d) & (d.edcl == 4),
        "hs_or_less": lambda d: sample(d) & d.edcl.isin([1, 2]),
        # All families with a college-graduate reference person: the Fed
        # publishes this median (Table 4), so it anchors the comparison.
        "college_all_families": lambda d: d.edcl == 4,
        # The Fed publishes a standard error for this one (all families),
        # which checks this port of MEANIT.
        "all_families": lambda d: d.edcl > 0,
    }
    res = estimate(ext, imp1, subsets, stats=("median", "mean"))
    res.insert(0, "year", year)
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / f"standard_errors_{year}.csv"
    res.to_csv(out, index=False)
    print(f"{year}, 2025 dollars. Sample for college/hs_or_less: families with children, "
          f"reference person aged {AGE_MIN}-{AGE_MAX}.")
    print(res.round(3).to_string(index=False))
    print(f"\nWrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
