"""Line charts of median and mean family net worth by education.

Reads the summary tables made by process_data.py and writes separate figures
(the two education measures are never combined on one chart). Each figure
below also has a mean version, figures/mean_networth_by_*.png:

    figures/median_networth_by_parent_educ.png
        By parents' education (the reference person's mother and father),
        2016-2025, the only years the SCF asked about it.
    figures/median_networth_by_own_educ.png
        By the reference person's own education, 1989-2025.

Both use the analysis sample: families with children, reference person aged
25-64. All values are in 2025 dollars.
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.ticker import FuncFormatter

ROOT = Path(__file__).resolve().parent
PROCESSED = ROOT / "data" / "processed"
FIG_DIR = ROOT / "figures"

SURFACE = "#fcfcfb"
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
GRID = "#e4e3df"
COLORS = {"college": "#2a78d6", "hs_or_less": "#eb6834"}

SAMPLE_NOTE = ("Sample: families with children (Fed KIDS variable, any age) whose reference person is aged 25-64. "
               "Weighted medians pooled across the five imputations.")

CHARTS = [
    {
        "summary": "median_networth_by_parent_educ.csv",
        "definition": "ref",
        "stat": "median",
        "ratio_col": "ratio_college_to_hs",
        "out": "median_networth_by_parent_educ.png",
        "labels": {"college": "Reference person's mother or father has a bachelor's degree or higher",
                   "hs_or_less": "Neither of the reference person's parents went past a high school diploma"},
        "title": ("In {year}, families with children in which the reference person's mother or father had a "
                  "bachelor's degree\nhad a median net worth of {college}, {ratio:.1f} times that of families "
                  "in which neither parent went past high school"),
        "subtitle": ("Median net worth of families with children (reference person aged 25-64) "
                     "by parents' education, thousands of 2025 dollars"),
        "note": [
            "Source: Federal Reserve Board, Survey of Consumer Finances 2016, 2019, 2022, 2025 (public microdata). "
            "Net worth: Fed NETWORTH measure, 2025 dollars (CPI-U-RS).",
            "Parents' education: mother and father of the household's reference person (X6032, X6033). "
            "Families whose most-educated parent has some college or an associate degree are not shown.",
            SAMPLE_NOTE,
            "Parents' education was not asked before 2016. No sampling standard errors shown. "
            "Descriptive comparison, not an estimate of a causal effect.",
        ],
    },
    {
        "summary": "median_networth_by_own_educ.csv",
        "definition": "own",
        "stat": "median",
        "ratio_col": "ratio_college_to_hs",
        "out": "median_networth_by_own_educ.png",
        "labels": {"college": "Reference person has a bachelor's degree or higher",
                   "hs_or_less": "Reference person has a high school diploma or less"},
        "title": ("In {year}, families with children whose reference person had a bachelor's degree had a "
                  "median net worth\nof {college}, {ratio:.1f} times that of families whose reference person "
                  "had a high school education or less"),
        "subtitle": ("Median net worth of families with children (reference person aged 25-64) "
                     "by own education, thousands of 2025 dollars"),
        "note": [
            "Source: Federal Reserve Board, Survey of Consumer Finances 1989-2025 (Summary Extract public data). "
            "Net worth: Fed NETWORTH measure, 2025 dollars (CPI-U-RS).",
            "Education: the reference person's OWN education (Fed EDCL variable), not their parents'. "
            "Families whose reference person has some college or an associate degree are not shown.",
            SAMPLE_NOTE,
            "The education question changed in 2016; the Fed maps both versions to the same groups. "
            "No sampling standard errors shown. Descriptive comparison, not an estimate of a causal effect.",
        ],
    },
]


def dollars_k(x, _pos):
    if abs(x) >= 1e6:
        return "$" + f"{x / 1e6:,.2f}".rstrip("0").rstrip(".") + "M"
    return f"${x / 1000:,.0f}k"


def mean_version(chart):
    """The same chart showing weighted means instead of medians."""
    mean = dict(chart, stat="mean", ratio_col="mean_ratio_college_to_hs",
                out=chart["out"].replace("median_", "mean_"))
    mean["title"] = chart["title"].replace("a median net worth", "a mean net worth")
    mean["subtitle"] = (chart["subtitle"].replace("Median net worth", "Mean net worth")
                        .replace("thousands of 2025 dollars", "2025 dollars"))
    mean["note"] = [line.replace("Weighted medians", "Weighted means") for line in chart["note"]]
    mean["note"].append("Means are pulled up by the wealthiest families in each group; "
                        "medians describe the typical family.")
    return mean


def draw(chart):
    df = pd.read_csv(PROCESSED / chart["summary"])
    df = df[df["definition"] == chart["definition"]].sort_values("year")
    years = df["year"].tolist()

    plt.rcParams.update({"font.family": "sans-serif", "font.size": 10})
    fig, ax = plt.subplots(figsize=(10, 6.4), facecolor=SURFACE)
    ax.set_facecolor(SURFACE)

    stat = chart["stat"]
    for group, label in chart["labels"].items():
        y = df[f"{stat}_networth_{group}"]
        ax.plot(years, y, color=COLORS[group], linewidth=2, marker="o", markersize=7,
                markeredgecolor=SURFACE, markeredgewidth=2, label=label, zorder=3)
        # Selective direct labels: first and last value only.
        for x_, y_, ha in [(years[0], y.iloc[0], "right"), (years[-1], y.iloc[-1], "left")]:
            offset = -10 if ha == "right" else 10
            ax.annotate(dollars_k(y_, None), (x_, y_), xytext=(offset, 0),
                        textcoords="offset points", ha=ha, va="center",
                        color=TEXT_PRIMARY, fontsize=10)

    last = df.iloc[-1]
    ax.set_title(
        chart["title"].format(year=int(last.year), college=dollars_k(last[f"{stat}_networth_college"], None),
                              ratio=last[chart["ratio_col"]]),
        loc="left", fontsize=12, color=TEXT_PRIMARY, pad=34,
    )
    ax.text(0, 1.025, chart["subtitle"], transform=ax.transAxes, color=TEXT_SECONDARY, fontsize=10)

    pad = 0.09 * (years[-1] - years[0])  # room for the first/last value labels
    ax.set_xticks(years)
    ax.set_xlim(years[0] - pad, years[-1] + pad)
    ax.set_ylim(0, max(df[f"{stat}_networth_college"]) * 1.18)
    ax.yaxis.set_major_formatter(FuncFormatter(dollars_k))
    ax.set_xlabel("Survey year", color=TEXT_SECONDARY)
    ax.set_ylabel(f"{stat.capitalize()} net worth (2025 dollars)", color=TEXT_SECONDARY)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.tick_params(colors=TEXT_SECONDARY, length=0)
    for side in ["top", "right", "left"]:
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)

    ax.legend(loc="upper left", frameon=False, labelcolor=TEXT_PRIMARY, fontsize=10)
    fig.text(0.01, 0.01, "\n".join(chart["note"]), ha="left", va="bottom", fontsize=7.3,
             color=TEXT_SECONDARY, linespacing=1.5)
    fig.tight_layout(rect=(0, 0.025 * len(chart["note"]), 1, 1))

    FIG_DIR.mkdir(exist_ok=True)
    out = FIG_DIR / chart["out"]
    fig.savefig(out, dpi=200, facecolor=SURFACE)
    plt.close(fig)
    print(f"Saved {out.relative_to(ROOT)}")


def main():
    for chart in CHARTS:
        draw(chart)
        draw(mean_version(chart))


if __name__ == "__main__":
    main()
