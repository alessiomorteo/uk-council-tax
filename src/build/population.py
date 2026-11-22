"""Parse the ONS mid-year population estimates into a council-level table.

One workbook carries four measures that matter here, each spanning 2011 to 2025:

- MYE4: total population by local authority
- MYE5: area in square kilometres and population density
- MYE6: median age

All three use the same geography conventions: a code in column 0, a name in
column 1, a geography type in column 2, then one column per year. The geography
type is the filter that matters, because the sheets interleave countries,
regions, counties and metropolitan counties with the 350 billing authorities.
Counties sit above districts and would double-count if included.
"""
import sys
import warnings
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import DATA_PROC, DATA_RAW  # noqa: E402

warnings.filterwarnings("ignore")

# The header sits on row 7 and data starts on row 8, on all three sheets.
HEADER_ROW = 7
FIRST_DATA_ROW = 8

# Geography types that correspond to a billing authority. Countries, regions,
# counties and metropolitan counties are deliberately excluded: counties sit
# above districts, so including them double-counts the same population.
AUTHORITY_TYPES: set[str] = {
    "Unitary Authority",
    "London Borough",
    "Metropolitan District",
    "Non-metropolitan District",
    "Council Area",
    "Local Government District",
}


def _year_from_header(header: object) -> str:
    """Extract a four-digit year from a header cell.

    Args:
        header: The header cell value, for example "2025 people per sq. km" or
            "Mid-2025".

    Returns:
        The four-digit year as a string, or an empty string if none is present.
    """
    digits = "".join(ch for ch in str(header).split(".")[0] if ch.isdigit())
    return digits if len(digits) == 4 else ""


def _read_sheet(path: Path, sheet: str) -> tuple[pd.DataFrame, list[object]]:
    """Read one MYE sheet, returning authority rows and the header row.

    Args:
        path: Path to the mid-year estimates workbook.
        sheet: Worksheet name.

    Returns:
        A tuple of the authority rows and the header row as a list.
    """
    raw = pd.read_excel(path, sheet_name=sheet, header=None)
    header = raw.iloc[HEADER_ROW].tolist()
    body = raw.iloc[FIRST_DATA_ROW:].reset_index(drop=True)
    body = body[body[2].isin(AUTHORITY_TYPES)].copy()
    body = body[body[0].astype(str).str.match(r"^[EWS]\d{8}$")]
    return body, header


def parse_population(path: Path) -> pd.DataFrame:
    """Build the long population, density and median-age table.

    Args:
        path: Path to the mid-year estimates workbook.

    Returns:
        One row per authority and year with population, density, median age and
        area. ``nation`` is derived from the ONS code prefix.
    """
    # Population by year.
    population_raw, population_header = _read_sheet(path, "MYE4")
    records: list[dict[str, object]] = []
    for _, row in population_raw.iterrows():
        code = str(row[0]).strip()
        for column in range(3, population_raw.shape[1]):
            year = _year_from_header(population_header[column])
            if not year:
                continue
            records.append(
                {
                    "ons_code": code,
                    "authority": str(row[1]).strip(),
                    "year": year,
                    "population": pd.to_numeric(row[column], errors="coerce"),
                }
            )
    frame = pd.DataFrame(records)

    # Area and density. MYE5 alternates population and density per year, newest
    # first, so density columns are the population columns plus one.
    density_raw, density_header = _read_sheet(path, "MYE5")
    area_by_code: dict[str, float] = {
        str(row[0]).strip(): pd.to_numeric(row[3], errors="coerce")
        for _, row in density_raw.iterrows()
    }
    density_records: list[dict[str, object]] = []
    for _, row in density_raw.iterrows():
        code = str(row[0]).strip()
        for column in range(3, density_raw.shape[1]):
            text = str(density_header[column])
            if "people per sq" not in text:
                continue
            year = _year_from_header(text)
            if not year:
                continue
            density_records.append(
                {
                    "ons_code": code,
                    "year": year,
                    "density": pd.to_numeric(row[column], errors="coerce"),
                }
            )
    density = pd.DataFrame(density_records)
    if len(density):
        frame = frame.merge(density, on=["ons_code", "year"], how="left")

    # Median age.
    age_raw, age_header = _read_sheet(path, "MYE6")
    age_records: list[dict[str, object]] = []
    for _, row in age_raw.iterrows():
        code = str(row[0]).strip()
        for column in range(3, age_raw.shape[1]):
            year = _year_from_header(age_header[column])
            if not year:
                continue
            age_records.append(
                {
                    "ons_code": code,
                    "year": year,
                    "median_age": pd.to_numeric(row[column], errors="coerce"),
                }
            )
    age = pd.DataFrame(age_records)
    if len(age):
        frame = frame.merge(age, on=["ons_code", "year"], how="left")

    frame["area_sq_km"] = frame["ons_code"].map(area_by_code)
    frame["nation"] = frame["ons_code"].str[0].map(
        {"E": "England", "W": "Wales", "S": "Scotland"}
    )
    frame = frame[frame["nation"].notna()]
    return frame.sort_values(["nation", "authority", "year"])


def main() -> None:
    """Parse and write the council-level population table."""
    print("Parsing mid-year population estimates")
    path = DATA_RAW / "population_mye_2025.xlsx"
    frame = parse_population(path)
    frame.to_csv(DATA_PROC / "population_long.csv", index=False)
    print(f"  population_long.csv            {len(frame):>6,} rows")

    latest = frame[frame.year == "2025"]
    print("\n=== 2025 ===")
    print(
        latest.groupby("nation")
        .agg(
            authorities=("authority", "nunique"),
            population_m=("population", lambda s: round(s.sum() / 1e6, 2)),
            median_age=("median_age", "median"),
            density=("density", "median"),
        )
        .to_string()
    )

    print(f"\n  years: {frame.year.min()} to {frame.year.max()}")
    print(f"  authorities: {frame.ons_code.nunique()}")

    print("\n=== DENSEST ===")
    print(
        latest.nlargest(5, "density")[
            ["nation", "authority", "density", "population", "area_sq_km"]
        ].to_string(index=False)
    )
    print("\n=== OLDEST BY MEDIAN AGE ===")
    print(
        latest.nlargest(5, "median_age")[
            ["nation", "authority", "median_age", "population"]
        ].to_string(index=False)
    )
    print("\n=== YOUNGEST BY MEDIAN AGE ===")
    print(
        latest.nsmallest(5, "median_age")[
            ["nation", "authority", "median_age", "population"]
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()
