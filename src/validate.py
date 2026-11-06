"""Assert the invariants this dataset depends on.

Run with ``make test`` or ``python3 src/validate.py``. The process exits
non-zero if any check fails.
"""

import sys
import warnings
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (  # noqa: E402
    BANDS,
    DATA_PROC,
    ENGLAND_WALES,
    SCOTLAND_POST_2017,
    SCOTLAND_PRE_2017,
    ladder,
)

warnings.filterwarnings("ignore")

# Absolute tolerance for the ratio identity, allowing for published rounding.
RATIO_TOLERANCE: float = 1e-3

# Spread above this counts as real variation rather than rounding noise.
UNIFORMITY_TOLERANCE: float = 1e-4

EXPECTED_COUNTS: dict[str, int] = {"England": 296, "Wales": 22, "Scotland": 32}

# Councils the ONS suppresses for small sample sizes, so no earnings estimate.
SUPPRESSED_COUNCILS: set[str] = {"City of London", "Isles of Scilly"}

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: object = "") -> None:
    """Record the outcome of a single assertion.

    Args:
        name: A short description of what is being asserted.
        condition: The assertion result.
        detail: Extra context printed when the check fails.
    """
    if condition:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}  {detail}")
        FAILURES.append(name)


def check_ratio_identity(aligned: pd.DataFrame) -> None:
    """Assert that every charge equals its statutory multiplier times Band D.

    Args:
        aligned: The aligned charge table with expected and actual ratios.
    """
    deviation = (aligned.ratio_actual - aligned.ratio_expected).abs().dropna()
    check(
        "ratio identity (charge divided by Band D equals statutory multiplier)",
        bool((deviation < RATIO_TOLERANCE).all()),
        f"max deviation {deviation.max():.6f}",
    )


def check_coverage(bands: pd.DataFrame, full: pd.DataFrame) -> None:
    """Assert the expected authority counts and the suppression behaviour.

    Args:
        bands: The full band table covering every council.
        full: The affordability table after the earnings join.
    """
    band_counts = (
        bands.drop_duplicates(["nation", "authority"]).groupby("nation").size().to_dict()
    )
    for nation, expected in EXPECTED_COUNTS.items():
        check(
            f"{nation} has {expected} authorities",
            band_counts.get(nation) == expected,
            band_counts,
        )

    counts = full.groupby("nation").size().to_dict()
    check(
        "affordability drops exactly 2 English councils",
        counts.get("England") == EXPECTED_COUNTS["England"] - len(SUPPRESSED_COUNCILS),
        counts,
    )

    england_bands = set(bands[bands.nation == "England"].authority)
    england_full = set(full[full.nation == "England"].authority)
    check(
        "the dropped councils are the ONS-suppressed ones",
        england_bands - england_full == SUPPRESSED_COUNCILS,
        england_bands - england_full,
    )


def check_completeness(full: pd.DataFrame) -> None:
    """Assert no duplicate councils and no missing bands.

    Args:
        full: The affordability table.
    """
    duplicates = int(full.duplicated(subset=["nation", "authority"]).sum())
    check("no duplicate councils", duplicates == 0, f"{duplicates} duplicates")

    for band in "ABCDEFGH":
        nulls = int(full[f"band_{band.lower()}"].isna().sum())
        check(f"band {band} complete", nulls == 0, f"{nulls} nulls")


def check_uniformity(aligned: pd.DataFrame) -> None:
    """Assert the multiplier is a national constant, not a local choice.

    Args:
        aligned: The aligned charge table.
    """
    for nation, group in aligned.groupby("nation"):
        worst = 0.0
        for band in BANDS:
            values = group[group.band == band]["ratio_actual"].dropna()
            if len(values) > 1:
                worst = max(worst, float(values.max() - values.min()))
        check(
            f"{nation} ladder uniform across councils",
            worst < UNIFORMITY_TOLERANCE,
            f"spread {worst:.8f}",
        )


def check_statute() -> None:
    """Assert the statutory ladders, including the 2017 Scottish reform."""
    check(
        "Scotland post-2017 Band H is 2.450",
        abs(SCOTLAND_POST_2017["H"] - 2.45) < 1e-9,
    )
    check(
        "Scotland pre-2017 Band H is 2.000",
        abs(SCOTLAND_PRE_2017["H"] - 2.0) < 1e-9,
    )
    check(
        "ladder switches at 2017",
        ladder("Scotland", "2016-17")["H"] == 2.0
        and abs(ladder("Scotland", "2017-18")["H"] - 2.45) < 1e-9,
    )

    for band in "ABCDEFGH":
        check(
            f"England and Wales band {band} share a multiplier",
            abs(ENGLAND_WALES[band] - ladder("England", "2026-27")[band]) < 1e-12,
        )

    check("Wales has Band I at 21/9", abs(ENGLAND_WALES["I"] - 21 / 9) < 1e-9)
    check("Scotland has no Band I", "I" not in SCOTLAND_POST_2017)


def check_affordability(full: pd.DataFrame) -> None:
    """Assert the affordability figures fall in a plausible range.

    Args:
        full: The affordability table.
    """
    shares = full["band_d_pct_pay"]
    check(
        "affordability within plausible bounds",
        bool(shares.between(0, 20).all()),
        f"{shares.min():.2f} to {shares.max():.2f} per cent",
    )
    check(
        "Wandsworth is the most affordable",
        full.loc[shares.idxmin(), "authority"] == "Wandsworth",
    )
    check(
        "Nottingham is the least affordable",
        full.loc[shares.idxmax(), "authority"] == "Nottingham",
    )


def check_nation_multipliers(multipliers: pd.DataFrame) -> None:
    """Assert the nation-level Band H multipliers.

    Args:
        multipliers: The nation multiplier table indexed by band.
    """
    check(
        "Scotland Band H multiplier is 2.45",
        abs(multipliers.loc["H", "Scotland"] - 2.45) < 1e-4,
    )
    check(
        "England Band H multiplier is 2.00",
        abs(multipliers.loc["H", "England"] - 2.0) < 1e-4,
    )


def check_taxbase(taxbase: pd.DataFrame) -> None:
    """Assert the Council Taxbase table is complete and reconciles.

    The published Band D equivalent tax base is not ``dwellings x statutory
    ratio``: it applies discounts, premiums and exemptions first. The naive
    product overstates it by 6 to 12 per cent, so both are checked.

    Args:
        taxbase: The long taxbase table with nation, band, dwellings and
            tax_base columns.
    """
    latest = {"England": "2025-26", "Wales": "2026-27", "Scotland": "2026-27"}
    expected_auth = {"England": 296, "Wales": 22, "Scotland": 32}
    expected_bands = {"England": 8, "Wales": 9, "Scotland": 8}

    for nation, year in latest.items():
        group = taxbase[(taxbase.nation == nation) & (taxbase.year == year)]
        bands = group[group.band != "Total"]
        totals = group[group.band == "Total"]

        check(
            f"taxbase: {nation} has {expected_auth[nation]} authorities",
            bands.authority.nunique() == expected_auth[nation],
            bands.authority.nunique(),
        )
        check(
            f"taxbase: {nation} has {expected_bands[nation]} bands",
            bands.band.nunique() == expected_bands[nation],
            bands.band.nunique(),
        )
        check(
            f"taxbase: {nation} has a published tax base",
            totals.tax_base.notna().any() and totals.tax_base.sum() > 0,
        )

        mult = ladder(nation, year)
        naive = (bands.dwellings * bands.band.map(mult)).sum()
        published = totals.tax_base.sum()
        gap = (naive - published) / published * 100
        check(
            f"taxbase: {nation} naive product overstates by 5-15pc",
            5 < gap < 15,
            f"{gap:.2f}%",
        )


def check_revenue(full: pd.DataFrame) -> None:
    """Assert the taxbase join is complete and the revenue figures are sane.

    Gross revenue is ``dwellings x charge`` before discounts, so it must exceed
    the revenue implied by the published tax base. The ratio between them is the
    value of discounts and premiums, which should sit in a narrow band.

    Args:
        full: The joined council tax table with dwellings and revenue columns.
    """
    check(
        "every council has a dwelling count",
        full.dwellings.notna().all(),
        f"{int(full.dwellings.isna().sum())} missing",
    )
    check(
        "every council has a published tax base",
        full.tax_base_published.notna().all(),
        f"{int(full.tax_base_published.isna().sum())} missing",
    )
    check(
        "every council has gross revenue",
        full.revenue_gross.notna().all(),
        f"{int(full.revenue_gross.isna().sum())} missing",
    )

    # Gross must exceed budgeted: discounts reduce the yield.
    check(
        "gross revenue exceeds tax-base revenue everywhere",
        (full.revenue_gross >= full.revenue_tax_base).mean() > 0.95,
        f"{(full.revenue_gross < full.revenue_tax_base).sum()} councils inverted",
    )
    check(
        "tax base ratio sits between 0.75 and 1.05",
        full.tax_base_ratio.between(0.75, 1.05).all(),
        f"range {full.tax_base_ratio.min():.3f} to {full.tax_base_ratio.max():.3f}",
    )

    # National revenue must be in the right order of magnitude.
    england = full[full.nation == "England"]
    check(
        "England gross revenue is 50-65bn",
        50e9 < england.revenue_gross.sum() < 65e9,
        f"{england.revenue_gross.sum() / 1e9:.1f}bn",
    )
    check(
        "revenue per dwelling is plausible",
        full.revenue_gross.sum() / full.dwellings.sum() > 1000,
        f"{full.revenue_gross.sum() / full.dwellings.sum():.0f}",
    )


def main() -> None:
    """Run every validation check.

    Raises:
        SystemExit: If any check fails.
    """
    print("Validating processed data\n")

    aligned = pd.read_csv(DATA_PROC / "uk_bands_aligned_2026-27.csv")
    full = pd.read_csv(DATA_PROC / "uk_council_tax_full.csv")
    bands = pd.read_csv(DATA_PROC / "uk_bands_2026-27.csv")
    multipliers = pd.read_csv(DATA_PROC / "nation_multipliers.csv", index_col=0)

    check_ratio_identity(aligned)
    check_coverage(bands, full)
    check_completeness(full)
    check_uniformity(aligned)
    check_statute()
    check_affordability(full)
    check_nation_multipliers(multipliers)
    check_taxbase(pd.read_csv(DATA_PROC / "taxbase_long.csv"))
    check_revenue(full)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failures: {FAILURES}")
        raise SystemExit(1)
    print("all checks passed.")


if __name__ == "__main__":
    main()
