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
    "dwellings",
    "tax_base_published",
    "revenue_gross",
    "revenue_tax_base",
    "tax_base_ratio",
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


def add_taxbase(geo: pd.DataFrame) -> pd.DataFrame:
    """Attach dwelling counts and derive the council tax revenue per council.

    Revenue is ``dwellings x charge`` summed across bands. This is gross
    liability before discounts, so it is a ceiling rather than the collected
    figure. The published Band D equivalent tax base is attached alongside for
    comparison, and the ratio between the two shows how much a council's
    headline charge overstates its actual yield.

    England joins on ONS code; Wales and Scotland join on normalised name
    because their taxbase files carry no code.

    Args:
        geo: Output of :func:`build_geo_table`.

    Returns:
        The frame with ``dwellings``, ``tax_base_published``, ``revenue_gross``
        and ``tax_base_ratio`` added.
    """
    taxbase = pd.read_csv(DATA_PROC / "taxbase_long.csv")
    latest = {"England": "2025-26", "Wales": "2026-27", "Scotland": "2026-27"}
    taxbase = pd.concat(
        [
            group[group.year == latest[nation]]
            for nation, group in taxbase.groupby("nation")
        ],
        ignore_index=True,
    )

    bands = taxbase[taxbase.band != "Total"].copy()
    totals = taxbase[taxbase.band == "Total"].copy()

    # Dwellings per band, keyed by nation plus code or normalised name. Wales
    # and Scotland carry no ONS code in their taxbase files, so they key on the
    # normalised authority name. England needs the ONS recode applied because
    # Barnsley and Sheffield were renumbered.
    def _key(ons_code: object, authority: object) -> str:
        """Return the join key for one taxbase row."""
        if isinstance(ons_code, str) and ons_code.strip():
            return ONS_RECODE.get(ons_code.strip(), ons_code.strip())
        return norm_name(str(authority))

    bands["key"] = [
        _key(code, name) for code, name in zip(bands.ons_code, bands.authority)
    ]
    totals["key"] = [
        _key(code, name) for code, name in zip(totals.ons_code, totals.authority)
    ]

    dwellings = (
        bands.groupby(["nation", "key", "band"]).dwellings.sum().reset_index()
    )
    published = (
        totals.groupby(["nation", "key"]).tax_base.sum().reset_index()
        .rename(columns={"tax_base": "tax_base_published"})
    )

    geo = geo.copy()
    # England joins on ONS code with the recode applied, because Barnsley and
    # Sheffield were renumbered. Wales and Scotland join on normalised name
    # because their taxbase files carry no code at all.
    geo["key"] = [
        (
            ONS_RECODE.get(code.strip(), code.strip())
            if nation == "England" and isinstance(code, str) and code.strip()
            else norm_name(str(name))
        )
        for nation, code, name in zip(geo.nation, geo.LAD24CD, geo.authority)
    ]

    # Total dwellings per council.
    per_council = (
        dwellings.groupby(["nation", "key"]).dwellings.sum().reset_index()
        .rename(columns={"dwellings": "dwellings"})
    )
    geo = geo.merge(per_council, on=["nation", "key"], how="left")
    geo = geo.merge(published, on=["nation", "key"], how="left")

    # Gross revenue: sum of dwellings x charge across bands.
    charge_cols = {band: f"band_{band.lower()}" for band in "ABCDEFGHI"}
    revenue: dict[tuple[str, str], float] = {}
    for _, row in dwellings.iterrows():
        charge = geo.loc[
            (geo.nation == row.nation) & (geo.key == row.key),
            charge_cols.get(row.band, ""),
        ]
        if not len(charge) or charge_cols.get(row.band) not in geo.columns:
            continue
        value = charge.iloc[0]
        if pd.isna(value):
            continue
        revenue[(row.nation, row.key)] = (
            revenue.get((row.nation, row.key), 0.0) + row.dwellings * float(value)
        )

    geo["revenue_gross"] = [
        revenue.get((nation, key)) for nation, key in zip(geo.nation, geo.key)
    ]

    # Revenue implied by the published tax base: Band D equivalents times the
    # Band D charge. This is the figure the council actually budgets on, because
    # the tax base already nets off discounts, premiums and exemptions.
    geo["revenue_tax_base"] = (geo.tax_base_published * geo.band_d).round(0)

    # How much the gross product overstates the budgeted yield. Expect roughly
    # 0.85 to 0.95: discounts are worth 5 to 15 per cent.
    geo["tax_base_ratio"] = (
        geo.revenue_tax_base / geo.revenue_gross.replace(0, pd.NA)
    ).round(4)

    matched = int(geo.dwellings.notna().sum())
    print(f"  taxbase join: {matched}/{len(geo)} councils matched")
    return geo.drop(columns=["key"])


def main() -> None:
    """Join boundaries and earnings, then write the full and presentation tables."""
    print("Joining boundaries and earnings")

    geo = build_geo_table()
    matched = int(geo.LAD24CD.notna().sum())
    print(f"  boundary join: {matched}/{len(geo)} matched")

    affordable = add_affordability(geo)
    print(f"  affordability: {len(affordable)} councils with earnings")

    affordable = add_taxbase(affordable)

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
