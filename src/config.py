"""Shared configuration: paths, source URLs, statutory ladders and ONS recodes."""

import re
from pathlib import Path

# ---------------------------------------------------------------- paths
ROOT = Path(__file__).resolve().parents[1]
DATA_RAW = ROOT / "data" / "raw"
DATA_PROC = ROOT / "data" / "processed"
OUT_FIG = ROOT / "output" / "figures"
OUT_PAGES = ROOT / "output" / "pages"
OUT_TABLES = ROOT / "output" / "tables"

for _p in (DATA_RAW, DATA_PROC, OUT_FIG, OUT_PAGES, OUT_TABLES):
    _p.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------- sources
# All material is published under the Open Government Licence v3.0.
SOURCES: dict[str, str] = {
    "england_bands": (
        "https://assets.publishing.service.gov.uk/media/69de1fa63e81003ae0422508/"
        "Tables_1-9_2026-27.ods"
    ),
    "england_bandd": (
        "https://assets.publishing.service.gov.uk/media/69e8ab2d9ca985145673b826/"
        "Band_D_2026-27.ods"
    ),
    "wales_bands": (
        "https://api.stats.gov.wales/v2/1988b6af-2a9c-43b6-8939-83e6cceb3903/"
        "data?format=csv&lang=en-gb"
    ),
    "scotland_bands": (
        "https://www.gov.scot/binaries/content/documents/govscot/publications/statistics/"
        "2019/04/council-tax-datasets/documents/average-council-tax-per-dwelling/"
        "council-tax-by-band-2026-27/council-tax-by-band-2026-27/govscot:document/"
        "CTAS+2026+-+Council+Tax+Assumptions+-+Council+Tax+by+Band+-+2026-27.xlsx"
    ),
    "ashe_earnings": (
        "https://www.ons.gov.uk/file?uri=/employmentandlabourmarket/peopleinwork/"
        "earningsandworkinghours/datasets/placeofresidencebylocalauthorityashetable8/"
        "2025revised/ashetable82025revised.zip"
    ),
    "lad_boundaries": (
        "https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/"
        "Local_Authority_Districts_December_2024_Boundaries_UK_BUC/FeatureServer/0/query"
    ),
}

ASHE_ZIP_MEMBER: str = "Home Geography Table 8.7a   Annual pay - Gross 2025.xlsx"

# ---------------------------------------------------------------- ladders
# England and Wales: Local Government Finance Act 1992, s.5. Wales adds a ninth
# band at 21/9 following the 2003 revaluation.
ENGLAND_WALES: dict[str, float] = {
    "A": 6 / 9,
    "B": 7 / 9,
    "C": 8 / 9,
    "D": 1.0,
    "E": 11 / 9,
    "F": 13 / 9,
    "G": 15 / 9,
    "H": 18 / 9,
    "I": 21 / 9,
}

# Scotland: the standard ladder held until 2016-17, then SSI 2016/368 replaced
# the E to H multipliers with effect from 1 April 2017.
SCOTLAND_PRE_2017: dict[str, float] = {
    "A": 6 / 9,
    "B": 7 / 9,
    "C": 8 / 9,
    "D": 1.0,
    "E": 11 / 9,
    "F": 13 / 9,
    "G": 15 / 9,
    "H": 18 / 9,
}
SCOTLAND_POST_2017: dict[str, float] = {
    "A": 240 / 360,
    "B": 280 / 360,
    "C": 320 / 360,
    "D": 360 / 360,
    "E": 473 / 360,
    "F": 585 / 360,
    "G": 705 / 360,
    "H": 882 / 360,
}

SCOTLAND_REFORM_YEAR: int = 2017

BANDS: list[str] = ["A", "B", "C", "D", "E", "F", "G", "H", "I"]

# Property value thresholds, used for the cross-nation alignment caveats.
VALUATION_THRESHOLDS: dict[str, dict[str, object]] = {
    "England": {"date": "1991-04-01", "bands": 8, "band_d": (68_001, 88_000)},
    "Scotland": {"date": "1991-04-01", "bands": 8, "band_d": (45_001, 58_000)},
    "Wales": {"date": "2003-04-01", "bands": 9, "band_d": (91_001, 123_000)},
}

# The ONS recoded these authorities; boundary files may carry the older code.
ONS_RECODE: dict[str, str] = {
    "E08000016": "E08000038",  # Barnsley
    "E08000019": "E08000039",  # Sheffield
}

NATION_BY_PREFIX: dict[str, str] = {
    "E": "England",
    "W": "Wales",
    "S": "Scotland",
    "N": "Northern Ireland",
}


def ladder(nation: str, year: str) -> dict[str, float]:
    """Return the statutory multiplier ladder for a nation in a financial year.

    Args:
        nation: One of ``England``, ``Wales`` or ``Scotland``.
        year: Financial year as ``YYYY-YY``, for example ``2026-27``.

    Returns:
        Mapping of band letter to its multiplier against Band D. Scotland
        returns the post-2017 ladder from 2017-18 onward and the standard
        ladder before that; the other nations always return the same ladder.
    """
    if nation == "Scotland":
        start = int(year.split("-")[0])
        return SCOTLAND_POST_2017 if start >= SCOTLAND_REFORM_YEAR else SCOTLAND_PRE_2017
    return ENGLAND_WALES


def norm_name(name: str) -> str:
    """Normalise an authority name so it can be joined across sources.

    The ONS uses forms such as ``Bristol, City of`` and ``Herefordshire, County
    of`` while council publications use ``Bristol`` and ``Herefordshire``.
    Stripping the structural words and punctuation yields a common key.

    Args:
        name: An authority name from any source.

    Returns:
        A lower-case key with structural words and punctuation removed.
    """
    text = str(name).lower().strip().replace("&", "and").replace(",", " ")
    text = re.sub(r"\bcouncil\b", "", text)
    text = re.sub(r"\bcounty\b", "", text)
    text = re.sub(r"[^a-z0-9 ]", "", text)
    text = re.sub(r"\bcity of\b", "", text)
    text = re.sub(r"\bof\b", "", text)
    return re.sub(r"\s+", " ", text).strip()
