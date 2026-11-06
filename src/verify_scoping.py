"""Verify every factual claim made in docs/scoping-taxbase-imd.md."""
import os
import warnings

import pandas as pd

warnings.filterwarnings("ignore")
probe = "/Users/alessiomorteo/.hermes/profiles/data-scoper/cache/scratch/probe/"

results = []


def check(name, condition, detail=""):
    results.append((name, condition, detail))
    print(f"  {'PASS' if condition else 'FAIL'}  {name}  {detail if not condition else ''}")


print("=== COUNCIL TAXBASE ===")
xl = pd.ExcelFile(probe + "ctb.xlsx")
check("16 sheets", len(xl.sheet_names) == 16, f"got {len(xl.sheet_names)}")
check("has 'Council Taxbase Data'", "Council Taxbase Data" in xl.sheet_names)

raw = pd.read_excel(probe + "ctb.xlsx", sheet_name="Council Taxbase Data", header=None)
check("303 rows", raw.shape[0] == 303, f"got {raw.shape[0]}")
check("336 cols", raw.shape[1] == 336, f"got {raw.shape[1]}")
check("row 4 has 35 block titles", raw.iloc[4].notna().sum() == 35,
      f"got {raw.iloc[4].notna().sum()}")
check("row 4 col 5 is Table 1.01",
      str(raw.iloc[4, 5]).startswith("Table 1.01"), str(raw.iloc[4, 5])[:40])
check("row 5 col 0 is 'E-code'", str(raw.iloc[5, 0]).strip() == "E-code",
      str(raw.iloc[5, 0]))
check("row 5 col 5 is 'Band A'", str(raw.iloc[5, 5]).strip() == "Band A")
check("row 5 col 13 is 'Total'", str(raw.iloc[5, 13]).strip() == "Total",
      str(raw.iloc[5, 13]))
hdr = [str(h) for h in raw.iloc[5]]
check("31 occurrences of 'Band A'", hdr.count("Band A") == 31, f"got {hdr.count('Band A')}")

body = raw.iloc[6:].copy()
body.columns = range(len(raw.columns))
ons = body[1].astype(str)
valid = body[ons.str.match(r"^E\d{8}$")]
check("297 rows with valid ONS code", len(valid) == 297, f"got {len(valid)}")
check("first row is England E92000001", valid.iloc[0, 1] == "E92000001",
      str(valid.iloc[0, 1]))
non_england = len(valid) - 1
check("296 billing authorities after dropping England", non_england == 296,
      f"got {non_england}")

print("\n=== IMD FILE 10 ===")
xl10 = pd.ExcelFile(probe + "imd_lad.xlsx")
check("11 sheets", len(xl10.sheet_names) == 11, f"got {len(xl10.sheet_names)}")
expected = ["Notes", "IMD", "Income", "Employment", "Education", "Health",
            "Crime", "Barriers", "Living", "IDACI", "IDAOPI"]
check("sheet names match", xl10.sheet_names == expected, str(xl10.sheet_names))

imd = xl10.parse("IMD", header=None)
check("297 data rows (excl header)", len(imd) == 297, f"got {len(imd)}")
check("col 0 is ONS code", imd.iloc[1, 0] == "E06000001", str(imd.iloc[1, 0]))
check("col 1 is LA name", imd.iloc[1, 1] == "Hartlepool", str(imd.iloc[1, 1]))
check("Hartlepool avg score 37.58", abs(float(imd.iloc[1, 4]) - 37.58) < 0.01,
      str(imd.iloc[1, 4]))
check("Hartlepool rank 6", int(imd.iloc[1, 5]) == 6, str(imd.iloc[1, 5]))

blackpool = imd[imd[1] == "Blackpool"]
check("Blackpool avg score 43.467",
      abs(float(blackpool.iloc[0, 4]) - 43.467) < 0.01, str(blackpool.iloc[0, 4]))
check("Blackpool rank 1", int(blackpool.iloc[0, 5]) == 1, str(blackpool.iloc[0, 5]))

warrington = imd[imd[1] == "Warrington"]
check("Warrington avg score 16.835",
      abs(float(warrington.iloc[0, 4]) - 16.835) < 0.01, str(warrington.iloc[0, 4]))
check("Warrington rank 174", int(warrington.iloc[0, 5]) == 174, str(warrington.iloc[0, 5]))

print("\n=== IMD FILE 1 (LSOA) ===")
xl1 = pd.ExcelFile(probe + "imd_lsoa.xlsx")
check("2 sheets", len(xl1.sheet_names) == 2, str(xl1.sheet_names))
check("sheets are Notes, IMD25", xl1.sheet_names == ["Notes", "IMD25"])
lsoa = xl1.parse("IMD25", header=None)
check("33,756 LSOA rows", len(lsoa) == 33756, f"got {len(lsoa)}")
check("col 0 is LSOA code", str(lsoa.iloc[1, 0]).startswith("E01"), str(lsoa.iloc[1, 0]))
check("col 2 is LA code", str(lsoa.iloc[1, 2]).startswith("E09"), str(lsoa.iloc[1, 2]))

print("\n=== JOIN CLAIM ===")
ours = pd.read_csv(os.path.expanduser(
    "~/uk-council-tax/data/processed/uk_council_tax_full.csv"))
eng = ours[ours.nation == "England"]
tb = valid.iloc[1:][[1]].rename(columns={1: "ons"})
m = eng.merge(tb, left_on="LAD24CD", right_on="ons", how="left")
matched = int(m["ons"].notna().sum())
check("292 of 294 English councils match", matched == 292 and len(eng) == 294,
      f"matched {matched} of {len(eng)}")
unmatched = sorted(m[m["ons"].isna()]["authority"].tolist())
check("unmatched are Barnsley and Sheffield",
      unmatched == ["Barnsley", "Sheffield"], str(unmatched))

print()
fails = [r for r in results if not r[1]]
print(f"{len(results) - len(fails)}/{len(results)} claims verified")
if fails:
    print("FAILURES:", [f[0] for f in fails])
    raise SystemExit(1)
print("all claims in the scoping doc verified against the files.")
