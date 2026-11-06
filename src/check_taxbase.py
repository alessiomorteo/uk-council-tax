"""Check the parsed taxbase against each nation's published tax base.

The key check: the published Band D equivalent tax base is not
``dwellings x statutory ratio``. It applies discounts, premiums and exemptions
first, so the naive product overstates it. This script quantifies that gap and
confirms the parsed published figures match the source publications.
"""
import sys
import warnings
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import DATA_PROC, ladder  # noqa: E402

warnings.filterwarnings("ignore")
results = []


def check(name, cond, detail=""):
    """Record and print a single assertion."""
    results.append((name, cond))
    print(f"  {'PASS' if cond else 'FAIL'}  {name}  {'' if cond else detail}")


tb = pd.read_csv(DATA_PROC / "taxbase_long.csv")
LATEST = {"England": "2025-26", "Wales": "2026-27", "Scotland": "2026-27"}

print("=== TAXBASE LONG TABLE ===")
print(f"rows: {len(tb):,}")
print(tb.groupby("nation").agg(
    rows=("dwellings", "size"),
    authorities=("authority", "nunique"),
    bands=("band", "nunique"),
    years=("year", "nunique"),
).to_string())

print("\n=== DWELLINGS AND PUBLISHED TAX BASE, LATEST YEAR ===")
rows = []
for nation, year in LATEST.items():
    group = tb[(tb.nation == nation) & (tb.year == year)]
    bands = group[group.band != "Total"]
    total = group[group.band == "Total"]

    dwellings = bands.dwellings.sum()
    mult = ladder(nation, year)
    naive = (bands.dwellings * bands.band.map(mult)).sum()
    published = total.tax_base.sum()

    rows.append({
        "nation": nation,
        "year": year,
        "authorities": bands.authority.nunique(),
        "bands": bands.band.nunique(),
        "dwellings": int(dwellings),
        "naive_bde": round(naive),
        "published_bde": round(published),
        "gap_pct": round((naive - published) / published * 100, 2) if published else None,
    })

summary = pd.DataFrame(rows)
print(summary.to_string(index=False))

print("\n=== ASSERTIONS ===")
check("England has 296 authorities", summary.loc[0, "authorities"] == 296)
check("Wales has 22 authorities", summary.loc[1, "authorities"] == 22)
check("Scotland has 32 authorities", summary.loc[2, "authorities"] == 32)
check("England has 8 bands", summary.loc[0, "bands"] == 8)
check("Wales has 9 bands (Band I)", summary.loc[1, "bands"] == 9)
check("Scotland has 8 bands", summary.loc[2, "bands"] == 8)

# England published tax base, Table 1.29
check("England published tax base is 21,731,127",
      abs(summary.loc[0, "published_bde"] - 21731127) < 5,
      str(summary.loc[0, "published_bde"]))
# Wales E1
check("Wales published tax base is 1,329,256",
      abs(summary.loc[1, "published_bde"] - 1329256) < 5,
      str(summary.loc[1, "published_bde"]))
# Scotland Band D equivalents workbook
check("Scotland published tax base is 2,428,273",
      abs(summary.loc[2, "published_bde"] - 2428273) < 5,
      str(summary.loc[2, "published_bde"]))

# The naive product must overstate, consistently, in every nation.
check("naive overstates in all three nations",
      (summary.gap_pct > 0).all(), str(summary.gap_pct.tolist()))
check("naive overstates by 5 to 15 per cent everywhere",
      summary.gap_pct.between(5, 15).all(), str(summary.gap_pct.tolist()))

# England dwellings cross-check against the published aggregate.
raw = pd.read_excel(
    DATA_PROC.parent / "raw" / "taxbase_england_2025.xlsx",
    sheet_name="Council Taxbase Data", header=None)
published_total = int(raw.iloc[6, 13])
eng_dwellings = int(summary.loc[0, "dwellings"])
check(f"England dwellings match published {published_total:,}",
      eng_dwellings == published_total, f"got {eng_dwellings:,}")

print()
fails = [r for r in results if not r[1]]
print(f"{len(results) - len(fails)}/{len(results)} checks passed")
if fails:
    print("FAILURES:", [f[0] for f in fails])
    raise SystemExit(1)
