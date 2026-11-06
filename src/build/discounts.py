"""Build a council-level discounts and exemptions table for England and Wales.

England publishes 35 tables side by side in one sheet, each banded A to H with a
Total. Wales publishes 64 row types, all banded A to I. Scotland publishes no
routine council-level discount or exemption series, so it is absent here rather
than zero-filled.

The output is one row per council with the raw counts and the derived rates that
make councils comparable despite very different dwelling stocks.
"""
import sys
import warnings
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import DATA_PROC, DATA_RAW, ONS_RECODE, norm_name  # noqa: E402

warnings.filterwarnings("ignore")

# England block titles, mapped to the short name used in the output. Each block
# is Band A to H plus a Total, but a few carry an extra disabled-relief column,
# so the Total is located by scanning rather than by a fixed offset.
ENGLAND_BLOCKS: dict[str, str] = {
    "Table 1.01": "dwellings_on_list",
    "Table 1.02": "exempt",
    "Table 1.04": "chargeable",
    "Table 1.08": "single_adult_discount",
    "Table 1.09": "discount_25_other",
    "Table 1.10": "discount_50",
    "Table 1.11": "second_homes",
    "Table 1.18": "empty",
    "Table 1.23": "liable_full",
    "Table 1.26": "dwelling_equivalents",
    "Table 1.29": "tax_base",
    "Table 1.31": "cts_reduction",
}

# Wales row types, mapped to the same output names.
WALES_ROWS: dict[str, str] = {
    "A1": "chargeable",
    "D1": "exempt",
    "D2": "exempt_class_o",
    "B1": "no_discount",
    "B2a": "discount_25",
    "B2b": "discount_50",
    "H7": "empty",
    "H8": "second_homes",
}


def _total_columns(raw: pd.DataFrame) -> dict[str, int]:
    """Locate the Total column of every block in the England sheet.

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


def parse_england() -> pd.DataFrame:
    """Parse England's council-level discount and exemption counts.

    Returns:
        One row per billing authority with a column per measure.
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
            "nation": "England",
            "authority": body[3].astype(str).str.strip(),
            "ons_code": body[1].astype(str).str.strip(),
        }
    )
    for prefix, name in ENGLAND_BLOCKS.items():
        # Match on the full "Table 1.NN" prefix, not a substring: "Table 1.1"
        # would otherwise collide across 1.10 to 1.19.
        matches = [
            col for title, col in totals.items() if title.startswith(f"{prefix}.")
        ]
        frame[name] = (
            pd.to_numeric(body[matches[0]], errors="coerce") if matches else None
        )
    frame["year"] = "2025-26"
    return frame


def parse_wales() -> pd.DataFrame:
    """Parse Wales's council-level discount and exemption counts.

    Returns:
        One row per unitary authority with a column per measure, summed across
        bands A to I.
    """
    wales = pd.read_csv(DATA_RAW / "taxbase_wales_1996-2027.csv")
    current = wales[wales.Year == "2026-27"].copy()
    current = current[
        ~current.Authority.astype(str).str.contains("Total", na=False)
    ]
    current["Data values"] = pd.to_numeric(current["Data values"], errors="coerce")

    records: list[dict[str, object]] = []
    for authority, group in current.groupby("Authority"):
        row: dict[str, object] = {
            "nation": "Wales",
            "authority": str(authority).strip(),
            "ons_code": "",
            "year": "2026-27",
        }
        for code, name in WALES_ROWS.items():
            rows = group[group.Row.astype(str).str.startswith(f"{code} -")]
            banded = rows[rows.Band.isin(list("ABCDEFGHI"))]
            row[name] = banded["Data values"].sum() if len(banded) else None
        # Wales publishes the tax base as a single per-authority total.
        tax_base = group[group.Row.astype(str).str.startswith("E1 -")]
        row["tax_base"] = (
            tax_base["Data values"].sum() if len(tax_base) else None
        )
        records.append(row)
    return pd.DataFrame(records)


def derive_rates(frame: pd.DataFrame) -> pd.DataFrame:
    """Add the rates that make councils comparable.

    Raw counts scale with dwelling stock, so a large authority always looks like
    an outlier. Rates against the chargeable stock are the comparable measure.

    Args:
        frame: The combined England and Wales table.

    Returns:
        The frame with rate columns added.
    """
    frame = frame.copy()
    # Bracket access throughout: ``empty`` and ``discount`` collide with
    # DataFrame attributes, so attribute access silently returns a method.
    frame["exempt_rate"] = (frame["exempt"] / frame["chargeable"] * 100).round(2)
    frame["empty_rate"] = (frame["empty"] / frame["chargeable"] * 100).round(2)
    frame["second_home_rate"] = (
        frame["second_homes"] / frame["chargeable"] * 100
    ).round(2)

    # England publishes the single-adult discount separately; Wales folds it into
    # B2a, so the two columns are aligned under one name before combining.
    discount = frame.get("single_adult_discount")
    if discount is None:
        discount = pd.Series(index=frame.index, dtype=float)
    wales_discount = frame.get("discount_25")
    if wales_discount is None:
        wales_discount = pd.Series(index=frame.index, dtype=float)
    frame["discount_25_combined"] = discount.fillna(wales_discount)
    frame["discount_rate"] = (
        frame["discount_25_combined"] / frame["chargeable"] * 100
    ).round(2)
    return frame


def main() -> None:
    """Build and write the council-level discounts table."""
    print("Building council-level discounts and exemptions")

    england = parse_england()
    wales = parse_wales()
    combined = pd.concat([england, wales], ignore_index=True)
    combined = derive_rates(combined)

    columns = [
        "nation",
        "authority",
        "ons_code",
        "year",
        "chargeable",
        "exempt",
        "empty",
        "second_homes",
        "discount_25_combined",
        "tax_base",
        "exempt_rate",
        "empty_rate",
        "second_home_rate",
        "discount_rate",
    ]
    combined = combined[columns].sort_values(["nation", "authority"])
    combined.to_csv(DATA_PROC / "council_discounts.csv", index=False)
    print(f"  council_discounts.csv          {len(combined):>6,} rows")

    print("\n=== COUNCIL-LEVEL COVERAGE ===")
    print(
        combined.groupby("nation")
        .agg(
            councils=("authority", "size"),
            chargeable=("chargeable", "sum"),
            exempt=("exempt", "sum"),
            empty=("empty", "sum"),
        )
        .to_string()
    )

    print("\n=== HIGHEST EXEMPT RATE ===")
    top = combined.nlargest(6, "exempt_rate")
    print(top[["nation", "authority", "exempt_rate", "exempt", "chargeable"]]
          .to_string(index=False))

    print("\n=== LOWEST EXEMPT RATE ===")
    low = combined.nsmallest(6, "exempt_rate")
    print(low[["nation", "authority", "exempt_rate", "exempt", "chargeable"]]
          .to_string(index=False))

    print("\n=== HIGHEST SECOND-HOME RATE ===")
    top_sh = combined.nlargest(6, "second_home_rate")
    print(top_sh[["nation", "authority", "second_home_rate", "second_homes"]]
          .to_string(index=False))

    print("\n=== HIGHEST EMPTY-HOME RATE ===")
    top_empty = combined.nlargest(6, "empty_rate")
    print(top_empty[["nation", "authority", "empty_rate", "empty"]]
          .to_string(index=False))


if __name__ == "__main__":
    main()
