"""Parse each raw source into tidy long-format CSVs in data/processed.

Every parser returns the columns ``nation``, ``authority``, ``year``, ``band``,
``charge_gbp`` and ``source``.
"""

import re
import sys
import warnings
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import DATA_PROC, DATA_RAW, NATION_BY_PREFIX  # noqa: E402

warnings.filterwarnings("ignore")

ODF_TABLE = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
ODF_TEXT = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"

# Cap on expanding ODS repeated-cell runs; genuine data never repeats this far.
MAX_CELL_REPEAT: int = 200

BAND_LETTERS: str = "ABCDEFGH"


def read_ods_sheet(path: Path, sheet: str) -> list[list[str]]:
    """Read a single ODS sheet as a list of rows of strings.

    ODS stores runs of empty cells as one cell carrying a large
    ``number-columns-repeated``. Expanding those faithfully pads the header and
    breaks positional alignment, so the expansion is capped and trailing empties
    are stripped.

    Args:
        path: Path to the ODS workbook.
        sheet: Exact sheet name to read.

    Returns:
        One list of cell strings per row, with trailing empties removed.

    Raises:
        KeyError: If the sheet is not present in the workbook.
    """
    root = ET.fromstring(zipfile.ZipFile(path).read("content.xml"))
    for table in root.iter(ODF_TABLE + "table"):
        if table.get(ODF_TABLE + "name") != sheet:
            continue
        rows: list[list[str]] = []
        for row in table.iter(ODF_TABLE + "table-row"):
            cells: list[str] = []
            for cell in row.iter(ODF_TABLE + "table-cell"):
                repeat = int(cell.get(ODF_TABLE + "number-columns-repeated") or 1)
                text = "".join(
                    node.text or "" for node in cell.iter(ODF_TEXT + "p")
                )
                cells.extend([text] * (repeat if repeat <= MAX_CELL_REPEAT else 1))
            while cells and cells[-1] == "":
                cells.pop()
            rows.append(cells)
        return rows
    raise KeyError(f"sheet {sheet!r} not in {path.name}")


def tidy_year(header: str) -> str | None:
    """Convert a header label such as ``1993 to 1994`` to ``1993-94``.

    Args:
        header: A column header from a statistical workbook.

    Returns:
        The financial year in ``YYYY-YY`` form, or None if the header is not a
        year label.
    """
    match = re.match(r"(\d{4}) to (\d{4})", str(header).strip())
    if not match:
        return None
    return f"{match.group(1)}-{match.group(2)[2:]}"


def parse_england_bands(path: Path) -> pd.DataFrame:
    """Parse MHCLG Tables 1 to 9, sheet ``Table_9``, into a long table.

    ``Table_9`` holds area council tax by band for every billing authority. It
    is not linked from the live-tables index page, which advertises Band D only.

    Args:
        path: Path to the Tables 1 to 9 workbook.

    Returns:
        One row per authority and band, with the charge in pounds.
    """
    frame = pd.read_excel(path, sheet_name="Table_9", engine="odf", header=None)
    body = frame.iloc[3:].copy()
    body.columns = [str(column).strip() for column in frame.iloc[2].tolist()]
    body = body[body["Authority"].notna()]

    records: list[dict[str, object]] = []
    for _, row in body.iterrows():
        for band in BAND_LETTERS:
            column = f"Band {band}"
            if column not in body.columns or pd.isna(row[column]):
                continue
            records.append(
                {
                    "nation": "England",
                    "authority": str(row["Authority"]).strip(),
                    "ons_code": str(row["ONS Code"]).strip(),
                    "year": "2026-27",
                    "band": band,
                    "charge_gbp": round(float(row[column]), 2),
                    "source": "MHCLG Tables 1-9 (Table_9)",
                }
            )
    return pd.DataFrame(records)


def parse_england_band_d(path: Path) -> pd.DataFrame:
    """Parse the Band D live table covering 1993-94 onward.

    The table is published as three parallel sheets: including parish precepts,
    excluding them, and the area total. The header carries a trailing ``Notes``
    label that the data rows omit, so it is dropped before columns are mapped by
    position; otherwise every year shifts by one.

    Args:
        path: Path to the Band D live table workbook.

    Returns:
        One row per authority, year and measure, with the charge in pounds.
    """
    sheets = [
        ("inc_PP", "band_d_incl_parish"),
        ("exc_PP", "band_d_excl_parish"),
        ("Area_CT", "band_d_area_total"),
    ]
    frames: list[pd.DataFrame] = []

    for sheet, measure in sheets:
        rows = read_ods_sheet(path, sheet)
        header = rows[2]
        if header and str(header[-1]).strip().lower() == "notes":
            header = header[:-1]

        year_positions = [
            index for index, label in enumerate(header) if tidy_year(label)
        ]
        years = [tidy_year(header[index]) for index in year_positions]
        first_year_column = year_positions[0]

        records: list[dict[str, object]] = []
        for row in rows[3:]:
            if not row or len(row) < 3:
                continue
            authority = row[2].strip()
            if not authority:
                continue
            for offset, year in enumerate(years):
                index = first_year_column + offset
                if index >= len(row):
                    continue
                raw = row[index].strip()
                try:
                    value = float(raw.replace(",", ""))
                except ValueError:
                    continue  # suppression and not-applicable sentinels
                records.append(
                    {
                        "nation": "England",
                        "authority": authority,
                        "ons_code": row[1].strip() if len(row) > 1 else "",
                        "year": year,
                        "band": "D",
                        "measure": measure,
                        "charge_gbp": value,
                        "source": "MHCLG Band D live table",
                    }
                )
        frames.append(pd.DataFrame(records))

    return pd.concat(frames, ignore_index=True)


def parse_wales(path: Path) -> pd.DataFrame:
    """Parse the StatsWales council tax levels export.

    The export includes a ``Total Unitary Authorities`` aggregate row, which is
    dropped so that per-authority counts stay correct.

    Args:
        path: Path to the StatsWales CSV export.

    Returns:
        One row per authority, year and band, covering 1996-97 onward.
    """
    frame = pd.read_csv(path)
    frame = frame[frame["Authority"] != "Total Unitary Authorities"]

    records: list[dict[str, object]] = []
    for _, row in frame.iterrows():
        try:
            value = float(row["Data values"])
        except (TypeError, ValueError):
            continue
        records.append(
            {
                "nation": "Wales",
                "authority": str(row["Authority"]).strip(),
                "ons_code": "",
                "year": str(row["Year"]),
                "band": str(row["Band"]),
                "charge_gbp": round(value, 2),
                "source": "StatsWales API v2",
            }
        )
    return pd.DataFrame(records)


def parse_scotland(path: Path) -> pd.DataFrame:
    """Parse the Scottish Government Council Tax by Band workbook.

    The workbook appends prose notes below the table, including a row reading
    ``Excludes Water and Sewerage``. Those rows are filtered out or they parse
    as authorities and inflate the council count.

    Args:
        path: Path to the CTAS Council Tax by Band workbook.

    Returns:
        One row per council and band for 2026-27.

    Raises:
        ValueError: If the Band A to H header row cannot be located.
    """
    frame = pd.read_excel(path, header=None)

    header_index: int | None = None
    for index in range(min(15, len(frame))):
        values = [str(cell) for cell in frame.iloc[index, :10] if pd.notna(cell)]
        present = sum(1 for band in BAND_LETTERS if f"Band {band}" in values)
        if present >= 6:
            header_index = index
            break
    if header_index is None:
        raise ValueError("Scotland: could not locate the Band A to H header row")

    skip_prefixes = ("ratio", "scotland", "source", "valuation", "excludes")
    records: list[dict[str, object]] = []

    for index in range(header_index + 1, len(frame)):
        name = frame.iloc[index, 0]
        if not isinstance(name, str):
            continue
        name = name.strip()
        if not name or name.lower().startswith(skip_prefixes):
            continue
        try:
            values = [float(frame.iloc[index, column]) for column in range(1, 9)]
        except (TypeError, ValueError):
            continue
        if values[3] <= 0:
            continue
        for band, value in zip(BAND_LETTERS, values):
            records.append(
                {
                    "nation": "Scotland",
                    "authority": name,
                    "ons_code": "",
                    "year": "2026-27",
                    "band": band,
                    "charge_gbp": round(value, 2),
                    "source": "Scottish Government CTAS",
                }
            )
    return pd.DataFrame(records)


def parse_ashe(path: Path) -> pd.DataFrame:
    """Parse ASHE Table 8.7a, sheet ``All``, for median gross annual pay.

    Args:
        path: Path to the ASHE annual pay workbook.

    Returns:
        One row per local authority with its ONS code and median and mean pay.
    """
    frame = pd.read_excel(path, sheet_name="All", header=None)
    frame = frame.iloc[5:, [0, 1, 3, 5]].copy()
    frame.columns = ["name", "code", "median", "mean"]
    # The published codes carry a leading apostrophe as a text marker.
    frame["code"] = frame["code"].astype(str).str.replace("\u2019", "", regex=False)
    frame["code"] = frame["code"].str.replace("'", "", regex=False).str.strip()
    frame = frame[frame["code"].str.match(r"^(E0[6-9]|S12|W06)\d{6}$")].copy()
    frame["median"] = pd.to_numeric(frame["median"], errors="coerce")
    frame["mean"] = pd.to_numeric(frame["mean"], errors="coerce")
    frame["nation"] = frame["code"].str[0].map(NATION_BY_PREFIX)
    return frame[["nation", "name", "code", "median", "mean"]]


def main() -> None:
    """Parse every raw source and write the processed CSVs."""
    print("Parsing raw -> processed")

    england = parse_england_bands(DATA_RAW / "england_tables_1-9_2026-27.ods")
    england.to_csv(DATA_PROC / "england_bands_2026-27.csv", index=False)
    print(f"  england_bands_2026-27.csv      {len(england):>6,} rows")

    band_d = parse_england_band_d(DATA_RAW / "england_band_d_2026-27.ods")
    band_d.to_csv(DATA_PROC / "england_band_d_1993-2027.csv", index=False)
    print(f"  england_band_d_1993-2027.csv   {len(band_d):>6,} rows")

    wales = parse_wales(DATA_RAW / "wales_bands_1996-2027.csv")
    wales.to_csv(DATA_PROC / "wales_bands_1996-2027.csv", index=False)
    print(f"  wales_bands_1996-2027.csv      {len(wales):>6,} rows")

    scotland = parse_scotland(DATA_RAW / "scotland_bands_2026-27.xlsx")
    scotland.to_csv(DATA_PROC / "scotland_bands_2026-27.csv", index=False)
    print(f"  scotland_bands_2026-27.csv     {len(scotland):>6,} rows")

    ashe = parse_ashe(DATA_RAW / "ashe_annual_pay_2025.xlsx")
    ashe.to_csv(DATA_PROC / "ashe_earnings_2025.csv", index=False)
    print(f"  ashe_earnings_2025.csv         {len(ashe):>6,} rows")

    combined = pd.concat([england, wales, scotland], ignore_index=True)
    combined.to_csv(DATA_PROC / "uk_bands_2026-27.csv", index=False)
    print(f"  uk_bands_2026-27.csv           {len(combined):>6,} rows")


if __name__ == "__main__":
    main()
