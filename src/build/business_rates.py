"""Build a council-level business rates table for England, Wales and Scotland.

Business rates are collected by the same billing authorities as council tax, but
the published sources differ sharply in shape:

- England: the NNDR1 supplementary workbook, three sheets of per-authority data
  with ONS codes. Hereditament counts by relief type and multiplier, plus
  estimated relief values in pounds.
- Wales: StatsWales estimates, per authority, including aggregate rateable value.
- Scotland: the reliefs publication, per council area, including rateable value
  and total relief value.

The output is one row per authority with the comparable measures. Where a
measure is not published for a nation it is absent rather than zero, because a
zero would read as "no relief awarded" rather than "not collected".
"""
import sys
import warnings
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import DATA_PROC, DATA_RAW, norm_name  # noqa: E402

warnings.filterwarnings("ignore")

# England: the NNDR1 supplementary sheets carry a header on row 5 and data from
# row 6, with aggregate rows first. Only rows with a real ONS code are kept.
ENGLAND_HEADER_ROW = 5
ENGLAND_FIRST_DATA_ROW = 6

# Relief counts, by column index in the Hdits Reliefs sheet.
ENGLAND_RELIEF_COLUMNS: dict[int, str] = {
    6: "sbrr_discount",
    10: "mr_charity",
    11: "mr_casc",
    12: "mr_rural_shops",
    14: "mr_partly_occupied",
    15: "mr_empty",
    22: "dr_charity",
    23: "dr_non_profit",
    29: "s31_retail_hospitality_leisure",
    33: "total_sbrr",
    34: "total_other_mandatory",
    35: "total_discretionary",
}

# Hereditament counts by multiplier.
ENGLAND_MULTIPLIER_COLUMNS: dict[int, str] = {
    6: "hdits_small_multiplier",
    7: "hdits_standard_multiplier",
    8: "hdits_small_multiplier_forecast",
    9: "hdits_standard_multiplier_forecast",
    12: "hdits_higher_value_multiplier",
}

# Relief values in pounds. The published figures are negative because they are
# deductions, so they are flipped to positive on load.
ENGLAND_VALUE_COLUMNS: dict[int, str] = {
    6: "value_empty_relief",
    13: "value_sbrr",
    16: "value_other_discretionary",
}


def parse_england() -> pd.DataFrame:
    """Parse England's per-authority business rates data.

    Returns:
        One row per billing authority with relief counts, hereditament counts
        and relief values.
    """
    source = DATA_RAW / "nndr1_supplementary_2026-27.xlsx"
    workbook = pd.ExcelFile(source)

    def read_sheet(name: str, columns: dict[int, str]) -> pd.DataFrame:
        """Extract the identifier columns and a chosen set of measures."""
        sheet = workbook.parse(name, header=None)
        body = sheet.iloc[ENGLAND_FIRST_DATA_ROW:].copy()
        body = body[body[1].astype(str).str.match(r"^E\d{8}$")]
        body = body[body[1] != "E92000001"]
        frame = pd.DataFrame(
            {
                "authority": body[2].astype(str).str.strip(),
                "ons_code": body[1].astype(str).str.strip(),
                "authority_type": body[3].astype(str).str.strip(),
            }
        )
        for index, name_out in columns.items():
            # The workbook uses "[x]" for "not applicable" and "[z]" for "not
            # available"; both must become missing rather than a string that
            # silently breaks the numeric column.
            frame[name_out] = pd.to_numeric(body[index], errors="coerce")
        return frame

    frame = read_sheet("NNDR1S Hdits Reliefs Data", ENGLAND_RELIEF_COLUMNS)
    multipliers = read_sheet("NNDR1S Hdits Multipliers Data", ENGLAND_MULTIPLIER_COLUMNS)
    values = read_sheet("NNDR1S Empty & SBRR Data", ENGLAND_VALUE_COLUMNS)

    # The three sheets share the same authority rows, so merge on the ONS code.
    # Drop the identifier columns from the right-hand frames to avoid suffixes.
    multipliers = multipliers.drop(columns=["authority", "authority_type"])
    values = values.drop(columns=["authority", "authority_type"])

    frame = frame.merge(multipliers, on="ons_code", how="left", validate="one_to_one")
    frame = frame.merge(values, on="ons_code", how="left", validate="one_to_one")

    # Published as negative deductions; express as positive relief given.
    for column in ["value_empty_relief", "value_sbrr", "value_other_discretionary"]:
        frame[column] = frame[column].abs()

    # Total hereditaments on the rating list: the small and standard multiplier
    # counts together.
    frame["hdits_total"] = (
        frame["hdits_small_multiplier"] + frame["hdits_standard_multiplier"]
    )

    frame["nation"] = "England"
    frame["year"] = "2026-27"
    frame["source"] = "MHCLG NNDR1 supplementary 2026-27"
    return frame


def parse_wales() -> pd.DataFrame:
    """Parse Wales's per-authority business rates estimates.

    Returns:
        One row per unitary authority with rateable value, hereditament counts
        and relief values.
    """
    source = DATA_RAW / "nndr_wales_estimates.csv"
    frame = pd.read_csv(source)
    frame = frame[frame.Year == "2026-27"].copy()
    frame = frame[~frame.Authority.astype(str).str.contains("Total", na=False)]
    frame["Data values"] = pd.to_numeric(frame["Data values"], errors="coerce")

    wanted = {
        "Number of hereditaments on rating list at 31 December": "hdits_total",
        "Aggregate rateable value at 31 December": "rateable_value_m",
        "Gross rates payable": "gross_rates_payable_m",
        "Mandatory reliefs - total": "relief_mandatory_m",
        "Mandatory reliefs - small business rates relief total": "relief_sbrr_m",
        "Mandatory reliefs - empty premises": "relief_empty_m",
        "Mandatory reliefs - charitable occupations": "relief_charity_m",
    }

    records: list[dict[str, object]] = []
    for authority, group in frame.groupby("Authority"):
        row: dict[str, object] = {
            "nation": "Wales",
            "authority": str(authority).strip(),
            "ons_code": "",
            "authority_type": "UA",
            "year": "2026-27",
            "source": "StatsWales NDR estimates 2026-27",
        }
        for label, name in wanted.items():
            match = group[group["Row description"] == label]
            if not len(match):
                row[name] = None
                continue
            value = match["Data values"].iloc[0]
            # Wales reports hereditaments in thousands and money in thousands of
            # pounds. Reliefs are published as negative deductions.
            if name == "hdits_total":
                value = value * 1000
            elif name == "rateable_value_m":
                # Rateable value is published in thousands of pounds, so this
                # is thousands of pounds, not millions.
                value = abs(value) * 1e3
            else:
                value = abs(value)
            row[name] = value
        records.append(row)
    return pd.DataFrame(records)


def parse_scotland() -> pd.DataFrame:
    """Parse Scotland's per-council-area business rates data.

    Two tables are combined: Table 12 gives properties and rateable value on the
    valuation roll, and Table 4 gives relief counts and values by council area.

    Returns:
        One row per council area with rateable value and relief totals.
    """
    source = DATA_RAW / "nndr_scotland_reliefs_2025.xlsx"
    workbook = pd.ExcelFile(source)

    # Table 12: properties and rateable value by council area.
    table12 = workbook.parse("12", header=None)
    roll = table12.iloc[6:, :3].copy()
    roll.columns = ["authority", "hdits_total", "rateable_value_m"]
    roll = roll[roll["authority"].notna()]
    roll["authority"] = roll["authority"].astype(str).str.strip()
    roll = roll[roll["authority"] != "Scotland"]
    # "Designated utilities" is not a council area, but it is real: 54
    # properties and £799m of rateable value, valued centrally rather than by a
    # council. It is kept as its own row so the national total reconciles, and
    # flagged by authority_type so it can be excluded from per-council work.
    roll["is_designated_utilities"] = roll["authority"] == "Designated utilities"
    roll["hdits_total"] = pd.to_numeric(roll["hdits_total"], errors="coerce")
    roll["rateable_value_m"] = pd.to_numeric(
        roll["rateable_value_m"], errors="coerce"
    )

    # Table 4: relief counts and values by council area.
    table4 = workbook.parse("4", header=None)
    relief = table4.iloc[7:, :5].copy()
    relief.columns = [
        "authority",
        "snapshot",
        "relief_properties",
        "relief_proportion",
        "relief_value_m",
    ]
    relief = relief[relief["authority"].notna()]
    relief["authority"] = relief["authority"].astype(str).str.strip()
    relief = relief[relief["authority"] != "Scotland"]
    # Table 4 carries several years per authority. Keep only the latest snapshot,
    # which is the 1 June 2025 row; the older rows use "[low]" markers instead of
    # figures and would otherwise be picked up by drop_duplicates.
    relief = relief[relief["snapshot"].astype(str).str.startswith("01 June 2025")]
    relief["relief_properties"] = pd.to_numeric(
        relief["relief_properties"], errors="coerce"
    )
    relief["relief_value_m"] = pd.to_numeric(relief["relief_value_m"], errors="coerce")
    relief = relief.drop_duplicates(subset=["authority"])

    frame = roll.merge(relief, on="authority", how="outer")
    frame["nation"] = "Scotland"
    frame["ons_code"] = ""
    frame["authority_type"] = frame["is_designated_utilities"].map(
        {True: "UTIL", False: "CA"}
    )
    frame["year"] = "2025-26"
    frame["source"] = "Scottish Government NDR reliefs 2025"
    return frame


def main() -> None:
    """Build and write the council-level business rates table."""
    print("Building council-level business rates")

    england = parse_england()
    wales = parse_wales()
    scotland = parse_scotland()
    combined = pd.concat([england, wales, scotland], ignore_index=True)

    # Normalise units. Each source reports money differently: England in pounds,
    # Wales in thousands of pounds, Scotland in millions. Everything is stored
    # in pounds so the columns are comparable.
    #
    # Wales rateable value is already converted to pounds in parse_wales because
    # it is published in thousands, unlike Scotland's millions.
    combined["rateable_value"] = combined["rateable_value_m"] * 1e6
    wales_mask = combined["nation"] == "Wales"
    combined.loc[wales_mask, "rateable_value"] = combined.loc[
        wales_mask, "rateable_value_m"
    ]
    combined["gross_rates_payable"] = combined["gross_rates_payable_m"] * 1e3
    combined["relief_mandatory"] = combined["relief_mandatory_m"] * 1e3
    combined["relief_sbrr"] = combined["relief_sbrr_m"] * 1e3
    combined["relief_empty"] = combined["relief_empty_m"] * 1e3
    combined["relief_charity"] = combined["relief_charity_m"] * 1e3
    combined["relief_value"] = combined["relief_value_m"] * 1e6

    columns = [
        "nation",
        "authority",
        "ons_code",
        "authority_type",
        "year",
        "hdits_total",
        "rateable_value",
        "gross_rates_payable",
        "relief_properties",
        "relief_value",
        "relief_mandatory",
        "relief_sbrr",
        "relief_empty",
        "relief_charity",
        "value_empty_relief",
        "value_sbrr",
        "value_other_discretionary",
        "total_sbrr",
        "total_other_mandatory",
        "total_discretionary",
        "source",
    ]
    for column in columns:
        if column not in combined.columns:
            combined[column] = None

    combined = combined[columns].sort_values(["nation", "authority"])
    combined.to_csv(DATA_PROC / "business_rates.csv", index=False)
    print(f"  business_rates.csv             {len(combined):>6,} rows")

    print("\n=== COVERAGE ===")
    print(
        combined.groupby("nation")
        .agg(
            councils=("authority", "size"),
            with_hereditaments=("hdits_total", lambda s: s.notna().sum()),
            with_rateable_value=("rateable_value", lambda s: s.notna().sum()),
            with_relief_value=("relief_value", lambda s: s.notna().sum()),
        )
        .to_string()
    )

    print("\n=== ENGLAND: relief counts by type ===")
    eng = combined[combined.nation == "England"]
    for column, label in [
        ("total_sbrr", "Small business rates relief"),
        ("total_other_mandatory", "Other mandatory reliefs"),
        ("total_discretionary", "Discretionary reliefs"),
    ]:
        total = eng[column].sum()
        print(f"  {label:30s} {total:>12,.0f}")

    print("\n=== ENGLAND: relief value ===")
    for column, label in [
        ("value_sbrr", "Small business rates relief"),
        ("value_empty_relief", "Empty property relief"),
        ("value_other_discretionary", "Other discretionary"),
    ]:
        total = eng[column].sum()
        print(f"  {label:30s} £{total / 1e6:>10,.0f}m")

    print("\n=== HIGHEST RELIEF VALUE PER AUTHORITY ===")
    top = combined.nlargest(6, "relief_value")
    print(
        top[["nation", "authority", "relief_value", "hdits_total"]]
        .assign(relief_m=lambda d: (d.relief_value / 1e6).round(1))
        [["nation", "authority", "relief_m", "hdits_total"]]
        .to_string(index=False)
    )


if __name__ == "__main__":
    main()
