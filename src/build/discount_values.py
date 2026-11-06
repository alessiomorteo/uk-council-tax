"""Price England's council tax discounts in pounds, per council.

The taxbase workbook publishes dwelling-equivalents, not money. Money is
recoverable because a Band D equivalent is by definition one Band D charge:
multiply the shortfall between chargeable dwellings and dwelling-equivalents by
the council's own Band D charge.

The chain is:

    chargeable dwellings      Table 1.07   25,056,421
    less discounts/premiums   Table 1.26   23,166,973  ->  1,889,448 lost
    less council tax support  Table 1.31    2,435,814  -> 19,793,966 net

Each step is priced at the council's Band D charge.
"""
import sys
import warnings
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import DATA_PROC, DATA_RAW  # noqa: E402

warnings.filterwarnings("ignore")

# Block titles, mapped to output names.
BLOCKS: dict[str, str] = {
    "Table 1.07": "chargeable_dwellings",
    "Table 1.26": "dwelling_equivalents",
    "Table 1.27": "band_d_equivalents",
    "Table 1.29": "tax_base",
    "Table 1.31": "cts_reduction",
    "Table 1.32": "equivalents_after_cts",
    "Table 1.33": "band_d_equivalents_after_cts",
}


def _total_columns(raw: pd.DataFrame) -> dict[str, int]:
    """Locate the Total column of every block in the sheet.

    Args:
        raw: The sheet read with ``header=None``.

    Returns:
        A mapping from block title to the index of its Total column.
    """
    starts = [c for c in range(len(raw.columns)) if pd.notna(raw.iloc[4, c])]
    ends = starts[1:] + [len(raw.columns)]
    mapping: dict[str, int] = {}
    for start, end in zip(starts, ends):
        title = str(raw.iloc[4, start]).strip()
        totals = [
            c for c in range(start, end) if str(raw.iloc[5, c]).strip() == "Total"
        ]
        if totals:
            mapping[title] = totals[0]
    return mapping


def build_discount_values() -> pd.DataFrame:
    """Build the per-council discount value table.

    Returns:
        One row per billing authority with dwelling-equivalent losses and their
        value in pounds at that council's Band D charge.
    """
    raw = pd.read_excel(
        DATA_RAW / "taxbase_england_2025.xlsx",
        sheet_name="Council Taxbase Data",
        header=None,
    )
    totals = _total_columns(raw)

    body = raw.iloc[6:].copy()
    body.columns = range(len(raw.columns))
    body = body[body[1].astype(str).str.match(r"^E\d{8}$")]
    body = body[body[1] != "E92000001"]

    frame = pd.DataFrame(
        {
            "authority": body[3].astype(str).str.strip(),
            "ons_code": body[1].astype(str).str.strip(),
        }
    )
    for prefix, name in BLOCKS.items():
        matches = [
            col for title, col in totals.items() if title.startswith(f"{prefix}.")
        ]
        frame[name] = (
            pd.to_numeric(body[matches[0]], errors="coerce") if matches else None
        )

    # Attach the council's own Band D charge. The taxbase is 2025-26, so the
    # charge must be 2025-26 too: using the 2026-27 charge would price a
    # 2025-26 dwelling count at next year's rate and overstate the total.
    charges = pd.read_csv(DATA_PROC / "england_band_d_1993-2027.csv")
    charges = charges[
        (charges.measure == "band_d_area_total") & (charges.year == "2025-26")
    ][["ons_code", "charge_gbp"]].rename(columns={"charge_gbp": "band_d"})
    charges = charges.drop_duplicates(subset=["ons_code"])
    frame = frame.merge(charges, on="ons_code", how="left")

    # Dwelling-equivalents lost at each stage, all in Band D equivalent units.
    #
    # The published chain is:
    #   Table 1.26  dwelling equivalents after discounts and premiums
    #   Table 1.27  the same expressed in Band D equivalents
    #   Table 1.28  contributions in lieu, added on top
    #   Table 1.29  tax base = 1.27 + 1.28
    #   Table 1.31  council tax support reduction, deducted from 1.29
    #
    # Gross is therefore Table 1.27 plus the discount shortfall: the equivalents
    # the stock would yield if nothing were discounted. Using the chargeable
    # dwelling count instead mixes units, because a Band H dwelling is 2.0 to
    # 2.45 equivalents.
    frame["discount_equivalents"] = (
        frame["chargeable_dwellings"] - frame["dwelling_equivalents"]
    )
    frame["cts_equivalents"] = frame["cts_reduction"]

    frame["gross_equivalents"] = (
        frame["band_d_equivalents"] + frame["discount_equivalents"]
    )
    frame["net_equivalents"] = frame["tax_base"] - frame["cts_reduction"]

    frame["discount_value"] = (frame["discount_equivalents"] * frame["band_d"]).round(0)
    frame["cts_value"] = (frame["cts_equivalents"] * frame["band_d"]).round(0)
    frame["total_reduction"] = (
        frame["discount_value"] + frame["cts_value"]
    ).round(0)
    frame["gross_liability"] = (frame["gross_equivalents"] * frame["band_d"]).round(0)
    frame["net_liability"] = (frame["net_equivalents"] * frame["band_d"]).round(0)
    frame["reduction_pct"] = (
        frame["total_reduction"] / frame["gross_liability"] * 100
    ).round(2)

    columns = [
        "authority",
        "ons_code",
        "band_d",
        "chargeable_dwellings",
        "dwelling_equivalents",
        "tax_base",
        "cts_reduction",
        "discount_equivalents",
        "cts_equivalents",
        "discount_value",
        "cts_value",
        "total_reduction",
        "gross_liability",
        "net_equivalents",
        "net_liability",
        "reduction_pct",
    ]
    return frame[columns].sort_values("authority")


def main() -> None:
    """Build and describe the discount value table."""
    print("Pricing council tax discounts in pounds")
    frame = build_discount_values()
    frame.to_csv(DATA_PROC / "discount_values.csv", index=False)
    print(f"  discount_values.csv            {len(frame):>6,} rows")

    total_gross = frame["gross_liability"].sum()
    total_discount = frame["discount_value"].sum()
    total_cts = frame["cts_value"].sum()
    total_net = frame["net_liability"].sum()

    print("\n=== ENGLAND, 2025-26 ===")
    print(f"  gross liability at Band D rates   £{total_gross / 1e9:>6.1f}bn")
    print(f"  less discounts and premiums       £{total_discount / 1e9:>6.1f}bn")
    print(f"  less council tax support          £{total_cts / 1e9:>6.1f}bn")
    print(f"  net liability                     £{total_net / 1e9:>6.1f}bn")
    print(
        f"  total reduction                    "
        f"{(total_discount + total_cts) / total_gross * 100:>6.2f}% of gross"
    )

    print("\n=== BIGGEST DISCOUNT BILL (pounds) ===")
    top = frame.nlargest(6, "discount_value")
    print(
        top[["authority", "discount_value", "cts_value", "reduction_pct"]]
        .assign(
            discount_m=lambda d: (d.discount_value / 1e6).round(0),
            cts_m=lambda d: (d.cts_value / 1e6).round(0),
        )[["authority", "discount_m", "cts_m", "reduction_pct"]]
        .to_string(index=False)
    )

    print("\n=== HIGHEST REDUCTION AS A SHARE OF GROSS ===")
    top_pct = frame.nlargest(6, "reduction_pct")
    print(
        top_pct[["authority", "reduction_pct", "discount_value", "cts_value"]]
        .assign(
            discount_m=lambda d: (d.discount_value / 1e6).round(1),
            cts_m=lambda d: (d.cts_value / 1e6).round(1),
        )[["authority", "reduction_pct", "discount_m", "cts_m"]]
        .to_string(index=False)
    )

    print("\n=== LOWEST REDUCTION AS A SHARE OF GROSS ===")
    low_pct = frame.nsmallest(6, "reduction_pct")
    print(
        low_pct[["authority", "reduction_pct", "discount_value", "cts_value"]]
        .assign(
            discount_m=lambda d: (d.discount_value / 1e6).round(1),
            cts_m=lambda d: (d.cts_value / 1e6).round(1),
        )[["authority", "reduction_pct", "discount_m", "cts_m"]]
        .to_string(index=False)
    )


if __name__ == "__main__":
    main()
