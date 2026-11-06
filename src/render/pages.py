"""Build the interactive map page and the sortable data table page.

Both are self-contained single files. The GeoJSON and the row data are inlined
as JavaScript literals so they work from ``file://`` without a server, because a
``fetch`` of a sibling file is blocked by cross-origin policy.
"""

import json
import sys
import warnings
from pathlib import Path
from typing import Any

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import DATA_PROC, DATA_RAW, OUT_PAGES, norm_name  # noqa: E402

warnings.filterwarnings("ignore")

TEMPLATES = Path(__file__).resolve().parent / "templates"

# Coordinates are rounded to three decimal places, roughly 110 metres, which is
# ample for a national choropleth and keeps the inlined payload small.
COORDINATE_PRECISION: int = 3

TABLE_COLUMNS: list[str] = [
    "nation",
    "authority",
    "LAD24CD",
    "band_a",
    "band_b",
    "band_c",
    "band_d",
    "band_e",
    "band_f",
    "band_g",
    "band_h",
    "median",
    "band_d_pct_pay",
    "band_h_pct_pay",
    "mult_e",
    "mult_h",
    "dwellings",
    "revenue_gross",
    "revenue_tax_base",
    "tax_base_published",
]


def round_coordinates(value: Any) -> Any:
    """Recursively round a GeoJSON coordinate structure.

    Args:
        value: A coordinate pair, or a nested list of them.

    Returns:
        The same structure with every coordinate rounded.
    """
    if isinstance(value[0], (int, float)):
        return [round(value[0], COORDINATE_PRECISION),
                round(value[1], COORDINATE_PRECISION)]
    return [round_coordinates(item) for item in value]


def slim_geojson(bands: pd.DataFrame, affordable: pd.DataFrame) -> dict[str, Any]:
    """Build a boundary collection carrying per-council values.

    Band fields come from the full 350-council set and affordability fields from
    the 348-council set, because two councils have no earnings estimate. Merging
    both keeps the band maps complete while leaving affordability genuinely
    empty where there is no data.

    Args:
        bands: One row per council with a column per band and an ONS code.
        affordable: One row per council with earnings and derived ratios.

    Returns:
        A GeoJSON FeatureCollection with values attached to each feature.
    """
    geo = json.loads((DATA_RAW / "lad_boundaries.geojson").read_text())
    band_lookup = {row.LAD24CD: row for _, row in bands.iterrows()}
    afford_lookup = {row.LAD24CD: row for _, row in affordable.iterrows()}

    features: list[dict[str, Any]] = []
    for feature in geo["features"]:
        code = feature["properties"]["LAD24CD"]
        band_row = band_lookup.get(code)
        afford_row = afford_lookup.get(code)
        properties: dict[str, Any] = {
            "code": code,
            "name": feature["properties"]["LAD24NM"],
        }

        if band_row is not None:
            properties.update(
                {
                    "authority": band_row.authority,
                    "nation": band_row.nation,
                    "band_a": round(float(band_row.band_a), 2),
                    "band_d": round(float(band_row.band_d), 2),
                    "band_h": round(float(band_row.band_h), 2),
                    "band_h_ratio": round(
                        float(band_row.band_h) / float(band_row.band_d), 4
                    ),
                }
            )
        else:
            properties.update(
                {
                    "authority": None,
                    "nation": None,
                    "band_a": None,
                    "band_d": None,
                    "band_h": None,
                    "band_h_ratio": None,
                }
            )

        if afford_row is not None:
            properties.update(
                {
                    "median_pay": round(float(afford_row["median"]), 0),
                    "pct_income": round(float(afford_row.band_d_pct_pay), 2),
                    "dwellings": (
                        int(afford_row.dwellings)
                        if pd.notna(afford_row.dwellings) else None
                    ),
                    "revenue_gross": (
                        round(float(afford_row.revenue_gross), 0)
                        if pd.notna(afford_row.revenue_gross) else None
                    ),
                    "tax_base_published": (
                        round(float(afford_row.tax_base_published), 0)
                        if pd.notna(afford_row.tax_base_published) else None
                    ),
                    "rev_per_dwelling": (
                        round(
                            float(afford_row.revenue_gross)
                            / float(afford_row.dwellings),
                            0,
                        )
                        if pd.notna(afford_row.dwellings)
                        and pd.notna(afford_row.revenue_gross)
                        and float(afford_row.dwellings) > 0
                        else None
                    ),
                }
            )
        else:
            properties.update(
                {
                    "median_pay": None,
                    "pct_income": None,
                    "dwellings": None,
                    "revenue_gross": None,
                    "tax_base_published": None,
                    "rev_per_dwelling": None,
                }
            )

        geometry = feature["geometry"]
        geometry["coordinates"] = round_coordinates(geometry["coordinates"])
        features.append(
            {"type": "Feature", "properties": properties, "geometry": geometry}
        )

    return {"type": "FeatureCollection", "features": features}


def build_map(bands: pd.DataFrame, affordable: pd.DataFrame) -> None:
    """Write the interactive map page.

    Args:
        bands: One row per council with a column per band and an ONS code.
        affordable: One row per council with earnings and derived ratios.
    """
    geo = slim_geojson(bands, affordable)
    template = (TEMPLATES / "map.html").read_text()
    html = template.replace("__GEODATA__", json.dumps(geo, separators=(",", ":")))
    (OUT_PAGES / "map.html").write_text(html)

    with_bands = sum(
        1 for feature in geo["features"] if feature["properties"]["band_d"] is not None
    )
    with_affordability = sum(
        1
        for feature in geo["features"]
        if feature["properties"]["pct_income"] is not None
    )
    feature_count = len(geo["features"])
    print(
        f"  map.html     {feature_count} features, "
        f"{with_bands} with band data, {with_affordability} with affordability, "
        f"{round(len(html) / 1024)} KB"
    )


def build_table(affordable: pd.DataFrame) -> None:
    """Write the sortable data table page.

    Args:
        affordable: One row per council with earnings and derived ratios.
    """
    rows = affordable[TABLE_COLUMNS].copy()
    rows = rows.rename(columns={"LAD24CD": "ons_code", "median": "median_pay"})
    rows["rev_per_dwelling"] = (
        rows.revenue_gross / rows.dwellings.replace(0, pd.NA)
    ).round(0)
    rows["tax_base_published"] = rows.tax_base_published.round(0)
    rows = rows.sort_values(["nation", "authority"]).round(2)

    template = (TEMPLATES / "table.html").read_text()
    html = template.replace(
        "__ROWDATA__",
        json.dumps(rows.to_dict(orient="records"), separators=(",", ":")),
    )
    (OUT_PAGES / "table.html").write_text(html)
    print(f"  table.html   {len(rows)} rows, {round(len(html) / 1024)} KB")


def main() -> None:
    """Build both pages from the processed data."""
    print("Building pages ->", OUT_PAGES)

    affordable = pd.read_csv(DATA_PROC / "uk_council_tax_full.csv")

    # The full 350-council band table, before the earnings join dropped two.
    bands = pd.read_csv(DATA_PROC / "uk_bands_2026-27.csv")
    wide = bands.pivot_table(
        index=["nation", "authority"], columns="band", values="charge_gbp",
        aggfunc="first",
    ).reset_index()
    wide.columns = [
        f"band_{column.lower()}" if column in list("ABCDEFGHI") else column
        for column in wide.columns
    ]

    boundaries = json.loads((DATA_RAW / "lad_attributes.json").read_text())
    boundary_frame = pd.DataFrame(
        [feature["attributes"] for feature in boundaries["features"]]
    )
    boundary_frame["key"] = boundary_frame.LAD24NM.map(norm_name)
    boundary_frame["nation"] = boundary_frame.LAD24CD.str[0].map(
        {"E": "England", "W": "Wales", "S": "Scotland", "N": "Northern Ireland"}
    )
    wide["key"] = wide.authority.map(norm_name)
    wide = wide.merge(
        boundary_frame[["LAD24CD", "key", "nation"]],
        on=["key", "nation"],
        how="left",
    )

    build_map(wide, affordable)
    build_table(affordable)


if __name__ == "__main__":
    main()
