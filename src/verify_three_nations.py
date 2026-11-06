"""Verify the England + Wales + Scotland taxbase and deprivation sources."""
import os
import warnings

import pandas as pd

warnings.filterwarnings("ignore")
probe = "/Users/alessiomorteo/.hermes/profiles/data-scoper/cache/scratch/probe/"
results = []


def check(name, cond, detail=""):
    results.append((name, cond))
    print(f"  {'PASS' if cond else 'FAIL'}  {name}  {'' if cond else detail}")


# ---------------------------------------------------------------- ENGLAND
print("=== ENGLAND taxbase ===")
raw = pd.read_excel(probe + "ctb.xlsx", sheet_name="Council Taxbase Data", header=None)
body = raw.iloc[6:].copy()
body.columns = range(len(raw.columns))
ons = body[1].astype(str)
eng = body[ons.str.match(r"^E\d{8}$") & (body[1] != "E92000001")]
check("296 English billing authorities", len(eng) == 296, f"got {len(eng)}")

print("\n=== WALES taxbase ===")
wt = pd.read_csv(probe + "wales_taxbase.csv")
check("31 years", wt.Year.nunique() == 31, f"got {wt.Year.nunique()}")
check("has 2026-27", "2026-27" in wt.Year.unique())
check("bands A-I plus Total", set(wt.Band.unique()) >= {"A", "B", "C", "D", "E", "F", "G", "H", "I"},
      str(sorted(wt.Band.unique())))
check("22 authorities plus total", wt.Authority.nunique() == 23, f"got {wt.Authority.nunique()}")
check("64 row types", wt.Row.nunique() == 64, f"got {wt.Row.nunique()}")

cur = wt[(wt.Year == "2026-27") & (wt.Row.str.startswith("A1"))]
check("A1 all chargeable dwellings present", len(cur) > 0, f"got {len(cur)}")

print("\n=== SCOTLAND taxbase ===")
xl = pd.ExcelFile(probe + "scot_taxbase.xlsx")
check("single sheet", len(xl.sheet_names) == 1, str(xl.sheet_names))
st = xl.parse(xl.sheet_names[0], header=None)
check("Band A-H header on row 4",
      all(str(st.iloc[4, c]).strip() == f"Band {b}" for c, b in
          zip(range(1, 9), "ABCDEFGH")),
      str([st.iloc[4, c] for c in range(1, 9)]))
check("Scotland total row present", str(st.iloc[7, 0]).strip() == "Scotland",
      str(st.iloc[7, 0]))
raw_names = st.iloc[8:, 0].dropna().tolist()
councils = [n for n in raw_names
            if not str(n).strip().lower().startswith(("source", "note"))]
check("34 raw rows incl 2 prose notes", len(raw_names) == 34, f"got {len(raw_names)}")
check("32 Scottish councils after filtering prose", len(councils) == 32,
      f"got {len(councils)}")
check("Scotland Band D total is 373124", int(st.iloc[7, 4]) == 373124,
      str(st.iloc[7, 4]))

# ---------------------------------------------------------------- DEPRIVATION
print("\n=== ENGLAND IMD ===")
imd = pd.ExcelFile(probe + "imd_lad.xlsx")
check("11 sheets", len(imd.sheet_names) == 11, str(len(imd.sheet_names)))
imd_imd = imd.parse("IMD", header=None)
check("297 LA rows", len(imd_imd) == 297, f"got {len(imd_imd)}")

print("\n=== WALES WIMD ===")
wimd = pd.read_csv(probe + "wales_wimd.csv")
check("22 areas", wimd["Area code"].nunique() == 22, f"got {wimd['Area code'].nunique()}")
check("9 domains", wimd.Domain.nunique() == 9, f"got {wimd.Domain.nunique()}")
check("W0600 codes", wimd["Area code"].astype(str).str.startswith("W06").all())
check("has deprivation groups", "Most deprived 10% LSOAs in Wales (ranks 1-191)"
      in wimd["Deprivation group"].unique())

print("\n=== SCOTLAND SIMD ===")
simd = pd.read_csv(probe + "simd.csv")
check("has GeographyCode", "GeographyCode" in simd.columns)
check("has Simd Domain", "Simd Domain" in simd.columns)
check("has Value", "Value" in simd.columns)
types = simd.GeographyType.unique()
check("CSV is data zones only", list(types) == ["2011 Data Zones"], str(types))
check("CSV has no council field", not any("ouncil" in c for c in simd.columns))

lookup = pd.ExcelFile(probe + "simd_lookup.xlsx").parse(
    "SIMD 2020v2 DZ lookup data", header=None)
lookup.columns = lookup.iloc[0]
lookup = lookup.iloc[1:]
check("lookup has 6,976 data zones", len(lookup) == 6976, f"got {len(lookup)}")
check("lookup carries LAcode", "LAcode" in lookup.columns)
check("lookup has 32 council areas", lookup.LAcode.nunique() == 32,
      f"got {lookup.LAcode.nunique()}")

# ---------------------------------------------------------------- JOINS
print("\n=== JOINS TO EXISTING DATA ===")
ours = pd.read_csv(os.path.expanduser(
    "~/uk-council-tax/data/processed/uk_council_tax_full.csv"))
counts = ours.groupby("nation").size().to_dict()
check("existing data has 294 England", counts.get("England") == 294, str(counts))
check("existing data has 22 Wales", counts.get("Wales") == 22, str(counts))
check("existing data has 32 Scotland", counts.get("Scotland") == 32, str(counts))

# Scotland council names vs SIMD council areas
import sys
sys.path.insert(0, "src")
from config import norm_name

scot_names = set(ours[ours.nation == "Scotland"].authority)
simd_names = set(lookup.LAname.dropna().unique())
raw_overlap = scot_names & simd_names
check("raw name overlap is 28 of 32", len(raw_overlap) == 28, f"got {len(raw_overlap)}")

norm_overlap = {norm_name(n) for n in scot_names} & {norm_name(n) for n in simd_names}
check("norm_name resolves all 32", len(norm_overlap) == 32, f"got {len(norm_overlap)}")

print()
fails = [r for r in results if not r[1]]
print(f"{len(results) - len(fails)}/{len(results)} verified")
if fails:
    print("FAILURES:", [f[0] for f in fails])
    raise SystemExit(1)
