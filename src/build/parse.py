"""Parse each raw source into tidy long-format CSVs in data/processed/.

Every parser returns columns: nation, authority, year, band, charge_gbp, source.
"""
import re
import sys
import warnings
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import (BANDS, DATA_PROC, DATA_RAW, NATION_BY_PREFIX,  # noqa: E402
                    ONS_RECODE, norm_name)

warnings.filterwarnings("ignore")

ODF_T = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
ODF_TX = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"


# ------------------------------------------------------------------ helpers
def read_ods_sheet(path: Path, sheet: str) -> list[list[str]]:
    """Read one ODS sheet as a list of rows.

    ODS stores runs of empty cells as a single cell with a large
    number-columns-repeated. Expanding those faithfully pads the header and
    breaks positional alignment, so cap the expansion.
    """
    root = ET.fromstring(zipfile.ZipFile(path).read("content.xml"))
    for table in root.iter(ODF_T + "table"):
        if table.get(ODF_T + "name") != sheet:
            continue
        rows = []
        for r in table.iter(ODF_T + "table-row"):
            cells = []
            for c in r.iter(ODF_T + "table-cell"):
                rep = int(c.get(ODF_T + "number-columns-repeated") or 1)
                txt = "".join(n.text or "" for n in c.iter(ODF_TX + "p"))
                cells.extend([txt] * (rep if rep <= 200 else 1))
            while cells and cells[-1] == "":
                cells.pop()
            rows.append(cells)
        return rows
    raise KeyError(f"sheet {sheet!r} not in {path.name}")


def tidy_year(h: str) -> str | None:
    m = re.match(r"(\d{4}) to (\d{4})", str(h).strip())
    return f"{m.group(1)}-{m.group(2)[2:]}" if m else None


# ------------------------------------------------------------------ England
def parse_england_bands(path: Path) -> pd.DataFrame:
    """MHCLG Tables 1-9, sheet Table_9 = area council tax by band, all authorities."""
    d = pd.read_excel(path, sheet_name="Table_9", engine="odf", header=None)
    body = d.iloc[3:].copy()
    body.columns = [str(c).strip() for c in d.iloc[2].tolist()]
    body = body[body["Authority"].notna()]

    out = []
    for _, r in body.iterrows():
        for b in "ABCDEFGH":
            col = f"Band {b}"
            if col not in body.columns or pd.isna(r[col]):
                continue
            out.append({
                "nation": "England",
                "authority": str(r["Authority"]).strip(),
                "ons_code": str(r["ONS Code"]).strip(),
                "year": "2026-27",
                "band": b,
                "charge_gbp": round(float(r[col]), 2),
                "source": "MHCLG Tables 1-9 (Table_9)",
            })
    return pd.DataFrame(out)


def parse_england_band_d(path: Path) -> pd.DataFrame:
    """Live table: Band D 1993-94 onward, incl/excl parish, and area total.

    The header carries a trailing 'Notes' label that the data rows omit; drop it
    or every year column shifts by one.
    """
    frames = []
    for sheet, measure in [("inc_PP", "band_d_incl_parish"),
                           ("exc_PP", "band_d_excl_parish"),
                           ("Area_CT", "band_d_area_total")]:
        rows = read_ods_sheet(path, sheet)
        hdr = rows[2]
        if hdr and str(hdr[-1]).strip().lower() == "notes":
            hdr = hdr[:-1]
        year_pos = [i for i, h in enumerate(hdr) if tidy_year(h)]
        years = [tidy_year(hdr[i]) for i in year_pos]
        first = year_pos[0]

        recs = []
        for r in rows[3:]:
            if not r or len(r) < 3:
                continue
            auth = r[2].strip() if len(r) > 2 else ""
            if not auth:
                continue
            for k, yr in enumerate(years):
                idx = first + k
                if idx >= len(r):
                    continue
                raw = r[idx].strip()
                try:
                    val = float(raw.replace(",", ""))
                except ValueError:
                    continue  # '[z]' / '[x]' sentinels
                recs.append({
                    "nation": "England",
                    "authority": auth,
                    "ons_code": r[1].strip() if len(r) > 1 else "",
                    "year": yr,
                    "band": "D",
                    "measure": measure,
                    "charge_gbp": val,
                    "source": "MHCLG Band D live table",
                })
        frames.append(pd.DataFrame(recs))
    return pd.concat(frames, ignore_index=True)


# ------------------------------------------------------------------ Wales
def parse_wales(path: Path) -> pd.DataFrame:
    d = pd.read_csv(path)
    d = d[d["Authority"] != "Total Unitary Authorities"]
    out = []
    for _, r in d.iterrows():
        try:
            v = float(r["Data values"])
        except (TypeError, ValueError):
            continue
        out.append({
            "nation": "Wales",
            "authority": str(r["Authority"]).strip(),
            "ons_code": "",
            "year": str(r["Year"]),
            "band": str(r["Band"]),
            "charge_gbp": round(v, 2),
            "source": "StatsWales API v2",
        })
    return pd.DataFrame(out)


# ------------------------------------------------------------------ Scotland
def parse_scotland(path: Path) -> pd.DataFrame:
    d = pd.read_excel(path, header=None)
    hdr_i = None
    for i in range(min(15, len(d))):
        vals = [str(x) for x in d.iloc[i, :10] if pd.notna(x)]
        if sum(1 for b in "ABCDEFGH" if f"Band {b}" in vals) >= 6:
            hdr_i = i
            break
    if hdr_i is None:
        raise ValueError("Scotland: could not locate the Band A-H header row")

    out = []
    for i in range(hdr_i + 1, len(d)):
        name = d.iloc[i, 0]
        if not isinstance(name, str):
            continue
        name = name.strip()
        if not name or name.lower().startswith(
                ("ratio", "scotland", "source", "valuation", "excludes")):
            continue
        try:
            vals = [float(d.iloc[i, j]) for j in range(1, 9)]
        except (TypeError, ValueError):
            continue
        if vals[3] <= 0:
            continue
        for b, v in zip("ABCDEFGH", vals):
            out.append({
                "nation": "Scotland",
                "authority": name,
                "ons_code": "",
                "year": "2026-27",
                "band": b,
                "charge_gbp": round(v, 2),
                "source": "Scottish Government CTAS",
            })
    return pd.DataFrame(out)


# ------------------------------------------------------------------ earnings
def parse_ashe(path: Path) -> pd.DataFrame:
    """ASHE Table 8.7a, sheet 'All' — median gross annual pay by LA of residence."""
    d = pd.read_excel(path, sheet_name="All", header=None)
    d = d.iloc[5:, [0, 1, 3, 5]].copy()
    d.columns = ["name", "code", "median", "mean"]
    d["code"] = d["code"].astype(str).str.replace("'", "", regex=False).str.strip()
    d = d[d["code"].str.match(r"^(E0[6-9]|S12|W06)\d{6}$")].copy()
    d["median"] = pd.to_numeric(d["median"], errors="coerce")
    d["mean"] = pd.to_numeric(d["mean"], errors="coerce")
    d["nation"] = d["code"].str[0].map(NATION_BY_PREFIX)
    return d[["nation", "name", "code", "median", "mean"]]


# ------------------------------------------------------------------ driver
def main():
    print("Parsing raw -> processed")

    eng = parse_england_bands(DATA_RAW / "england_tables_1-9_2026-27.ods")
    eng.to_csv(DATA_PROC / "england_bands_2026-27.csv", index=False)
    print(f"  england_bands_2026-27.csv      {len(eng):>6,} rows")

    engd = parse_england_band_d(DATA_RAW / "england_band_d_2026-27.ods")
    engd.to_csv(DATA_PROC / "england_band_d_1993-2027.csv", index=False)
    print(f"  england_band_d_1993-2027.csv   {len(engd):>6,} rows")

    wal = parse_wales(DATA_RAW / "wales_bands_1996-2027.csv")
    wal.to_csv(DATA_PROC / "wales_bands_1996-2027.csv", index=False)
    print(f"  wales_bands_1996-2027.csv      {len(wal):>6,} rows")

    sco = parse_scotland(DATA_RAW / "scotland_bands_2026-27.xlsx")
    sco.to_csv(DATA_PROC / "scotland_bands_2026-27.csv", index=False)
    print(f"  scotland_bands_2026-27.csv     {len(sco):>6,} rows")

    ashe = parse_ashe(DATA_RAW / "ashe_annual_pay_2025.xlsx")
    ashe.to_csv(DATA_PROC / "ashe_earnings_2025.csv", index=False)
    print(f"  ashe_earnings_2025.csv         {len(ashe):>6,} rows")

    # combined long table for the current year
    cur = pd.concat([eng, wal, sco], ignore_index=True)
    cur.to_csv(DATA_PROC / "uk_bands_2026-27.csv", index=False)
    print(f"  uk_bands_2026-27.csv           {len(cur):>6,} rows")


if __name__ == "__main__":
    main()
