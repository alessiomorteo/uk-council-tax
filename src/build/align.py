"""Align nations on the ratio axis and validate against the statutory ladders.

This is the analytical core: it asserts that every published charge equals
multiplier x Band D for its nation and year, which is what makes a cross-nation
burden comparison legitimate.
"""
import sys
import warnings
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import BANDS, DATA_PROC, ladder  # noqa: E402

warnings.filterwarnings("ignore")

RATIO_TOL = 1e-3


def add_ratios(df: pd.DataFrame) -> pd.DataFrame:
    """Attach the expected multiplier, the Band D charge, and the actual ratio."""
    df = df.copy()
    df["ratio_expected"] = [
        ladder(n, y).get(b) for n, y, b in zip(df.nation, df.year, df.band)
    ]
    bd = (df[df.band == "D"][["nation", "authority", "year", "charge_gbp"]]
          .rename(columns={"charge_gbp": "band_d"}))
    df = df.merge(bd, on=["nation", "authority", "year"], how="left")
    df["ratio_actual"] = df["charge_gbp"] / df["band_d"]
    return df


def validate(df: pd.DataFrame) -> pd.DataFrame:
    """Assert charge/band_d == statutory multiplier on every row."""
    checks = []
    for b in BANDS:
        sub = df[(df.band == b) & df.ratio_expected.notna() & df.ratio_actual.notna()]
        for nation, g in sub.groupby("nation"):
            dev = (g.ratio_actual - g.ratio_expected).abs()
            checks.append({
                "nation": nation,
                "band": b,
                "n": len(g),
                "expected": round(float(g.ratio_expected.iloc[0]), 6),
                "max_dev": round(float(dev.max()), 8),
                "rows_off": int((dev > RATIO_TOL).sum()),
            })
    return pd.DataFrame(checks)


def nation_multipliers(df: pd.DataFrame) -> pd.DataFrame:
    """Nation-level ladder, plus the Scotland-vs-England gap."""
    piv = df.pivot_table(index="band", columns="nation",
                         values="ratio_actual", aggfunc="median")
    piv = piv.reindex(BANDS)
    if "Scotland" in piv and "England" in piv:
        piv["Scot_vs_Eng_%"] = ((piv["Scotland"] / piv["England"] - 1) * 100).round(1)
    return piv


def main():
    print("Aligning and validating")

    cur = pd.read_csv(DATA_PROC / "uk_bands_2026-27.csv")
    aligned = add_ratios(cur)
    aligned.to_csv(DATA_PROC / "uk_bands_aligned_2026-27.csv", index=False)
    print(f"  uk_bands_aligned_2026-27.csv  {len(aligned):>6,} rows")

    checks = validate(aligned)
    checks.to_csv(DATA_PROC / "ratio_validation.csv", index=False)
    total_off = int(checks.rows_off.sum())
    total_n = int(checks.n.sum())
    print(f"  ratio_validation.csv          {total_off} violations of {total_n:,} checks")

    mult = nation_multipliers(aligned)
    mult.round(6).to_csv(DATA_PROC / "nation_multipliers.csv")
    print(f"  nation_multipliers.csv        {len(mult)} bands")

    # within-nation uniformity: is the ladder a national constant?
    print("\n  ladder uniformity within each nation:")
    for nation, g in aligned.groupby("nation"):
        worst = 0.0
        for b in BANDS:
            s = g[g.band == b]["ratio_actual"].dropna()
            if len(s) > 1:
                worst = max(worst, float(s.max() - s.min()))
        verdict = "uniform" if worst < 1e-4 else "VARIES"
        print(f"    {nation:10s} max spread {worst:.8f}  -> {verdict}")

    if total_off:
        print("\n  FAILURES:")
        print(checks[checks.rows_off > 0].to_string(index=False))
        raise SystemExit(1)
    print("\n  all ratio checks passed.")


if __name__ == "__main__":
    main()
