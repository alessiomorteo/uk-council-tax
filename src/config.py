"""Shared configuration: paths, constants, and the statutory band ladders."""
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
# All Open Government Licence v3.0.
SOURCES = {
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

ASHE_ZIP_MEMBER = "Home Geography Table 8.7a   Annual pay - Gross 2025.xlsx"

# ---------------------------------------------------------------- ladders
# England & Wales: LGFA 1992 s.5 (Wales adds Band I at 21/9 after the 2003 revaluation).
ENGLAND_WALES = {
    "A": 6 / 9, "B": 7 / 9, "C": 8 / 9, "D": 1.0,
    "E": 11 / 9, "F": 13 / 9, "G": 15 / 9, "H": 18 / 9, "I": 21 / 9,
}

# Scotland: standard ladder until 2016-17, then SSI 2016/368 from 1 April 2017.
SCOTLAND_PRE_2017 = {
    "A": 6 / 9, "B": 7 / 9, "C": 8 / 9, "D": 1.0,
    "E": 11 / 9, "F": 13 / 9, "G": 15 / 9, "H": 18 / 9,
}
SCOTLAND_POST_2017 = {
    "A": 240 / 360, "B": 280 / 360, "C": 320 / 360, "D": 360 / 360,
    "E": 473 / 360, "F": 585 / 360, "G": 705 / 360, "H": 882 / 360,
}

SCOTLAND_REFORM_YEAR = 2017  # first financial year using the new ladder

BANDS = ["A", "B", "C", "D", "E", "F", "G", "H", "I"]

# Property value thresholds, for the alignment caveats.
VALUATION_THRESHOLDS = {
    "England":  {"date": "1991-04-01", "bands": 8,
                 "D": (68_001, 88_000)},
    "Scotland": {"date": "1991-04-01", "bands": 8,
                 "D": (45_001, 58_000)},
    "Wales":    {"date": "2003-04-01", "bands": 9,
                 "D": (91_001, 123_000)},
}

# ONS recoded these authorities; boundary files may carry the old code.
ONS_RECODE = {
    "E08000016": "E08000038",  # Barnsley
    "E08000019": "E08000039",  # Sheffield
}

NATION_BY_PREFIX = {"E": "England", "W": "Wales", "S": "Scotland", "N": "Northern Ireland"}


def ladder(nation: str, year: str) -> dict:
    """Return the statutory multiplier ladder for a nation in a given financial year."""
    if nation == "Scotland":
        start = int(year.split("-")[0])
        return SCOTLAND_POST_2017 if start >= SCOTLAND_REFORM_YEAR else SCOTLAND_PRE_2017
    return ENGLAND_WALES


def norm_name(s: str) -> str:
    """Normalise an authority name for joining across ONS / council sources."""
    import re
    s = str(s).lower().strip().replace("&", "and").replace(",", " ")
    s = re.sub(r"\bcouncil\b", "", s)
    s = re.sub(r"\bcounty\b", "", s)
    s = re.sub(r"[^a-z0-9 ]", "", s)
    s = re.sub(r"\bcity of\b", "", s)
    s = re.sub(r"\bof\b", "", s)
    return re.sub(r"\s+", " ", s).strip()
