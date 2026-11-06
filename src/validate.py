"""Assert the invariants this dataset depends on.

Run: python3 src/validate.py   (or `make test`)
Exits non-zero on any failure.
"""
import sys
import warnings
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (BANDS, DATA_PROC, ENGLAND_WALES, SCOTLAND_POST_2017,  # noqa: E402
                    SCOTLAND_PRE_2017, ladder)

warnings.filterwarnings("ignore")

FAILURES = []


def check(name, condition, detail=""):
    if condition:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}  {detail}")
        FAILURES.append(name)


def main():
    print("Validating processed data\n")

    aligned = pd.read_csv(DATA_PROC / "uk_bands_aligned_2026-27.csv")
    full = pd.read_csv(DATA_PROC / "uk_council_tax_full.csv")
    mult = pd.read_csv(DATA_PROC / "nation_multipliers.csv", index_col=0)

    # 1. ratio identity on every row
    dev = (aligned.ratio_actual - aligned.ratio_expected).abs()
    check("ratio identity (charge / Band D == statutory multiplier)",
          bool((dev.dropna() < 1e-3).all()),
          f"max deviation {dev.max():.6f}")

    # 2. expected coverage
    bands = pd.read_csv(DATA_PROC / "uk_bands_2026-27.csv")
    band_counts = bands.drop_duplicates(["nation", "authority"]).groupby("nation").size().to_dict()
    check("England has 296 billing authorities", band_counts.get("England") == 296, band_counts)
    check("Wales has 22 unitary authorities", band_counts.get("Wales") == 22, band_counts)
    check("Scotland has 32 councils", band_counts.get("Scotland") == 32, band_counts)

    # the affordability file drops exactly the ONS-suppressed councils
    counts = full.groupby("nation").size().to_dict()
    check("affordability drops exactly 2 English councils (ONS suppressed)",
          counts.get("England") == 294, counts)
    suppressed = {"City of London", "Isles of Scilly"}
    eng_band = set(bands[bands.nation == "England"].authority)
    eng_full = set(full[full.nation == "England"].authority)
    check("the dropped councils are the ONS-suppressed ones",
          eng_band - eng_full == suppressed, eng_band - eng_full)

    # 3. no duplicate council rows
    dup = full.duplicated(subset=["nation", "authority"]).sum()
    check("no duplicate councils", dup == 0, f"{dup} duplicates")

    # 4. every council has all eight bands
    for b in "ABCDEFGH":
        nulls = full[f"band_{b.lower()}"].isna().sum()
        check(f"band {b} complete", nulls == 0, f"{nulls} nulls")

    # 5. the ladder is a national constant
    for nation, g in aligned.groupby("nation"):
        worst = 0.0
        for b in BANDS:
            s = g[g.band == b]["ratio_actual"].dropna()
            if len(s) > 1:
                worst = max(worst, float(s.max() - s.min()))
        check(f"{nation} ladder uniform across councils", worst < 1e-4, f"spread {worst:.8f}")

    # 6. the Scotland reform is present and dated
    check("Scotland post-2017 Band H is 2.450",
          abs(SCOTLAND_POST_2017["H"] - 2.45) < 1e-9)
    check("Scotland pre-2017 Band H is 2.000",
          abs(SCOTLAND_PRE_2017["H"] - 2.0) < 1e-9)
    check("ladder() switches at 2017",
          ladder("Scotland", "2016-17")["H"] == 2.0
          and abs(ladder("Scotland", "2017-18")["H"] - 2.45) < 1e-9)

    # 7. England and Wales share the A-H ladder
    for b in "ABCDEFGH":
        check(f"England/Wales band {b} share multiplier",
              abs(ENGLAND_WALES[b] - ladder("England", "2026-27")[b]) < 1e-12)

    # 8. Wales has a ninth band, England and Scotland do not
    check("Wales has Band I at 21/9", abs(ENGLAND_WALES["I"] - 21 / 9) < 1e-9)
    check("Scotland has no Band I", "I" not in SCOTLAND_POST_2017)

    # 9. affordability sanity
    check("affordability within plausible bounds",
          full.band_d_pct_pay.between(0, 20).all(),
          f"{full.band_d_pct_pay.min():.2f}-{full.band_d_pct_pay.max():.2f}%")
    check("Wandsworth is the most affordable",
          full.loc[full.band_d_pct_pay.idxmin(), "authority"] == "Wandsworth")
    check("Nottingham is the least affordable",
          full.loc[full.band_d_pct_pay.idxmax(), "authority"] == "Nottingham")

    # 10. nation multipliers
    check("Scotland Band H multiplier is 2.45x",
          abs(mult.loc["H", "Scotland"] - 2.45) < 1e-4)
    check("England Band H multiplier is 2.00x",
          abs(mult.loc["H", "England"] - 2.0) < 1e-4)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURES: {FAILURES}")
        raise SystemExit(1)
    print("all checks passed.")


if __name__ == "__main__":
    main()
