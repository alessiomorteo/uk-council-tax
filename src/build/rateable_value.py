"""Add England and Wales rateable value from the VOA stock of properties release.

The NNDR1 supplementary workbook does not publish rateable value, which left a
gap in the business rates table. The VOA fills it: Table SOP3.2 gives total
rateable value by administrative area for every year from 2011 to 2025, with ONS
codes, and Table SOP3.1 gives the matching property counts.

Two filters matter:

- Only ``LAUA`` rows are local authorities. ``CTYMET`` rows are counties and
  metropolitan counties, a different geography level that double-counts.
- Only rows with no ``abolished year`` are current. The file keeps legacy
  districts that were merged away (Allerdale, Carlisle, Copeland and others
  abolished in 2023), and including them inflates the national total.

With both applied, England reconciles to the published 68,503,619 thousand
pounds for 2025.
"""
import sys
import warnings
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import DATA_PROC, DATA_RAW  # noqa: E402

warnings.filterwarnings("ignore")

# Header row carrying the year columns, and the first data row.
HEADER_ROW = 6
FIRST_DATA_ROW = 7

# Column positions in the SOP tables.
COL_GEOGRAPHY = 0
COL_ABOLISHED = 1
COL_ONS_CODE = 3
COL_NAME = 4
COL_FIRST_YEAR = 5


def _parse_table(sheet_name: str) -> pd.DataFrame:
    """Parse one SOP3 table into a long frame of authorities by year.

    Args:
        sheet_name: The worksheet name, either Table_SOP3.1 or Table_SOP3.2.

    Returns:
        One row per current local authority, with a column per year.
    """
    raw = pd.read_excel(
        DATA_RAW / "voa_ndr_stock_2025.xlsx", sheet_name=sheet_name, header=None
    )
    years = [
        str(value).replace("31 March ", "").strip()
        for value in raw.iloc[HEADER_ROW, COL_FIRST_YEAR:].tolist()
        if pd.notna(value) and str(value).startswith("31 March")
    ]

    body = raw.iloc[FIRST_DATA_ROW:].copy()
    # Local authorities only: CTYMET rows are counties and would double-count.
    body = body[body[COL_GEOGRAPHY] == "LAUA"]
    body = body[body[COL_ONS_CODE].astype(str).str.match(r"^[EW]\d{8}$")]
    # Current authorities only: the file retains districts abolished by merger.
    abolished = body[COL_ABOLISHED].astype(str).str.strip()
    body = body[(abolished == "[z]") | body[COL_ABOLISHED].isna()]

    frame = pd.DataFrame(
        {
            "ons_code": body[COL_ONS_CODE].astype(str).str.strip().values,
            "authority": body[COL_NAME].astype(str).str.strip().values,
        }
    )
    for index, year in enumerate(years):
        column = COL_FIRST_YEAR + index
        frame[year] = pd.to_numeric(body[column], errors="coerce").values
    return frame


def build_rateable_value() -> pd.DataFrame:
    """Build the long rateable value and property count table.

    Returns:
        One row per authority and year with rateable value and property counts,
        both in pounds and units respectively.
    """
    values = _parse_table("Table_SOP3.2")
    counts = _parse_table("Table_SOP3.1")

    year_columns = [c for c in values.columns if c.isdigit()]

    long_values = values.melt(
        id_vars=["ons_code", "authority"],
        value_vars=year_columns,
        var_name="year",
        value_name="rateable_value_thousands",
    )
    long_counts = counts.melt(
        id_vars=["ons_code", "authority"],
        value_vars=year_columns,
        var_name="year",
        value_name="rateable_properties",
    )

    frame = long_values.merge(
        long_counts, on=["ons_code", "authority", "year"], how="left"
    )
    frame["nation"] = frame["ons_code"].str[0].map({"E": "England", "W": "Wales"})
    # Published in thousands of pounds; store pounds.
    frame["rateable_value"] = frame["rateable_value_thousands"] * 1e3
    frame = frame.drop(columns=["rateable_value_thousands"])
    frame["year"] = frame["year"].astype(str)
    return frame.sort_values(["nation", "authority", "year"])


def main() -> None:
    """Build and write the rateable value table, then report the reconciliation."""
    print("Building rateable value from the VOA stock of properties")
    frame = build_rateable_value()
    frame.to_csv(DATA_PROC / "rateable_value.csv", index=False)
    print(f"  rateable_value.csv             {len(frame):>6,} rows")

    latest = frame[frame.year == "2025"]
    print("\n=== 2025, current authorities only ===")
    print(
        latest.groupby("nation")
        .agg(
            authorities=("authority", "nunique"),
            rateable_value_bn=("rateable_value", lambda s: round(s.sum() / 1e9, 2)),
            properties_m=("rateable_properties", lambda s: round(s.sum() / 1e6, 2)),
        )
        .to_string()
    )

    england = latest[latest.nation == "England"]
    print("\n=== RECONCILIATION ===")
    print(f"  England rateable value 2025: £{england.rateable_value.sum() / 1e9:.2f}bn")
    print("  published by VOA:            £68.50bn")

    print("\n=== YEARS AVAILABLE ===")
    print(f"  {sorted(frame.year.unique())[0]} to {sorted(frame.year.unique())[-1]}")
    print(f"  {frame.year.nunique()} years")

    print("\n=== HIGHEST RATEABLE VALUE, 2025 ===")
    top = latest.nlargest(6, "rateable_value")
    print(
        top[["nation", "authority", "rateable_value", "rateable_properties"]]
        .assign(rv_bn=lambda d: (d.rateable_value / 1e9).round(2))
        [["nation", "authority", "rv_bn", "rateable_properties"]]
        .to_string(index=False)
    )


if __name__ == "__main__":
    main()
