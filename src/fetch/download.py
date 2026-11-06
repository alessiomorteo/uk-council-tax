"""Download every raw source into data/raw. The stage is idempotent."""

import sys
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import ASHE_ZIP_MEMBER, DATA_RAW, SOURCES  # noqa: E402

USER_AGENT: dict[str, str] = {
    "User-Agent": "Mozilla/5.0 (uk-council-tax-dataset)"
}

# Anything smaller than this is assumed to be an error page rather than data.
MIN_PLAUSIBLE_BYTES: int = 1_000


def fetch(url: str, dest: Path, force: bool = False) -> Path:
    """Download a URL to a local path, skipping work already done.

    Args:
        url: The source URL to retrieve.
        dest: Destination path for the downloaded bytes.
        force: When True, re-download even if a plausible file already exists.

    Returns:
        The destination path, whether freshly written or reused.

    Raises:
        urllib.error.URLError: If the request fails.
    """
    if dest.exists() and dest.stat().st_size > MIN_PLAUSIBLE_BYTES and not force:
        print(f"  skip  {dest.name} ({dest.stat().st_size:,} bytes)")
        return dest

    request = urllib.request.Request(url, headers=USER_AGENT)
    with urllib.request.urlopen(request, timeout=180) as response:
        dest.write_bytes(response.read())

    print(f"  get   {dest.name} ({dest.stat().st_size:,} bytes)")
    return dest


def extract_ashe(archive: Path, target: Path) -> None:
    """Extract the single ASHE workbook needed from the published zip.

    The published archive holds roughly twenty workbooks; only the annual pay
    table by local authority is required.

    Args:
        archive: The downloaded ASHE zip file.
        target: Destination path for the extracted workbook.
    """
    with zipfile.ZipFile(archive) as bundle:
        with bundle.open(ASHE_ZIP_MEMBER) as source:
            target.write_bytes(source.read())
    print(f"  unzip {target.name} ({target.stat().st_size:,} bytes)")


def main(force: bool = False) -> None:
    """Fetch every raw source required by the pipeline.

    Args:
        force: When True, re-download files that are already present.
    """
    print("Fetching raw sources ->", DATA_RAW)

    fetch(SOURCES["england_bands"], DATA_RAW / "england_tables_1-9_2026-27.ods", force)
    fetch(SOURCES["england_bandd"], DATA_RAW / "england_band_d_2026-27.ods", force)
    fetch(SOURCES["wales_bands"], DATA_RAW / "wales_bands_1996-2027.csv", force)
    fetch(SOURCES["scotland_bands"], DATA_RAW / "scotland_bands_2026-27.xlsx", force)

    # Council Taxbase: dwellings per band, by local authority.
    fetch(SOURCES["taxbase_england"], DATA_RAW / "taxbase_england_2025.xlsx", force)
    fetch(SOURCES["taxbase_wales"], DATA_RAW / "taxbase_wales_1996-2027.csv", force)
    fetch(SOURCES["taxbase_scotland"], DATA_RAW / "taxbase_scotland_2026.xlsx", force)
    fetch(
        SOURCES["taxbase_scotland_band_d"],
        DATA_RAW / "taxbase_scotland_band_d_2026.xlsx",
        force,
    )

    ashe_archive = DATA_RAW / "ashe_table8_2025.zip"
    fetch(SOURCES["ashe_earnings"], ashe_archive, force)
    ashe_target = DATA_RAW / "ashe_annual_pay_2025.xlsx"
    if force or not ashe_target.exists():
        extract_ashe(ashe_archive, ashe_target)

    # ONS local authority boundaries and attributes, via the ArcGIS REST API.
    # The portal download endpoint returns an async job stub, so query the
    # feature service directly.
    base = SOURCES["lad_boundaries"]
    fetch(
        base
        + "?where=1%3D1&outFields=LAD24CD,LAD24NM,LONG,LAT"
        + "&returnGeometry=false&f=json&resultRecordCount=2000",
        DATA_RAW / "lad_attributes.json",
        force,
    )
    fetch(
        base
        + "?where=1%3D1&outFields=LAD24CD,LAD24NM"
        + "&returnGeometry=true&f=geojson&outSR=4326&resultRecordCount=2000",
        DATA_RAW / "lad_boundaries.geojson",
        force,
    )

    print("done.")


if __name__ == "__main__":
    main(force="--force" in sys.argv)
