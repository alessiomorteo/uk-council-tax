"""Join council tax to boundaries and earnings, and derive affordability."""
import json
import sys
import warnings
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import DATA_PROC, DATA_RAW, ONS_RECODE  # noqa: E402
from parse import norm_name  # noqa: E402

warnings.filterwarnings("ignore")


def load_boundaries() -> pd.DataFrame:
    raw = json.loads((DATA_RAW / "lad_attributes.json").read_text())
    df = pd.DataFrame([f["attributes"] for f in raw["features"]])
    df["nation"] = df.LAD24CD.str[0].map(
        {"E": "England", "W": "Wales", "S": "Scotland", "N": "Northern Ireland"})
    df["join_code"] = df.LAD24CD.replace(ONS_RECODE)
    return df


def build_geo_table() -> pd.DataFrame:
    """Council tax joined to ONS codes and centroids."""
    bands = pd.read_csv(DATA_PROC / "uk_bands_2026-27.csv")
    wide = bands.pivot_table(index=["nation", "authority"], columns="band",
                             values="charge_gbp", aggfunc="first").reset_index()
    wide.columns = [f"band_{c.lower()}" if c in list("ABCDEFGHI") else c
                    for c in wide.columns]

    lad = load_boundaries()
    lad["key"] = lad.LAD24NM.map(norm_name)
    wide["key"] = wide.authority.map(norm_name)

    m = wide.merge(lad[["LAD24CD", "LAD24NM", "LONG", "LAT", "nation", "key", "join_code"]],
                   on=["key", "nation"], how="left")

    unmatched = m[m.LAD24CD.isna()]
    if len(unmatched):
        raise SystemExit(
            "Unmatched authorities after boundary join:\n"
            + unmatched[["nation", "authority"]].to_string(index=False))
    return m


def add_affordability(geo: pd.DataFrame) -> pd.DataFrame:
    ashe = pd.read_csv(DATA_PROC / "ashe_earnings_2025.csv")
    m = geo.merge(ashe[["code", "median", "mean"]],
                  left_on="join_code", right_on="code", how="left")

    missing = m[m["median"].isna()]
    if len(missing):
        print("  no earnings (ONS suppressed or absent):")
        for _, r in missing.iterrows():
            print(f"    {r.authority} ({r.nation})")

    m = m[m["median"].notna()].copy()
    m["band_d_pct_pay"] = (m.band_d / m["median"] * 100).round(2)
    m["band_h_pct_pay"] = (m.band_h / m["median"] * 100).round(2)
    m["mult_e"] = (m.band_e / m.band_d).round(4)
    m["mult_h"] = (m.band_h / m.band_d).round(4)
    return m


def main():
    print("Joining boundaries and earnings")

    geo = build_geo_table()
    print(f"  boundary join: {geo.LAD24CD.notna().sum()}/{len(geo)} matched")

    aff = add_affordability(geo)
    print(f"  affordability: {len(aff)} councils with earnings")

    cols = ["nation", "authority", "LAD24CD", "LONG", "LAT",
            "band_a", "band_b", "band_c", "band_d", "band_e",
            "band_f", "band_g", "band_h", "median", "mean",
            "band_d_pct_pay", "band_h_pct_pay", "mult_e", "mult_h"]
    aff[cols].sort_values(["nation", "authority"]).to_csv(
        DATA_PROC / "uk_council_tax_full.csv", index=False)
    print(f"  uk_council_tax_full.csv       {len(aff):,} rows")

    # presentation table
    tbl = aff[["nation", "authority", "LAD24CD", "band_a", "band_b", "band_c",
               "band_d", "band_e", "band_f", "band_g", "band_h",
               "median", "band_d_pct_pay", "band_h_pct_pay", "mult_e", "mult_h"]].copy()
    tbl = tbl.rename(columns={"LAD24CD": "ons_code", "median": "median_pay"})
    tbl.sort_values(["nation", "authority"]).round(2).to_csv(
        DATA_PROC / "table_export.csv", index=False)
    print(f"  table_export.csv              {len(tbl):,} rows")


if __name__ == "__main__":
    main()
