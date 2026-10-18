"""Download raw Survey of Consumer Finances (SCF) files from the Federal Reserve.

All files come from https://www.federalreserve.gov/econres/files/ and are saved
unmodified under data/raw/. Run from anywhere:

    python get_data.py            # download anything missing, then verify
    python get_data.py --verify   # only verify files already on disk

Existing files are never silently overwritten: a file already on disk is kept
if it passes an integrity check; if it fails, it is renamed to *.corrupt-<time>
before being downloaded again. Every file is recorded in data/raw/MANIFEST.csv
with its source URL, size, SHA-256 hash, and download time.
"""

import argparse
import csv
import datetime as dt
import hashlib
import io
import sys
import zipfile
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw"
MANIFEST = RAW / "MANIFEST.csv"
BASE_URL = "https://www.federalreserve.gov/econres/files/"
HEADERS = {"User-Agent": "ps158-wealth-lab research script (python-requests)"}

# Every triennial SCF with modern public microdata, 1989 through the latest (2025).
ALL_YEARS = [1989, 1992, 1995, 1998, 2001, 2004, 2007, 2010, 2013, 2016, 2019, 2022, 2025]

# Parents' education (X6032/X6033 and spouse X6132/X6133) was first asked in 2016.
PARENT_EDUC_YEARS = [2016, 2019, 2022, 2025]

# Bootstrap replicate weights (999 replicates, implicate 1 only) for
# sampling standard errors. Extend this list to get errors for other years.
REPLICATE_YEARS = [2025]

# Codebook file names are not uniform across years.
CODEBOOKS = {
    1989: "codebk89.txt", 1992: "codebk92.txt", 1995: "codebk95.txt",
    1998: "codebk98.txt", 2001: "codebk2001.txt", 2004: "codebk2004.txt",
    2007: "codebk2007.txt", 2010: "codebk2010.txt", 2013: "codebk2013.txt",
    2016: "codebk2016.txt", 2019: "codebk2019.txt", 2022: "codebk2022.txt",
    2025: "codebk2025.txt",
}

DOCS = [
    "bulletin.macro.txt",  # Fed SAS macro defining NETWORTH etc. and CPI-U-RS factors
    "2016_scf_changes.txt",  # documents the 2016 addition of parents' education
    "2019_scf_changes.txt",
    "2022_scf_changes.txt",
    "2025_scf_changes.pdf",
    "Standard_Error_Documentation.pdf",  # how to combine imputation and sampling error
    "scf2025_tables_public_real_historical.xlsx",  # official medians, for benchmarking
]

# Census Bureau, "Wealth, Asset Ownership, & Debt of Households Detailed
# Tables: 2024" (SIPP), from
# https://www.census.gov/data/tables/2024/demo/wealth/wealth-asset-ownership.html
SIPP_URL = ("https://www2.census.gov/programs-surveys/demo/tables/wealth/2023/"
            "wealth-asset-ownership/wealth_tables_dy2024.xlsx")

# Variables each Stata file must contain for the planned analysis. A tuple
# lists acceptable alternatives (the 1989 extract uses x1/xx1 as case IDs).
REQUIRED_VARS = {
    "full": ["yy1", "y1", "x42001", "x6032", "x6033", "x6132", "x6133", "x8000"],
    "summary": [("yy1", "xx1"), ("y1", "x1"), "wgt", "networth", "edcl", "age", "married"],
    "replicate": ["y1", "wt1b1", "wt1b999", "mm1", "mm999"],
}


def build_targets():
    """Return a list of (url, local path, kind) for every file to fetch."""
    targets = []
    for year in ALL_YEARS:
        # Summary Extract Public Data (Stata): NETWORTH etc., in 2025 dollars.
        name = f"scfp{year}s.zip"
        targets.append((BASE_URL + name, RAW / "scf_summary_extract" / name, "summary"))
        targets.append((BASE_URL + CODEBOOKS[year], RAW / "codebooks" / CODEBOOKS[year], "text"))
    for year in PARENT_EDUC_YEARS:
        # Full public data set (Stata): needed for parents' education items.
        name = f"scf{year}s.zip"
        targets.append((BASE_URL + name, RAW / "scf_full_public" / name, "full"))
    for year in REPLICATE_YEARS:
        name = f"scf{year}rw1s.zip"
        targets.append((BASE_URL + name, RAW / "scf_replicate_weights" / name, "replicate"))
    for name in DOCS:
        targets.append((BASE_URL + name, RAW / "docs" / name, "text"))
    # Independent comparison source: Census Bureau SIPP wealth tables, 2024.
    targets.append((SIPP_URL, RAW / "external" / "census_sipp" / SIPP_URL.rsplit("/", 1)[1], "text"))
    return targets


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def is_intact(path, kind):
    """Cheap integrity check: zips must pass a CRC test, other files be non-empty."""
    if not path.exists() or path.stat().st_size == 0:
        return False
    if path.suffix == ".zip":
        try:
            with zipfile.ZipFile(path) as z:
                return z.testzip() is None
        except zipfile.BadZipFile:
            return False
    if path.suffix in (".txt",):
        # Guard against an HTML error page saved under a .txt name.
        head = path.read_bytes()[:512].lower()
        return b"<html" not in head and b"<!doctype" not in head
    return True


def download(url, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    with requests.get(url, headers=HEADERS, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    tmp.rename(dest)


def fetch_all(targets):
    records = []
    for url, dest, kind in targets:
        rel = dest.relative_to(ROOT)
        if dest.exists():
            if is_intact(dest, kind):
                print(f"keep      {rel} (already present and intact)")
                status = "existing"
            else:
                stamp = dt.datetime.now().strftime("%Y%m%d%H%M%S")
                backup = dest.with_name(f"{dest.name}.corrupt-{stamp}")
                dest.rename(backup)
                print(f"WARNING   {rel} failed integrity check; moved to {backup.name}")
                download(url, dest)
                status = "redownloaded"
        else:
            print(f"download  {url}")
            download(url, dest)
            status = "downloaded"
        if not is_intact(dest, kind):
            sys.exit(f"ERROR: {rel} failed integrity check after download")
        records.append({
            "file": str(rel),
            "url": url,
            "bytes": dest.stat().st_size,
            "sha256": sha256(dest),
            "status": status,
            "checked_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        })
    return records


def write_manifest(records):
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(records[0]))
        w.writeheader()
        w.writerows(records)
    print(f"\nWrote {MANIFEST.relative_to(ROOT)} ({len(records)} files)")


def stata_columns(zip_path):
    """Read only the variable list from the single .dta file inside a zip."""
    with zipfile.ZipFile(zip_path) as z:
        members = [m for m in z.namelist() if m.lower().endswith(".dta")]
        if len(members) != 1:
            raise ValueError(f"{zip_path.name}: expected one .dta, found {members}")
        buf = io.BytesIO(z.read(members[0]))
    with pd.io.stata.StataReader(buf) as reader:
        return members[0], [c.lower() for c in reader.variable_labels()]


def verify_contents(targets):
    """Confirm each Stata file contains the variables the analysis needs."""
    print("\nVerifying variables inside Stata files:")
    ok = True
    for _, dest, kind in targets:
        if kind not in REQUIRED_VARS:
            continue
        member, cols = stata_columns(dest)
        wanted = [v if isinstance(v, tuple) else (v,) for v in REQUIRED_VARS[kind]]
        missing = ["/".join(alts) for alts in wanted if not any(a in cols for a in alts)]
        flag = "OK" if not missing else "MISSING " + ", ".join(missing)
        print(f"  {dest.relative_to(ROOT)} -> {member}: {len(cols)} vars, {flag}")
        ok &= not missing
    if not ok:
        sys.exit("ERROR: some required variables are missing (see above)")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--verify", action="store_true", help="verify files on disk without downloading")
    args = parser.parse_args()

    targets = build_targets()
    if args.verify:
        bad = [d for _, d, k in targets if not is_intact(d, k)]
        if bad:
            sys.exit("Missing or corrupt:\n  " + "\n  ".join(str(b.relative_to(ROOT)) for b in bad))
    else:
        write_manifest(fetch_all(targets))
    verify_contents(targets)
    print("\nAll raw files present and verified.")


if __name__ == "__main__":
    main()
