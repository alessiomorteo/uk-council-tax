"""Probe council-level discount and exemption data for all three nations.

England and Wales publish banded, per-council discount and exemption measures.
Scotland does not, beyond empty properties and second homes. This script
establishes exactly what is available at council grain before anything is built.
"""
import warnings
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path.home() / "uk-council-tax"
RAW = ROOT / "data" / "raw"


def england_blocks() -> dict[str, int]:
    """Map each England block title to the column holding its Total.

    The sheet holds 35 tables side by side. Each block is Band A to H followed by
    a Total, but a few blocks carry an extra disabled-relief column, so the Total
    cannot be found by a fixed offset. It is located by scanning the leaf header
    within the block's column range.

    Returns:
        A mapping from the block title to its Total column index.
    """
    raw = pd.read_excel(
        RAW / "taxbase_england_2025.xlsx",
        sheet_name="Council Taxbase Data",
        header=None,
    )
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


def main() -> None:
    """Print what is available at council grain."""
    print("=== ENGLAND: council-level blocks available ===\n")
    blocks = england_blocks()
    raw = pd.read_excel(
        RAW / "taxbase_england_2025.xlsx",
        sheet_name="Council Taxbase Data",
        header=None,
    )
    body = raw.iloc[6:].copy()
    body.columns = range(len(raw.columns))
    body = body[body[1].astype(str).str.match(r"^E\d{8}$")]
    body = body[body[1] != "E92000001"]

    interesting = [
        "1.01", "1.02", "1.04", "1.08", "1.09", "1.10",
        "1.11", "1.18", "1.23", "1.26", "1.29", "1.31",
    ]
    for title, col in blocks.items():
        if not any(title.startswith(f"Table {code}") for code in interesting):
            continue
        values = pd.to_numeric(body[col], errors="coerce")
        print(
            f"  col {col:3d}  n={values.notna().sum():3d}  "
            f"sum={values.sum():>13,.0f}  {title[:64]}"
        )

    print("\n=== WALES: council-level row types ===\n")
    wales = pd.read_csv(RAW / "taxbase_wales_1996-2027.csv")
    current = wales[wales.Year == "2026-27"]
    current = current[
        ~current.Authority.astype(str).str.contains("Total", na=False)
    ]
    for code in ["A1", "D1", "D2", "B1", "B2a", "B2b", "B3", "H7", "H8"]:
        rows = current[current.Row.astype(str).str.startswith(f"{code} -")]
        if not len(rows):
            continue
        banded = rows[rows.Band.isin(list("ABCDEFGHI"))]
        label = str(rows.Row.iloc[0])[:52]
        print(
            f"  {code:4s} authorities={banded.Authority.nunique():3d}  "
            f"sum={banded['Data values'].astype(float).sum():>12,.0f}  {label}"
        )

    print("\n=== Scotland ===\n")
    print("  chargeable dwellings: council-level, banded")
    print("  empty + second homes: council-level, separate publication")
    print("  discounts / exemptions: no routine council-level publication")


if __name__ == "__main__":
    main()
