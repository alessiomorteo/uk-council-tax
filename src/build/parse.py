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


# ------------------------------------------------------------------ taxbase
def parse_taxbase_england(path: Path) -> pd.DataFrame:
    """Parse the England Council Taxbase workbook into a long table.

    The ``Council Taxbase Data`` sheet holds 35 tables side by side, so the
    header row carries 31 duplicate ``Band A`` labels. Columns are therefore
    selected by position rather than by name.

    Two blocks are taken:

    - columns 5 to 12, the headline dwelling count per band (Table 1.01)
    - column 287, the published tax base in Band D equivalents (Table 1.29)

    The published tax base is *not* ``dwellings x statutory ratio``. It applies
    discounts, premiums and exemptions first, which makes it roughly 6 to 9 per
    cent lower than the naive product. Both are recorded so the difference is
    visible rather than silently wrong.

    Args:
        path: Path to the MHCLG Council Taxbase workbook.

    Returns:
        One row per authority and band, with the dwelling count, plus a
        ``total`` band carrying the published tax base.
    """
    raw = pd.read_excel(path, sheet_name="Council Taxbase Data", header=None)
    body = raw.iloc[6:].copy()
    body.columns = range(len(raw.columns))

    keep = {
        0: "ecode",
        1: "ons_code",
        2: "region",
        3: "authority",
        5: "band_a",
        6: "band_b",
        7: "band_c",
        8: "band_d",
        9: "band_e",
        10: "band_f",
        11: "band_g",
        12: "band_h",
        13: "total",
        287: "tax_base",  # Table 1.29, published Band D equivalents
    }
    frame = body[list(keep)].rename(columns=keep)
    frame = frame[frame.ons_code.astype(str).str.match(r"^E\d{8}$")].copy()
    # Drop the England aggregate row.
    frame = frame[frame.ons_code != "E92000001"]

    records: list[dict[str, object]] = []
    for _, row in frame.iterrows():
        for band in BAND_LETTERS:
            value = row[f"band_{band.lower()}"]
            if pd.isna(value):
                continue
            records.append(
                {
                    "nation": "England",
                    "authority": str(row["authority"]).strip(),
                    "ons_code": str(row["ons_code"]).strip(),
                    "year": "2025-26",
                    "band": band,
                    "dwellings": int(value),
                    "tax_base": None,
                    "source": "MHCLG Council Taxbase 2025",
                }
            )
        if pd.notna(row["tax_base"]):
            records.append(
                {
                    "nation": "England",
                    "authority": str(row["authority"]).strip(),
                    "ons_code": str(row["ons_code"]).strip(),
                    "year": "2025-26",
                    "band": "Total",
                    "dwellings": int(row["total"]) if pd.notna(row["total"]) else None,
                    "tax_base": float(row["tax_base"]),
                    "source": "MHCLG Council Taxbase 2025 (Table 1.29)",
                }
            )
    return pd.DataFrame(records)


def parse_taxbase_wales(path: Path) -> pd.DataFrame:
    """Parse the StatsWales Council Taxbase export into a long table.

    Wales publishes 64 different measures per band, not one. Two are taken:

    - ``A1 - All chargeable dwellings``, the headline dwelling count
    - ``E1 - Total band D equivalent dwellings``, the published tax base

    Only A1 is broken down by band; E1 is published as a per-authority total,
    so it is recorded on a ``Total`` band row. The remaining 62 measures cover
    discounts, second homes and empty properties.

    Args:
        path: Path to the StatsWales taxbase CSV export.

    Returns:
        One row per authority, year and band, plus a ``Total`` row per
        authority carrying the published Band D equivalent tax base.
    """
    frame = pd.read_csv(path)
    frame["Row"] = frame["Row"].astype(str)

    records: list[dict[str, object]] = []

    # Headline dwelling counts, broken down by band.
    a1 = frame[frame["Row"].str.startswith("A1")].copy()
    a1 = a1[a1["Band"] != "Total"]
    a1 = a1[~a1["Authority"].astype(str).str.contains("Total", na=False)]
    for _, row in a1.iterrows():
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
                "dwellings": int(round(value)),
                "tax_base": None,
                "source": "StatsWales Council tax dwellings (A1)",
            }
        )

    # Published Band D equivalent tax base, per authority.
    e1 = frame[frame["Row"].str.startswith("E1 -")].copy()
    e1 = e1[~e1["Authority"].astype(str).str.contains("Total", na=False)]
    for _, row in e1.iterrows():
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
                "band": "Total",
                "dwellings": None,
                "tax_base": value,
                "source": "StatsWales band D equivalents (E1)",
            }
        )
    return pd.DataFrame(records)


def parse_taxbase_scotland(path: Path) -> pd.DataFrame:
    """Parse the Scottish Government chargeable dwellings workbook.

    The sheet appends two prose rows after the 32 councils, a ``Source:`` line
    and a ``Note:`` line. Left unfiltered they parse as authorities and inflate
    the count to 34.

    Scotland publishes Band D equivalents in a separate workbook, so the
    ``tax_base`` column is left empty here and joined in later.

    Args:
        path: Path to the CTAXBASE chargeable dwellings workbook.

    Returns:
        One row per council and band, with the dwelling count.

    Raises:
        ValueError: If the Band A to H header row cannot be located.
    """
    frame = pd.read_excel(path, header=None)

    header_index: int | None = None
    for index in range(min(15, len(frame))):
        values = [str(cell) for cell in frame.iloc[index, :10] if pd.notna(cell)]
        if sum(1 for band in BAND_LETTERS if f"Band {band}" in values) >= 6:
            header_index = index
            break
    if header_index is None:
        raise ValueError("Scotland taxbase: could not locate the band header row")

    records: list[dict[str, object]] = []
    for index in range(header_index + 1, len(frame)):
        name = frame.iloc[index, 0]
        if not isinstance(name, str):
            continue
        name = name.strip()
        if not name or name.lower().startswith(
                ("scotland", "source", "note", "ratio", "valuation")):
            continue
        try:
            values = [float(frame.iloc[index, column]) for column in range(1, 9)]
        except (TypeError, ValueError):
            continue
        for band, value in zip(BAND_LETTERS, values):
            records.append(
                {
                    "nation": "Scotland",
                    "authority": name,
                    "ons_code": "",
                    "year": "2026-27",
                    "band": band,
                    "dwellings": int(round(value)),
                    "tax_base": None,
                    "source": "Scottish Government CTAXBASE 2026",
                }
            )
    return pd.DataFrame(records)


def parse_taxbase_scotland_band_d(path: Path) -> pd.DataFrame:
    """Parse the Scottish Band D equivalents workbook.

    The sheet is a wide year-by-column table: row 4 carries the years, row 5 the
    Scotland total, rows 6 onward one council each. The latest year column is
    taken as the published tax base.

    Args:
        path: Path to the CTAXBASE Band D equivalents workbook.

    Returns:
        One row per council with the published Band D equivalent tax base.

    Raises:
        ValueError: If the year header row cannot be located.
    """
    frame = pd.read_excel(path, sheet_name="Band D Equivalents", header=None)

    year_row: int | None = None
    for index in range(min(10, len(frame))):
        years = pd.to_numeric(frame.iloc[index, 1:], errors="coerce")
        if years.notna().sum() >= 10:
            year_row = index
            break
    if year_row is None:
        raise ValueError("Scotland Band D equivalents: could not locate year row")

    years = pd.to_numeric(frame.iloc[year_row, 1:], errors="coerce")
    latest_col = 1 + int(years.notna().values.nonzero()[0][-1])
    latest_year = int(years.dropna().iloc[-1])

    records: list[dict[str, object]] = []
    for index in range(year_row + 1, len(frame)):
        name = frame.iloc[index, 0]
        if not isinstance(name, str):
            continue
        name = name.strip()
        if not name or name.lower().startswith(("scotland", "source", "note")):
            continue
        # Footnotes and revision notes sit in the name column after the councils
        # and are long prose rather than authority names.
        if len(name) > 60 or name[0].islower():
            continue
        try:
            value = float(frame.iloc[index, latest_col])
        except (TypeError, ValueError):
            continue
        records.append(
            {
                "nation": "Scotland",
                "authority": name,
                "ons_code": "",
                "year": f"{latest_year}-{str(latest_year + 1)[-2:]}",
                "band": "Total",
                "dwellings": None,
                "tax_base": value,
                "source": "Scottish Government Band D equivalents 2026",
            }
        )
    return pd.DataFrame(records)


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

    taxbase_england = parse_taxbase_england(DATA_RAW / "taxbase_england_2025.xlsx")
    taxbase_wales = parse_taxbase_wales(DATA_RAW / "taxbase_wales_1996-2027.csv")
    taxbase_scotland = parse_taxbase_scotland(DATA_RAW / "taxbase_scotland_2026.xlsx")
    taxbase_scotland_bd = parse_taxbase_scotland_band_d(
        DATA_RAW / "taxbase_scotland_band_d_2026.xlsx"
    )
    taxbase = pd.concat(
        [taxbase_england, taxbase_wales, taxbase_scotland, taxbase_scotland_bd],
        ignore_index=True,
    )
    taxbase.to_csv(DATA_PROC / "taxbase_long.csv", index=False)
    print(f"  taxbase_long.csv               {len(taxbase):>6,} rows")

    combined = pd.concat([england, wales, scotland], ignore_index=True)
    combined.to_csv(DATA_PROC / "uk_bands_2026-27.csv", index=False)
    print(f"  uk_bands_2026-27.csv           {len(combined):>6,} rows")


if __name__ == "__main__":
    main()
