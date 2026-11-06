"""Join council tax to boundaries and earnings, then derive affordability."""

import json
import sys
import warnings
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import DATA_PROC, DATA_RAW, NATION_BY_PREFIX, ONS_RECODE, norm_name  # noqa: E402

warnings.filterwarnings("ignore")

BAND_COLUMNS: list[str] = [
    "band_a",
    "band_b",
    "band_c",
    "band_d",
    "band_e",
    "band_f",
    "band_g",
    "band_h",
]

FULL_COLUMNS: list[str] = [
    "nation",
    "authority",
    "LAD24CD",
    "LONG",
    "LAT",
    *BAND_COLUMNS,
    "median",
    "mean",
    "band_d_pct_pay",
    "band_h_pct_pay",
    "mult_e",
    "mult_h",
]


def load_boundaries() -> pd.DataFrame:
    """Load ONS local authority attributes with nation and recode applied.

    Returns:
        One row per local authority with its code, name, centroid and nation.
        A ``join_code`` column carries the ONS recode so statistics files using
        the newer codes still match.
    """
    payload = json.loads((DATA_RAW / "lad_attributes.json").read_text())
    frame = pd.DataFrame([feature["attributes"] for feature in payload["features"]])
    frame["nation"] = frame.LAD24CD.str[0].map(NATION_BY_PREFIX)
    frame["join_code"] = frame.LAD24CD.replace(ONS_RECODE)
    return frame


def build_geo_table() -> pd.DataFrame:
    """Join the long band table to ONS codes and centroids.

    Returns:
        One row per council with a column per band.

    Raises:
        SystemExit: If any authority fails to match a boundary, which would
            indicate a naming or recode problem rather than missing data.
    """
    bands = pd.read_csv(DATA_PROC / "uk_bands_2026-27.csv")
    wide = bands.pivot_table(
        index=["nation", "authority"], columns="band", values="charge_gbp",
        aggfunc="first",
    ).reset_index()
    wide.columns = [
        f"band_{column.lower()}" if column in list("ABCDEFGHI") else column
        for column in wide.columns
    ]

    boundaries = load_boundaries()
    boundaries["key"] = boundaries.LAD24NM.map(norm_name)
    wide["key"] = wide.authority.map(norm_name)

    merged = wide.merge(
        boundaries[
            ["LAD24CD", "LAD24NM", "LONG", "LAT", "nation", "key", "join_code"]
        ],
        on=["key", "nation"],
        how="left",
    )

    unmatched = merged[merged.LAD24CD.isna()]
    if len(unmatched):
        raise SystemExit(
            "Unmatched authorities after boundary join:\n"
            + unmatched[["nation", "authority"]].to_string(index=False)
        )
    return merged


def add_affordability(geo: pd.DataFrame) -> pd.DataFrame:
    """Attach median pay and derive affordability and multiplier columns.

    Councils without an ASHE estimate are reported and then dropped, because
    imputing earnings would invent data. Their council tax still appears in the
    band outputs.

    Args:
        geo: Output of :func:`build_geo_table`.

    Returns:
        The frame restricted to councils with earnings, with ``band_d_pct_pay``,
        ``band_h_pct_pay``, ``mult_e`` and ``mult_h`` added.
    """
    ashe = pd.read_csv(DATA_PROC / "ashe_earnings_2025.csv")
    merged = geo.merge(
        ashe[["code", "median", "mean"]],
        left_on="join_code",
        right_on="code",
        how="left",
    )

    missing = merged[merged["median"].isna()]
    if len(missing):
        print("  no earnings (ONS suppressed or absent):")
        for _, row in missing.iterrows():
            print(f"    {row.authority} ({row.nation})")

    merged = merged[merged["median"].notna()].copy()
    merged["band_d_pct_pay"] = (merged.band_d / merged["median"] * 100).round(2)
    merged["band_h_pct_pay"] = (merged.band_h / merged["median"] * 100).round(2)
    merged["mult_e"] = (merged.band_e / merged.band_d).round(4)
    merged["mult_h"] = (merged.band_h / merged.band_d).round(4)
    return merged


def main() -> None:
    """Join boundaries and earnings, then write the full and presentation tables."""
    print("Joining boundaries and earnings")

    geo = build_geo_table()
    matched = int(geo.LAD24CD.notna().sum())
    print(f"  boundary join: {matched}/{len(geo)} matched")

    affordable = add_affordability(geo)
    print(f"  affordability: {len(affordable)} councils with earnings")

    affordable[FULL_COLUMNS].sort_values(["nation", "authority"]).to_csv(
        DATA_PROC / "uk_council_tax_full.csv", index=False
    )
    print(f"  uk_council_tax_full.csv       {len(affordable):,} rows")

    presentation = affordable[FULL_COLUMNS].drop(columns=["LONG", "LAT"]).copy()
    presentation = presentation.rename(
        columns={"LAD24CD": "ons_code", "median": "median_pay"}
    )
    presentation.sort_values(["nation", "authority"]).round(2).to_csv(
        DATA_PROC / "table_export.csv", index=False
    )
    print(f"  table_export.csv              {len(presentation):,} rows")


if __name__ == "__main__":
    main()
