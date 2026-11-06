"""Align the nations on the ratio axis and validate against statute.

This is the analytical core. It asserts that every published charge equals the
statutory multiplier times Band D for its nation and year, which is what makes a
cross-nation burden comparison legitimate.
"""

import sys
import warnings
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import BANDS, DATA_PROC, ladder  # noqa: E402

warnings.filterwarnings("ignore")

# Published figures are rounded, so allow a small absolute tolerance.
RATIO_TOLERANCE: float = 1e-3

# Spread above this is real variation rather than rounding noise.
UNIFORMITY_TOLERANCE: float = 1e-4


def add_ratios(frame: pd.DataFrame) -> pd.DataFrame:
    """Attach the expected multiplier, the Band D charge and the actual ratio.

    Args:
        frame: Long-format charges with ``nation``, ``authority``, ``year``,
            ``band`` and ``charge_gbp`` columns.

    Returns:
        A copy of the frame with ``ratio_expected``, ``band_d`` and
        ``ratio_actual`` added.
    """
    aligned = frame.copy()
    aligned["ratio_expected"] = [
        ladder(nation, year).get(band)
        for nation, year, band in zip(aligned.nation, aligned.year, aligned.band)
    ]

    band_d = (
        aligned[aligned.band == "D"][["nation", "authority", "year", "charge_gbp"]]
        .rename(columns={"charge_gbp": "band_d"})
    )
    aligned = aligned.merge(band_d, on=["nation", "authority", "year"], how="left")
    aligned["ratio_actual"] = aligned["charge_gbp"] / aligned["band_d"]
    return aligned


def validate(frame: pd.DataFrame) -> pd.DataFrame:
    """Compare every charge against its statutory multiplier.

    Args:
        frame: Output of :func:`add_ratios`.

    Returns:
        One row per nation and band, reporting the row count, the expected
        multiplier, the largest absolute deviation and how many rows breach the
        tolerance.
    """
    checks: list[dict[str, object]] = []
    for band in BANDS:
        subset = frame[
            (frame.band == band)
            & frame.ratio_expected.notna()
            & frame.ratio_actual.notna()
        ]
        for nation, group in subset.groupby("nation"):
            deviation = (group.ratio_actual - group.ratio_expected).abs()
            checks.append(
                {
                    "nation": nation,
                    "band": band,
                    "n": len(group),
                    "expected": round(float(group.ratio_expected.iloc[0]), 6),
                    "max_dev": round(float(deviation.max()), 8),
                    "rows_off": int((deviation > RATIO_TOLERANCE).sum()),
                }
            )
    return pd.DataFrame(checks)


def nation_multipliers(frame: pd.DataFrame) -> pd.DataFrame:
    """Build the nation-level ladder and the Scotland-to-England gap.

    Args:
        frame: Output of :func:`add_ratios`.

    Returns:
        A frame indexed by band with one column per nation, plus a percentage
        gap column where both Scotland and England are present.
    """
    table = frame.pivot_table(
        index="band", columns="nation", values="ratio_actual", aggfunc="median"
    )
    table = table.reindex(BANDS)
    if "Scotland" in table and "England" in table:
        table["Scot_vs_Eng_%"] = (
            (table["Scotland"] / table["England"] - 1) * 100
        ).round(1)
    return table


def uniformity(frame: pd.DataFrame) -> dict[str, float]:
    """Measure how far the multiplier varies between councils within a nation.

    A near-zero spread confirms the ladder is a national constant rather than a
    local policy choice.

    Args:
        frame: Output of :func:`add_ratios`.

    Returns:
        Mapping of nation to the largest within-nation spread across bands.
    """
    spreads: dict[str, float] = {}
    for nation, group in frame.groupby("nation"):
        worst = 0.0
        for band in BANDS:
            values = group[group.band == band]["ratio_actual"].dropna()
            if len(values) > 1:
                worst = max(worst, float(values.max() - values.min()))
        spreads[nation] = worst
    return spreads


def main() -> None:
    """Align the current-year charges, validate them, and write the outputs.

    Raises:
        SystemExit: If any charge disagrees with its statutory multiplier.
    """
    print("Aligning and validating")

    current = pd.read_csv(DATA_PROC / "uk_bands_2026-27.csv")
    aligned = add_ratios(current)
    aligned.to_csv(DATA_PROC / "uk_bands_aligned_2026-27.csv", index=False)
    print(f"  uk_bands_aligned_2026-27.csv  {len(aligned):>6,} rows")

    checks = validate(aligned)
    checks.to_csv(DATA_PROC / "ratio_validation.csv", index=False)
    total_off = int(checks.rows_off.sum())
    total_checked = int(checks.n.sum())
    print(
        f"  ratio_validation.csv          "
        f"{total_off} violations of {total_checked:,} checks"
    )

    multipliers = nation_multipliers(aligned)
    multipliers.round(6).to_csv(DATA_PROC / "nation_multipliers.csv")
    print(f"  nation_multipliers.csv        {len(multipliers)} bands")

    print("\n  ladder uniformity within each nation:")
    for nation, spread in uniformity(aligned).items():
        verdict = "uniform" if spread < UNIFORMITY_TOLERANCE else "VARIES"
        print(f"    {nation:10s} max spread {spread:.8f}  -> {verdict}")

    if total_off:
        print("\n  FAILURES:")
        print(checks[checks.rows_off > 0].to_string(index=False))
        raise SystemExit(1)

    print("\n  all ratio checks passed.")


if __name__ == "__main__":
    main()
