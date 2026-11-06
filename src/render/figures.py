"""Render the static figures from the processed data."""

import json
import sys
import warnings
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.colors as mcolors  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.axes import Axes  # noqa: E402
from matplotlib.collections import PatchCollection  # noqa: E402
from matplotlib.patches import Patch, Polygon as MplPoly  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import BANDS, DATA_PROC, DATA_RAW, OUT_FIG  # noqa: E402

warnings.filterwarnings("ignore")

NATION_COLOUR: dict[str, str] = {
    "England": "#2d63a0",
    "Wales": "#b03434",
    "Scotland": "#1f6b3c",
}

NO_DATA_COLOUR: str = "#e8e8e8"
SCOTLAND_HIGHLIGHT: str = "#a30000"
STANDARD_LADDER_COLOUR: str = "#cfe3d4"

# Geographic extent of the boundary collection, in degrees.
MAP_XLIM: tuple[float, float] = (-8.7, 2.1)
MAP_YLIM: tuple[float, float] = (49.8, 61.0)
MAP_ASPECT: float = 1.6

# The Scottish Band H multiplier from 2017-18 onward.
SCOTLAND_BAND_H: float = 2.45


def load_geo() -> dict[str, Any]:
    """Load the raw ONS boundary collection.

    Returns:
        The GeoJSON FeatureCollection as a dictionary.
    """
    return json.loads((DATA_RAW / "lad_boundaries.geojson").read_text())


def rings(geometry: dict[str, Any]) -> list[list[list[float]]]:
    """Return the outer rings of a GeoJSON geometry.

    Args:
        geometry: A GeoJSON Polygon or MultiPolygon geometry.

    Returns:
        One coordinate ring per polygon.
    """
    if geometry["type"] == "Polygon":
        return [geometry["coordinates"][0]]
    return [polygon[0] for polygon in geometry["coordinates"]]


def attach_values(
    geo: dict[str, Any], frame: pd.DataFrame, fields: list[str]
) -> dict[str, Any]:
    """Attach per-council values to boundary features, keyed on the ONS code.

    Args:
        geo: The boundary FeatureCollection, modified in place.
        frame: Processed council data indexed by an ``LAD24CD`` column.
        fields: Column names to copy onto each feature's properties.

    Returns:
        The same collection, with the requested fields attached.
    """
    lookup = {row.LAD24CD: row for _, row in frame.iterrows()}
    for feature in geo["features"]:
        row = lookup.get(feature["properties"]["LAD24CD"])
        for field in fields:
            if row is None or pd.isna(row[field]):
                feature["properties"][field] = None
            else:
                feature["properties"][field] = float(row[field])
    return geo


def draw_choropleth(
    axes: Axes,
    geo: dict[str, Any],
    field: str,
    colour_map: Any,
    value_min: float,
    value_max: float,
    title: str,
) -> None:
    """Draw a filled map of one measure onto an axis.

    Args:
        axes: The axis to draw on.
        geo: The boundary FeatureCollection carrying the measure.
        field: Property name holding the value to colour by.
        colour_map: A matplotlib colour map.
        value_min: Value mapped to the bottom of the colour scale.
        value_max: Value mapped to the top of the colour scale.
        title: Axis title.
    """
    patches: list[MplPoly] = []
    colours: list[str] = []
    span = value_max - value_min

    for feature in geo["features"]:
        value = feature["properties"].get(field)
        for ring in rings(feature["geometry"]):
            patches.append(MplPoly(ring, closed=True))
            if value is None:
                colours.append(NO_DATA_COLOUR)
            else:
                position = (value - value_min) / span if span > 0 else 0.5
                colours.append(colour_map(position))

    axes.add_collection(
        PatchCollection(
            patches,
            facecolor=colours,
            edgecolor="white",
            linewidth=0.25,
            antialiased=True,
        )
    )
    axes.set_xlim(*MAP_XLIM)
    axes.set_ylim(*MAP_YLIM)
    axes.set_aspect(MAP_ASPECT)
    axes.axis("off")
    axes.set_title(title, fontsize=13, fontweight="bold", loc="left", pad=8)


def fig_band_levels(geo: dict[str, Any]) -> None:
    """Render the three-panel band level and multiplier map.

    Args:
        geo: The boundary FeatureCollection with band values attached.
    """
    figure, axes = plt.subplots(1, 3, figsize=(17, 8.2), facecolor="white")

    panels = [
        ("band_d", "Blues", "Band D council tax, 2026-27 (£)", "£ per year (Band D)"),
        ("band_a", "Reds", "Band A council tax, 2026-27 (£)", "£ per year (Band A)"),
    ]
    for axis, (field, map_name, title, colourbar_label) in zip(axes[:2], panels):
        values = [
            feature["properties"][field]
            for feature in geo["features"]
            if feature["properties"].get(field) is not None
        ]
        colour_map = plt.get_cmap(map_name)
        draw_choropleth(
            axis, geo, field, colour_map, min(values), max(values), title
        )
        scalar = plt.cm.ScalarMappable(
            cmap=colour_map, norm=mcolors.Normalize(min(values), max(values))
        )
        colourbar = figure.colorbar(
            scalar, ax=axis, orientation="horizontal", fraction=0.04, pad=0.02
        )
        colourbar.set_label(colourbar_label, fontsize=9)

    # The Band H multiplier is binary, so a categorical fill is honest where a
    # gradient would imply variation that does not exist.
    axis = axes[2]
    patches: list[MplPoly] = []
    colours: list[str] = []
    for feature in geo["features"]:
        value = feature["properties"].get("mult_h")
        for ring in rings(feature["geometry"]):
            patches.append(MplPoly(ring, closed=True))
            if value is None:
                colours.append(NO_DATA_COLOUR)
            elif abs(value - SCOTLAND_BAND_H) < 0.01:
                colours.append(SCOTLAND_HIGHLIGHT)
            else:
                colours.append(STANDARD_LADDER_COLOUR)

    axis.add_collection(
        PatchCollection(
            patches,
            facecolor=colours,
            edgecolor="white",
            linewidth=0.25,
            antialiased=True,
        )
    )
    axis.set_xlim(*MAP_XLIM)
    axis.set_ylim(*MAP_YLIM)
    axis.set_aspect(MAP_ASPECT)
    axis.axis("off")
    axis.set_title(
        "Band H as a multiple of Band D", fontsize=13, fontweight="bold",
        loc="left", pad=8,
    )
    axis.legend(
        handles=[
            Patch(
                facecolor=STANDARD_LADDER_COLOUR,
                edgecolor="#999",
                label="2.000×  England and Wales",
            ),
            Patch(
                facecolor=SCOTLAND_HIGHLIGHT,
                edgecolor="#999",
                label="2.450×  Scotland (from April 2017)",
            ),
            Patch(
                facecolor=NO_DATA_COLOUR,
                edgecolor="#999",
                label="no data (Northern Ireland)",
            ),
        ],
        loc="lower left",
        fontsize=8.5,
        frameon=True,
        title="Band H multiplier",
        title_fontsize=8.5,
    )

    figure.suptitle(
        "Council Tax Comparison Across the UK",
        fontsize=16,
        fontweight="bold",
        x=0.02,
        ha="left",
        y=0.985,
    )
    figure.text(
        0.02,
        0.945,
        "Band A and Band D levels are directly comparable across nations. "
        "Band H burden is binary: Scotland raised its E to H multipliers on "
        "1 April 2017 (SSI 2016/368).",
        fontsize=9.5,
        color="#555",
        ha="left",
    )
    plt.tight_layout(rect=[0, 0, 1, 0.93])

    output = OUT_FIG / "band_levels.png"
    plt.savefig(output, dpi=155, facecolor="white", bbox_inches="tight")
    plt.close(figure)
    print(f"  {output.name}")


def fig_affordability(geo: dict[str, Any], frame: pd.DataFrame) -> None:
    """Render the three-panel affordability figure.

    Args:
        geo: The boundary FeatureCollection with affordability attached.
        frame: Processed council data with earnings and derived ratios.
    """
    figure = plt.figure(figsize=(19, 9.6), facecolor="white")
    grid = figure.add_gridspec(1, 3, width_ratios=[1, 1, 1.15], wspace=0.06)

    axis_map = figure.add_subplot(grid[0, 0])
    values = [
        feature["properties"]["pct_pay"]
        for feature in geo["features"]
        if feature["properties"].get("pct_pay") is not None
    ]
    colour_map = plt.get_cmap("RdYlBu_r")
    draw_choropleth(
        axis_map,
        geo,
        "pct_pay",
        colour_map,
        min(values),
        max(values),
        "Band D as a percentage of median annual pay",
    )
    scalar = plt.cm.ScalarMappable(
        cmap=colour_map, norm=mcolors.Normalize(min(values), max(values))
    )
    colourbar = figure.colorbar(
        scalar, ax=axis_map, orientation="horizontal", fraction=0.045, pad=0.02
    )
    colourbar.set_label("Percentage of median gross annual pay", fontsize=9)

    axis_scatter = figure.add_subplot(grid[0, 1])
    for nation, group in frame.groupby("nation"):
        axis_scatter.scatter(
            group["median"] / 1000,
            group.band_d,
            s=26,
            alpha=0.72,
            color=NATION_COLOUR[nation],
            label=nation,
            edgecolor="white",
            linewidth=0.4,
        )

    pay_range = np.linspace(24, 51, 100)
    for percentage, style in [(4, ":"), (6, "--"), (8, "-."), (10, "-")]:
        axis_scatter.plot(
            pay_range,
            pay_range * 1000 * percentage / 100,
            color="#999",
            lw=0.9,
            ls=style,
            zorder=0,
        )
        axis_scatter.annotate(
            f"{percentage}%",
            (pay_range[-1], pay_range[-1] * 1000 * percentage / 100),
            fontsize=7.5,
            color="#777",
            va="center",
            ha="left",
        )

    axis_scatter.set_xlabel("Median gross annual pay (£000s)", fontsize=9.5)
    axis_scatter.set_ylabel("Band D council tax (£)", fontsize=9.5)
    axis_scatter.set_title(
        "The bill against the pay packet", fontsize=13, fontweight="bold",
        loc="left", pad=8,
    )
    axis_scatter.legend(fontsize=8.5, frameon=True, loc="upper left")
    axis_scatter.grid(alpha=0.22, lw=0.6)
    axis_scatter.tick_params(labelsize=8.5)
    axis_scatter.set_xlim(24, 53)

    axis_bars = figure.add_subplot(grid[0, 2])
    selected = pd.concat(
        [
            frame.nlargest(14, "band_d_pct_pay"),
            frame.nsmallest(8, "band_d_pct_pay"),
        ]
    ).sort_values("band_d_pct_pay")
    positions = np.arange(len(selected))

    axis_bars.barh(
        positions,
        selected["band_d_pct_pay"],
        color=[NATION_COLOUR[nation] for nation in selected.nation],
        height=0.72,
        edgecolor="white",
    )
    axis_bars.set_yticks(positions)
    axis_bars.set_yticklabels(selected.authority, fontsize=8.2)
    axis_bars.set_xlabel("Band D as a percentage of median annual pay", fontsize=9.5)
    axis_bars.set_title(
        "Least and most affordable councils", fontsize=13, fontweight="bold",
        loc="left", pad=8,
    )
    axis_bars.grid(axis="x", alpha=0.22, lw=0.6)
    axis_bars.tick_params(axis="x", labelsize=8.5)

    mean_share = frame["band_d_pct_pay"].mean()
    axis_bars.axvline(mean_share, color="#555", ls="--", lw=1)
    axis_bars.annotate(
        f"UK mean {mean_share:.1f}%",
        (mean_share, len(selected) - 0.2),
        fontsize=7.8,
        color="#555",
        ha="center",
    )
    for index, value in enumerate(selected["band_d_pct_pay"]):
        axis_bars.text(
            value + 0.08, index, f"{value:.1f}%", va="center", fontsize=7.4,
            color="#333",
        )
    axis_bars.set_xlim(0, 11.6)
    axis_bars.legend(
        handles=[
            Patch(color=NATION_COLOUR[nation], label=nation)
            for nation in NATION_COLOUR
        ],
        fontsize=8,
        loc="lower right",
        frameon=True,
    )

    figure.suptitle(
        "Council Tax Affordability: the Band D bill against local earnings",
        fontsize=16,
        fontweight="bold",
        x=0.015,
        ha="left",
        y=0.985,
    )
    figure.text(
        0.015,
        0.945,
        "Band D council tax 2026-27 divided by median gross annual pay by place "
        "of residence, ASHE 2025. 348 of 350 councils matched.",
        fontsize=9.3,
        color="#555",
        ha="left",
    )
    plt.tight_layout(rect=[0, 0, 1, 0.935])

    output = OUT_FIG / "affordability.png"
    plt.savefig(output, dpi=150, facecolor="white", bbox_inches="tight")
    plt.close(figure)
    print(f"  {output.name}")


def fig_multipliers() -> None:
    """Render the nation ladder chart and accompanying table."""
    multipliers = pd.read_csv(DATA_PROC / "nation_multipliers.csv", index_col=0)
    multipliers = multipliers.reindex(BANDS)

    figure = plt.figure(figsize=(15.5, 8.6), facecolor="white")
    grid = figure.add_gridspec(1, 2, width_ratios=[1.15, 1], wspace=0.20)

    axis = figure.add_subplot(grid[0, 0])
    positions = np.arange(len(BANDS))
    for nation in ["England", "Wales", "Scotland"]:
        values = [
            multipliers.loc[band, nation]
            if pd.notna(multipliers.loc[band, nation])
            else np.nan
            for band in BANDS
        ]
        axis.plot(
            positions,
            values,
            "-o",
            color=NATION_COLOUR[nation],
            lw=2.4,
            ms=7.5,
            label=nation,
            markeredgecolor="white",
            markeredgewidth=1.2,
            zorder=3,
        )

    axis.axvspan(3.6, 7.4, color=SCOTLAND_HIGHLIGHT, alpha=0.055, zorder=0)
    axis.text(
        5.5,
        0.72,
        "Scotland diverges\nfrom E upward",
        fontsize=9.5,
        color=SCOTLAND_HIGHLIGHT,
        ha="center",
        va="bottom",
        fontweight="bold",
    )

    england_h = multipliers.loc["H", "England"]
    scotland_h = multipliers.loc["H", "Scotland"]
    axis.annotate(
        "",
        xy=(7, scotland_h),
        xytext=(7, england_h),
        arrowprops=dict(arrowstyle="<->", color=SCOTLAND_HIGHLIGHT, lw=1.6),
    )
    axis.text(
        7.13,
        (england_h + scotland_h) / 2,
        "+22.5%",
        fontsize=9.5,
        color=SCOTLAND_HIGHLIGHT,
        fontweight="bold",
        va="center",
    )

    axis.set_xticks(positions)
    axis.set_xticklabels(BANDS, fontsize=11)
    axis.set_xlabel("Council tax band", fontsize=10.5)
    axis.set_ylabel("Multiplier (charge divided by Band D)", fontsize=10.5)
    axis.set_title(
        "The band ladder by nation, 2026-27", fontsize=13.5, fontweight="bold",
        loc="left", pad=10,
    )
    axis.grid(alpha=0.22, lw=0.7)
    axis.legend(fontsize=9.5, frameon=True, loc="upper left")
    axis.tick_params(labelsize=9.5)
    axis.set_xlim(-0.4, 8.6)
    axis.set_ylim(0.55, 2.62)
    axis.axhline(1.0, color="#999", lw=0.8, ls=":", zorder=1)
    axis.text(-0.32, 1.02, "Band D = 1.0", fontsize=8, color="#888")

    axis_table = figure.add_subplot(grid[0, 1])
    axis_table.axis("off")
    axis_table.set_xlim(0, 1)
    axis_table.set_ylim(0, 1)
    axis_table.text(
        0, 1.0, "Multiplier by band", fontsize=13.5, fontweight="bold", va="top"
    )
    axis_table.text(
        0,
        0.945,
        "Identical for every council within a nation, so this is a national "
        "constant rather than a local choice.",
        fontsize=9,
        color="#666",
        va="top",
    )

    column_x = [0.0, 0.20, 0.42, 0.62, 0.83]
    row_y = 0.875
    axis_table.add_patch(
        plt.Rectangle((0, row_y - 0.028), 1.0, 0.056, color="#1a1a1a", zorder=0)
    )
    for label, x_position in zip(
        ["Band", "England", "Wales", "Scotland", "Scotland vs England"], column_x
    ):
        axis_table.text(
            x_position, row_y, label, fontsize=9, fontweight="bold",
            color="#fff", va="center",
        )

    row_y -= 0.062
    for band in BANDS:
        values = [
            multipliers.loc[band, "England"],
            multipliers.loc[band, "Wales"],
            multipliers.loc[band, "Scotland"],
        ]
        difference = multipliers.loc[band, "Scot_vs_Eng_%"]
        highlighted = pd.notna(difference) and abs(difference) > 0.05
        if highlighted:
            axis_table.add_patch(
                plt.Rectangle(
                    (0, row_y - 0.026), 1.0, 0.052, color="#fff4e5", zorder=0
                )
            )
        axis_table.text(
            column_x[0], row_y, band, fontsize=9.5, fontweight="bold", va="center"
        )
        for index, value in enumerate(values):
            axis_table.text(
                column_x[index + 1],
                row_y,
                "—" if pd.isna(value) else f"{value:.4f}",
                fontsize=9.5,
                va="center",
                color=SCOTLAND_HIGHLIGHT if (index == 2 and highlighted) else "#222",
                fontweight="bold" if (index == 2 and highlighted) else "normal",
            )
        axis_table.text(
            column_x[4],
            row_y,
            "—" if pd.isna(difference) else f"+{difference:.1f}%",
            fontsize=9.5,
            va="center",
            color=SCOTLAND_HIGHLIGHT if highlighted else "#999",
            fontweight="bold" if highlighted else "normal",
        )
        row_y -= 0.058

    axis_table.text(
        0,
        row_y - 0.02,
        "England and Wales: LGFA 1992 s.5 (Wales adds Band I at 21/9 since the "
        "2003 revaluation).\n"
        "Scotland: LGFA 1992 s.74, substituted by SSI 2016/368 from 1 April 2017.",
        fontsize=8.2,
        color="#666",
        va="top",
        linespacing=1.55,
    )

    figure.suptitle(
        "Council Tax Comparison Across the UK: how the bands align by nation",
        fontsize=16,
        fontweight="bold",
        x=0.012,
        ha="left",
        y=0.985,
    )
    figure.text(
        0.012,
        0.945,
        "Multipliers computed from published 2026-27 charges (charge divided by "
        "Band D) for all 350 councils, then aggregated. A to D are identical in "
        "all three nations; Scotland's E to H are steeper.",
        fontsize=9.3,
        color="#555",
        ha="left",
    )
    plt.tight_layout(rect=[0, 0, 1, 0.925])

    output = OUT_FIG / "multipliers.png"
    plt.savefig(output, dpi=155, facecolor="white", bbox_inches="tight")
    plt.close(figure)
    print(f"  {output.name}")


def fig_revenue(geo: dict[str, Any], frame: pd.DataFrame) -> None:
    """Render the three-panel council taxbase and revenue figure.

    Panels: revenue per dwelling on a map, dwellings against Band D charge as a
    scatter sized by gross revenue, and a nation summary of the gap between the
    gross product and the budgeted tax base.

    Args:
        geo: The boundary FeatureCollection with revenue attached.
        frame: Processed council data with dwellings and revenue columns.
    """
    figure = plt.figure(figsize=(19, 9.6), facecolor="white")
    grid = figure.add_gridspec(1, 3, width_ratios=[1, 1, 1.15], wspace=0.06)

    # Panel 1: revenue per dwelling on the map.
    axis_map = figure.add_subplot(grid[0, 0])
    frame = frame.copy()
    frame["rev_per_dwelling"] = frame.revenue_gross / frame.dwellings
    values = frame.rev_per_dwelling.dropna().tolist()
    colour_map = plt.get_cmap("YlGnBu")
    draw_choropleth(
        axis_map,
        geo,
        "rev_per_dwelling",
        colour_map,
        min(values),
        max(values),
        "Average council tax per dwelling",
    )
    scalar = plt.cm.ScalarMappable(
        cmap=colour_map, norm=mcolors.Normalize(min(values), max(values))
    )
    colourbar = figure.colorbar(
        scalar, ax=axis_map, orientation="horizontal", fraction=0.045, pad=0.02
    )
    colourbar.set_label("Gross council tax per dwelling (£)", fontsize=9)

    # Panel 2: taxbase size against the Band D charge.
    axis_scatter = figure.add_subplot(grid[0, 1])
    for nation, group in frame.groupby("nation"):
        axis_scatter.scatter(
            group.dwellings / 1000,
            group.band_d,
            s=np.sqrt(group.revenue_gross / 1e6) * 3.2,
            alpha=0.62,
            color=NATION_COLOUR[nation],
            label=nation,
            edgecolor="white",
            linewidth=0.4,
        )
    axis_scatter.set_xscale("log")
    axis_scatter.set_xlabel("Dwellings in the area (000s, log scale)", fontsize=9.5)
    axis_scatter.set_ylabel("Band D council tax (£)", fontsize=9.5)
    axis_scatter.set_title(
        "Rate against base", fontsize=13, fontweight="bold", loc="left", pad=9
    )
    axis_scatter.text(
        0.5,
        1.005,
        "Bubble area is gross revenue. Small bases with high charges sit top left.",
        transform=axis_scatter.transAxes,
        fontsize=8.4,
        color="#666",
        ha="center",
        va="bottom",
    )
    axis_scatter.legend(frameon=False, fontsize=9, loc="lower right")
    axis_scatter.grid(alpha=0.18, linewidth=0.6)
    axis_scatter.set_axisbelow(True)

    # Panel 3: the nation summary.
    axis_table = figure.add_subplot(grid[0, 2])
    axis_table.axis("off")

    rows = []
    for nation in ["England", "Scotland", "Wales"]:
        group = frame[frame.nation == nation]
        rows.append([
            nation,
            f"{group.authority.nunique()}",
            f"{group.dwellings.sum() / 1e6:.2f}m",
            f"£{group.revenue_gross.sum() / 1e9:.1f}bn",
            f"£{group.revenue_tax_base.sum() / 1e9:.1f}bn",
            f"{group.tax_base_ratio.mean():.3f}",
        ])
    total = frame
    rows.append([
        "All",
        f"{total.authority.nunique()}",
        f"{total.dwellings.sum() / 1e6:.2f}m",
        f"£{total.revenue_gross.sum() / 1e9:.1f}bn",
        f"£{total.revenue_tax_base.sum() / 1e9:.1f}bn",
        f"{total.tax_base_ratio.mean():.3f}",
    ])

    table = axis_table.table(
        cellText=rows,
        colLabels=[
            "Nation", "Councils", "Dwellings", "Gross", "Tax base", "Ratio"
        ],
        cellLoc="right",
        loc="upper center",
        bbox=[0.0, 0.42, 1.0, 0.44],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(9.5)
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor("#e2e2e2")
        if row == 0:
            cell.set_text_props(fontweight="bold")
            cell.set_facecolor("#f4f4f4")
        if row == len(rows):
            cell.set_text_props(fontweight="bold")
            cell.set_facecolor("#fafafa")

    axis_table.text(
        0.0,
        0.33,
        "Gross is dwellings x charge before discounts. Tax base is the published\n"
        "Band D equivalent times the Band D charge, which is what a council\n"
        "actually budgets on. The ratio is the second over the first, so it\n"
        "measures how much discounts, premiums and exemptions are worth.",
        transform=axis_table.transAxes,
        fontsize=8.6,
        color="#555",
        va="top",
        linespacing=1.5,
    )
    axis_table.set_title(
        "What the taxbase is worth",
        fontsize=13,
        fontweight="bold",
        loc="left",
        pad=12,
    )

    figure.suptitle(
        "Council Tax Comparison Across the UK: dwellings and revenue",
        fontsize=16,
        fontweight="bold",
        x=0.012,
        ha="left",
        y=0.985,
    )
    figure.text(
        0.012,
        0.945,
        "Dwelling counts from each nation's Council Taxbase return. Revenue is "
        "derived here, not published. England and Scotland have eight bands; "
        "Wales has nine.",
        fontsize=9.3,
        color="#555",
        ha="left",
    )
    plt.tight_layout(rect=[0, 0, 1, 0.925])

    output = OUT_FIG / "revenue.png"
    plt.savefig(output, dpi=155, facecolor="white", bbox_inches="tight")
    plt.close(figure)
    print(f"  {output.name}")


def main() -> None:
    """Render every static figure."""
    print("Rendering figures ->", OUT_FIG)

    frame = pd.read_csv(DATA_PROC / "uk_council_tax_full.csv")
    geo = load_geo()
    attach_values(
        geo,
        frame,
        [
            "band_a",
            "band_d",
            "band_h",
            "mult_h",
            "band_d_pct_pay",
            "median",
            "dwellings",
            "revenue_gross",
            "revenue_tax_base",
            "tax_base_ratio",
        ],
    )

    # The affordability renderer expects a shorter property name.
    for feature in geo["features"]:
        properties = feature["properties"]
        properties["pct_pay"] = properties.pop("band_d_pct_pay", None)
        gross = properties.get("revenue_gross")
        dwellings = properties.get("dwellings")
        properties["rev_per_dwelling"] = (
            gross / dwellings if gross and dwellings else None
        )

    fig_band_levels(geo)
    fig_affordability(geo, frame)
    fig_multipliers()
    fig_revenue(geo, frame)


if __name__ == "__main__":
    main()
