"""Download every raw source into data/raw/. Idempotent — skips existing files."""
import sys
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import DATA_RAW, SOURCES, ASHE_ZIP_MEMBER  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0 (uk-council-tax-dataset)"}


def fetch(url: str, dest: Path, force: bool = False) -> Path:
    if dest.exists() and dest.stat().st_size > 1000 and not force:
        print(f"  skip  {dest.name} ({dest.stat().st_size:,} bytes)")
        return dest
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=180) as r, open(dest, "wb") as fh:
        fh.write(r.read())
    print(f"  get   {dest.name} ({dest.stat().st_size:,} bytes)")
    return dest


def main(force: bool = False):
    print("Fetching raw sources ->", DATA_RAW)

    fetch(SOURCES["england_bands"], DATA_RAW / "england_tables_1-9_2026-27.ods", force)
    fetch(SOURCES["england_bandd"], DATA_RAW / "england_band_d_2026-27.ods", force)
    fetch(SOURCES["wales_bands"], DATA_RAW / "wales_bands_1996-2027.csv", force)
    fetch(SOURCES["scotland_bands"], DATA_RAW / "scotland_bands_2026-27.xlsx", force)

    # ASHE ships as a zip of ~22 workbooks; keep the one we need.
    ashe_zip = DATA_RAW / "ashe_table8_2025.zip"
    fetch(SOURCES["ashe_earnings"], ashe_zip, force)
    target = DATA_RAW / "ashe_annual_pay_2025.xlsx"
    if force or not target.exists():
        with zipfile.ZipFile(ashe_zip) as z:
            with z.open(ASHE_ZIP_MEMBER) as src, open(target, "wb") as out:
                out.write(src.read())
        print(f"  unzip {target.name} ({target.stat().st_size:,} bytes)")

    # ONS LAD boundaries + attributes via the ArcGIS REST API.
    base = SOURCES["lad_boundaries"]
    fetch(base + "?where=1%3D1&outFields=LAD24CD,LAD24NM,LONG,LAT"
               "&returnGeometry=false&f=json&resultRecordCount=2000",
          DATA_RAW / "lad_attributes.json", force)
    fetch(base + "?where=1%3D1&outFields=LAD24CD,LAD24NM"
               "&returnGeometry=true&f=geojson&outSR=4326&resultRecordCount=2000",
          DATA_RAW / "lad_boundaries.geojson", force)

    print("done.")


if __name__ == "__main__":
    main(force="--force" in sys.argv)
