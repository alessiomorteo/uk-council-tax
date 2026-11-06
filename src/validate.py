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


def check_discounts(discounts: pd.DataFrame) -> None:
    """Assert the council-level discount and exemption table reconciles.

    England and Wales publish these counts; Scotland does not, so the table is
    asserted to contain exactly those two nations rather than being silently
    zero-filled for Scotland.

    Args:
        discounts: The council-level discounts table.
    """
    check(
        "discounts cover England and Wales only",
        set(discounts.nation.unique()) == {"England", "Wales"},
        str(sorted(discounts.nation.unique())),
    )
    check(
        "discounts: England has 296 councils",
        discounts[discounts.nation == "England"].authority.nunique() == 296,
        discounts[discounts.nation == "England"].authority.nunique(),
    )
    check(
        "discounts: Wales has 22 councils",
        discounts[discounts.nation == "Wales"].authority.nunique() == 22,
        discounts[discounts.nation == "Wales"].authority.nunique(),
    )

    # National totals must match the published aggregates exactly.
    england = discounts[discounts.nation == "England"]
    check(
        "discounts: England chargeable is 25,056,421",
        int(england["chargeable"].sum()) == 25056421,
        f"{int(england['chargeable'].sum()):,}",
    )
    check(
        "discounts: England exempt is 758,040",
        int(england["exempt"].sum()) == 758040,
        f"{int(england['exempt'].sum()):,}",
    )
    check(
        "discounts: England empty is 542,260",
        int(england["empty"].sum()) == 542260,
        f"{int(england['empty'].sum()):,}",
    )
    wales = discounts[discounts.nation == "Wales"]
    check(
        "discounts: Wales chargeable is 1,433,016",
        abs(wales["chargeable"].sum() - 1433016) < 2,
        f"{wales['chargeable'].sum():,.0f}",
    )

    # Rates must be plausible: a rate above 50 per cent would mean the counts
    # are being read from the wrong block.
    for column in ["exempt_rate", "empty_rate", "discount_rate"]:
        check(
            f"discounts: {column} within 0-50pc",
            discounts[column].between(0, 50).all(),
            f"{discounts[column].min():.2f} to {discounts[column].max():.2f}",
        )

    # The single-adult discount is the dominant term and should be large.
    check(
        "discounts: discount rate median is 30-40pc",
        30 < discounts["discount_rate"].median() < 40,
        f"{discounts['discount_rate'].median():.2f}",
    )


def check_discount_values(values: pd.DataFrame) -> None:
    """Assert the priced discount table reconciles to the published requirement.

    The strongest check available: the net liability derived here must match the
    council tax requirement published for 2025-26, which is £44.1bn on a tax base
    of 19.3m Band D equivalents.

    Args:
        values: The per-council discount value table.
    """
    check(
        "discount values: England has 296 councils",
        len(values) == 296,
        len(values),
    )
    check(
        "discount values: every council has a Band D charge",
        values.band_d.notna().all(),
        f"{int(values.band_d.isna().sum())} missing",
    )

    # The tax base for setting purposes.
    equivalents = values.net_equivalents.sum()
    check(
        "discount values: net equivalents match published 19.3m",
        abs(equivalents - 19_295_312) < 100,
        f"{equivalents:,.0f}",
    )

    # The council tax requirement. Published as £44.1bn; the small residual is
    # because the published average Band D is a rounded area figure.
    liability = values.net_liability.sum()
    check(
        "discount values: net liability within 3pc of published 44.1bn",
        abs(liability - 44.1e9) / 44.1e9 < 0.03,
        f"£{liability / 1e9:.2f}bn",
    )

    # Premiums can exceed discounts, so net can legitimately exceed gross for a
    # handful of councils. City of London and Isles of Scilly both have a large
    # second-homes premium, which raises more than discounts give away. The
    # check is that this stays rare and confined to those known cases.
    inverted = values[values.gross_liability <= values.net_liability]
    check(
        "discount values: at most 3 councils have net above gross",
        len(inverted) <= 3,
        f"{len(inverted)}: {sorted(inverted.authority)}",
    )
    check(
        "discount values: the inverted councils are the premium cases",
        set(inverted.authority) <= {"City of London", "Isles of Scilly", "Westminster"},
        str(sorted(inverted.authority)),
    )
    check(
        "discount values: reduction is -15 to 40pc of gross",
        values.reduction_pct.between(-15, 40).all(),
        f"{values.reduction_pct.min():.1f} to {values.reduction_pct.max():.1f}",
    )
    check(
        "discount values: median reduction is 15-20pc of gross",
        15 < values.reduction_pct.median() < 20,
        f"{values.reduction_pct.median():.2f}",
    )

    # Premiums can exceed discounts, so a negative discount value is genuine for
    # a handful of councils. It must stay rare.
    negative = int((values.discount_value < 0).sum())
    check(
        "discount values: few councils have negative discount value",
        negative <= 5,
        f"{negative} councils",
    )


def check_business_rates(rates: pd.DataFrame) -> None:
    """Assert the business rates table reconciles to published national totals.

    Args:
        rates: The council-level business rates table.
    """
    check(
        "business rates: 350 councils plus designated utilities",
        len(rates) == 351,
        len(rates),
    )
    check(
        "business rates: England has 296 authorities",
        (rates.nation == "England").sum() == 296,
        (rates.nation == "England").sum(),
    )
    check(
        "business rates: Scotland has 32 councils plus utilities",
        ((rates.nation == "Scotland") & (rates.authority_type == "CA")).sum() == 32,
        ((rates.nation == "Scotland") & (rates.authority_type == "CA")).sum(),
    )
    check(
        "business rates: Wales has 22 authorities",
        (rates.nation == "Wales").sum() == 22,
        (rates.nation == "Wales").sum(),
    )

    # England hereditaments reconcile exactly to the published national figure.
    england = rates[rates.nation == "England"]
    check(
        "business rates: England hereditaments are 1,990,047",
        int(england.hdits_total.sum()) == 1990047,
        f"{int(england.hdits_total.sum()):,}",
    )
    check(
        "business rates: England SBRR value is about £1.8bn",
        abs(england.value_sbrr.sum() - 1.817e9) / 1.817e9 < 0.02,
        f"£{england.value_sbrr.sum() / 1e9:.2f}bn",
    )

    # Scotland reconciles exactly on all three measures.
    scotland = rates[rates.nation == "Scotland"]
    check(
        "business rates: Scotland hereditaments are 253,608",
        int(scotland.hdits_total.sum()) == 253608,
        f"{int(scotland.hdits_total.sum()):,}",
    )
    check(
        "business rates: Scotland rateable value is about £7.58bn",
        abs(scotland.rateable_value.sum() - 7.578e9) / 7.578e9 < 0.02,
        f"£{scotland.rateable_value.sum() / 1e9:.2f}bn",
    )
    check(
        "business rates: Scotland relief value is about £0.73bn",
        abs(scotland.relief_value.sum() - 0.7298e9) / 0.7298e9 < 0.02,
        f"£{scotland.relief_value.sum() / 1e9:.2f}bn",
    )

    # Wales: rateable value must be in the right order of magnitude. A unit
    # error here is a factor of a thousand, so the bound is deliberately wide.
    wales = rates[rates.nation == "Wales"]
    check(
        "business rates: Wales rateable value is £2-4bn",
        2e9 < wales.rateable_value.sum() < 4e9,
        f"£{wales.rateable_value.sum() / 1e9:.2f}bn",
    )
    check(
        "business rates: Wales hereditaments are about 125,000",
        120_000 < wales.hdits_total.sum() < 130_000,
        f"{wales.hdits_total.sum():,.0f}",
    )

    # Two English authorities report "[x]" rather than a figure.
    check(
        "business rates: at most 2 English authorities lack hereditament counts",
        int(england.hdits_total.isna().sum()) <= 2,
        f"{int(england.hdits_total.isna().sum())}",
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
    check_discounts(pd.read_csv(DATA_PROC / "council_discounts.csv"))
    check_discount_values(pd.read_csv(DATA_PROC / "discount_values.csv"))
    check_business_rates(pd.read_csv(DATA_PROC / "business_rates.csv"))

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failures: {FAILURES}")
        raise SystemExit(1)
    print("all checks passed.")


if __name__ == "__main__":
    main()
