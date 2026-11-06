"""Render the static figures (PNG) from the processed data."""
import json
import sys
import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.colors as mcolors  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.collections import PatchCollection  # noqa: E402
from matplotlib.patches import Patch, Polygon as MplPoly  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import BANDS, DATA_PROC, DATA_RAW, OUT_FIG  # noqa: E402

warnings.filterwarnings("ignore")

NATION_COLOUR = {"England": "#2d63a0", "Wales": "#b03434", "Scotland": "#1f6b3c"}


def load_geo():
    return json.loads((DATA_RAW / "lad_boundaries.geojson").read_text())


def rings(geom):
    if geom["type"] == "Polygon":
        return [geom["coordinates"][0]]
    return [p[0] for p in geom["coordinates"]]


def attach_values(geo, df, fields):
    """Attach per-council fields to the boundary features by ONS code."""
    lut = {r.LAD24CD: r for _, r in df.iterrows()}
    for f in geo["features"]:
        r = lut.get(f["properties"]["LAD24CD"])
        for k in fields:
            f["properties"][k] = (None if r is None or pd.isna(r[k]) else float(r[k]))
    return geo


def draw_choropleth(ax, geo, field, cmap, vmin, vmax, title):
    patches, colours = [], []
    for f in geo["features"]:
        v = f["properties"].get(field)
        for ring in rings(f["geometry"]):
            patches.append(MplPoly(ring, closed=True))
            colours.append("#e8e8e8" if v is None
                           else cmap((v - vmin) / (vmax - vmin) if vmax > vmin else 0.5))
    ax.add_collection(PatchCollection(patches, facecolor=colours, edgecolor="white",
                                      linewidth=0.25, antialiased=True))
    ax.set_xlim(-8.7, 2.1)
    ax.set_ylim(49.8, 61.0)
    ax.set_aspect(1.6)
    ax.axis("off")
    ax.set_title(title, fontsize=13, fontweight="bold", loc="left", pad=8)


# ------------------------------------------------------------------ figure 1
def fig_band_levels(geo, df):
    fig, axes = plt.subplots(1, 3, figsize=(17, 8.2), facecolor="white")
    specs = [
        ("band_d", "Blues", "Band D council tax, 2026-27 (£)", "£ per year (Band D)"),
        ("band_a", "Reds", "Band A council tax, 2026-27 (£)", "£ per year (Band A)"),
    ]
    for ax, (field, cmapname, title, cblabel) in zip(axes[:2], specs):
        vals = [f["properties"][field] for f in geo["features"]
                if f["properties"].get(field) is not None]
        cmap = plt.get_cmap(cmapname)
        draw_choropleth(ax, geo, field, cmap, min(vals), max(vals), title)
        sm = plt.cm.ScalarMappable(cmap=cmap, norm=mcolors.Normalize(min(vals), max(vals)))
        cb = fig.colorbar(sm, ax=ax, orientation="horizontal", fraction=0.04, pad=0.02)
        cb.set_label(cblabel, fontsize=9)

    # Band H multiplier: categorical, because it is binary
    ax = axes[2]
    patches, colours = [], []
    for f in geo["features"]:
        v = f["properties"].get("mult_h")
        for ring in rings(f["geometry"]):
            patches.append(MplPoly(ring, closed=True))
            if v is None:
                colours.append("#e8e8e8")
            elif abs(v - 2.45) < 0.01:
                colours.append("#a30000")
            else:
                colours.append("#cfe3d4")
    ax.add_collection(PatchCollection(patches, facecolor=colours, edgecolor="white",
                                      linewidth=0.25, antialiased=True))
    ax.set_xlim(-8.7, 2.1)
    ax.set_ylim(49.8, 61.0)
    ax.set_aspect(1.6)
    ax.axis("off")
    ax.set_title("Band H as a multiple of Band D", fontsize=13, fontweight="bold",
                 loc="left", pad=8)
    ax.legend(handles=[
        Patch(facecolor="#cfe3d4", edgecolor="#999", label="2.000×  England & Wales"),
        Patch(facecolor="#a30000", edgecolor="#999", label="2.450×  Scotland (from Apr 2017)"),
        Patch(facecolor="#e8e8e8", edgecolor="#999", label="no data (N. Ireland)"),
    ], loc="lower left", fontsize=8.5, frameon=True,
        title="Band H multiplier", title_fontsize=8.5)

    fig.suptitle("Council Tax Comparison Across the UK", fontsize=16,
                 fontweight="bold", x=0.02, ha="left", y=0.985)
    fig.text(0.02, 0.945,
             "Band A and Band D levels are directly comparable across nations. "
             "Band H burden is binary: Scotland raised its E–H multipliers on "
             "1 April 2017 (SSI 2016/368).",
             fontsize=9.5, color="#555", ha="left")
    plt.tight_layout(rect=[0, 0, 1, 0.93])
    out = OUT_FIG / "band_levels.png"
    plt.savefig(out, dpi=155, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    print(f"  {out.name}")


# ------------------------------------------------------------------ figure 2
def fig_affordability(geo, df):
    fig = plt.figure(figsize=(19, 9.6), facecolor="white")
    gs = fig.add_gridspec(1, 3, width_ratios=[1, 1, 1.15], wspace=0.06)

    # choropleth
    ax1 = fig.add_subplot(gs[0, 0])
    vals = [f["properties"]["pct_pay"] for f in geo["features"]
            if f["properties"].get("pct_pay") is not None]
    cmap = plt.get_cmap("RdYlBu_r")
    draw_choropleth(ax1, geo, "pct_pay", cmap, min(vals), max(vals),
                    "Band D as % of median annual pay")
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=mcolors.Normalize(min(vals), max(vals)))
    cb = fig.colorbar(sm, ax=ax1, orientation="horizontal", fraction=0.045, pad=0.02)
    cb.set_label("% of median gross annual pay", fontsize=9)

    # scatter
    ax2 = fig.add_subplot(gs[0, 1])
    for nat, g in df.groupby("nation"):
        ax2.scatter(g["median"] / 1000, g.band_d, s=26, alpha=.72,
                    color=NATION_COLOUR[nat], label=nat,
                    edgecolor="white", linewidth=.4)
    xs = np.linspace(24, 51, 100)
    for pct, ls in [(4, ":"), (6, "--"), (8, "-."), (10, "-")]:
        ax2.plot(xs, xs * 1000 * pct / 100, color="#999", lw=.9, ls=ls, zorder=0)
        ax2.annotate(f"{pct}%", (xs[-1], xs[-1] * 1000 * pct / 100), fontsize=7.5,
                     color="#777", va="center", ha="left")
    ax2.set_xlabel("Median gross annual pay (£000s)", fontsize=9.5)
    ax2.set_ylabel("Band D council tax (£)", fontsize=9.5)
    ax2.set_title("The bill vs the pay packet", fontsize=13, fontweight="bold",
                  loc="left", pad=8)
    ax2.legend(fontsize=8.5, frameon=True, loc="upper left")
    ax2.grid(alpha=.22, lw=.6)
    ax2.tick_params(labelsize=8.5)
    ax2.set_xlim(24, 53)

    # ranked bars
    ax3 = fig.add_subplot(gs[0, 2])
    sel = pd.concat([df.nlargest(14, "band_d_pct_pay"),
                     df.nsmallest(8, "band_d_pct_pay")]).sort_values("band_d_pct_pay")
    y = np.arange(len(sel))
    ax3.barh(y, sel["band_d_pct_pay"],
             color=[NATION_COLOUR[n] for n in sel.nation], height=.72, edgecolor="white")
    ax3.set_yticks(y)
    ax3.set_yticklabels(sel.authority, fontsize=8.2)
    ax3.set_xlabel("Band D as % of median annual pay", fontsize=9.5)
    ax3.set_title("Least and most affordable councils", fontsize=13,
                  fontweight="bold", loc="left", pad=8)
    ax3.grid(axis="x", alpha=.22, lw=.6)
    ax3.tick_params(axis="x", labelsize=8.5)
    mean = df["band_d_pct_pay"].mean()
    ax3.axvline(mean, color="#555", ls="--", lw=1)
    ax3.annotate(f"UK mean {mean:.1f}%", (mean, len(sel) - 0.2),
                 fontsize=7.8, color="#555", ha="center")
    for i, v in enumerate(sel["band_d_pct_pay"]):
        ax3.text(v + 0.08, i, f"{v:.1f}%", va="center", fontsize=7.4, color="#333")
    ax3.set_xlim(0, 11.6)
    ax3.legend(handles=[Patch(color=NATION_COLOUR[k], label=k)
                        for k in NATION_COLOUR],
               fontsize=8, loc="lower right", frameon=True)

    fig.suptitle("Council Tax Affordability — the Band D bill against local earnings",
                 fontsize=16, fontweight="bold", x=0.015, ha="left", y=0.985)
    fig.text(0.015, 0.945,
             "Band D council tax 2026-27 ÷ median gross annual pay by place of "
             "residence, ASHE 2025. 348 of 350 councils matched.",
             fontsize=9.3, color="#555", ha="left")
    plt.tight_layout(rect=[0, 0, 1, 0.935])
    out = OUT_FIG / "affordability.png"
    plt.savefig(out, dpi=150, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    print(f"  {out.name}")


# ------------------------------------------------------------------ figure 3
def fig_multipliers(df):
    nat = pd.read_csv(DATA_PROC / "nation_multipliers.csv", index_col=0)
    nat = nat.reindex(BANDS)

    fig = plt.figure(figsize=(15.5, 8.6), facecolor="white")
    gs = fig.add_gridspec(1, 2, width_ratios=[1.15, 1], wspace=0.20)

    ax = fig.add_subplot(gs[0, 0])
    x = np.arange(len(BANDS))
    for nation in ["England", "Wales", "Scotland"]:
        y = [nat.loc[b, nation] if pd.notna(nat.loc[b, nation]) else np.nan
             for b in BANDS]
        ax.plot(x, y, "-o", color=NATION_COLOUR[nation], lw=2.4, ms=7.5,
                label=nation, markeredgecolor="white", markeredgewidth=1.2, zorder=3)
    ax.axvspan(3.6, 7.4, color="#a30000", alpha=0.055, zorder=0)
    ax.text(5.5, 0.72, "Scotland diverges\nfrom E upward", fontsize=9.5,
            color="#a30000", ha="center", va="bottom", fontweight="bold")
    eng, sco = nat.loc["H", "England"], nat.loc["H", "Scotland"]
    ax.annotate("", xy=(7, sco), xytext=(7, eng),
                arrowprops=dict(arrowstyle="<->", color="#a30000", lw=1.6))
    ax.text(7.13, (eng + sco) / 2, "+22.5%", fontsize=9.5, color="#a30000",
            fontweight="bold", va="center")
    ax.set_xticks(x)
    ax.set_xticklabels(BANDS, fontsize=11)
    ax.set_xlabel("Council tax band", fontsize=10.5)
    ax.set_ylabel("Multiplier (charge ÷ Band D)", fontsize=10.5)
    ax.set_title("The band ladder by nation, 2026-27", fontsize=13.5,
                 fontweight="bold", loc="left", pad=10)
    ax.grid(alpha=.22, lw=.7)
    ax.legend(fontsize=9.5, frameon=True, loc="upper left")
    ax.tick_params(labelsize=9.5)
    ax.set_xlim(-0.4, 8.6)
    ax.set_ylim(0.55, 2.62)
    ax.axhline(1.0, color="#999", lw=.8, ls=":", zorder=1)
    ax.text(-0.32, 1.02, "Band D = 1.0", fontsize=8, color="#888")

    ax2 = fig.add_subplot(gs[0, 1])
    ax2.axis("off")
    ax2.set_xlim(0, 1)
    ax2.set_ylim(0, 1)
    ax2.text(0, 1.0, "Multiplier by band", fontsize=13.5, fontweight="bold", va="top")
    ax2.text(0, 0.945,
             "Identical for every council within a nation — a national constant, "
             "not a local choice.", fontsize=9, color="#666", va="top")

    xs = [0.0, 0.20, 0.42, 0.62, 0.83]
    y = 0.875
    ax2.add_patch(plt.Rectangle((0, y - 0.028), 1.0, 0.056, color="#1a1a1a", zorder=0))
    for c, xp in zip(["Band", "England", "Wales", "Scotland", "Scot vs Eng"], xs):
        ax2.text(xp, y, c, fontsize=9, fontweight="bold", color="#fff", va="center")

    y -= 0.062
    for b in BANDS:
        vals = [nat.loc[b, "England"], nat.loc[b, "Wales"], nat.loc[b, "Scotland"]]
        diff = nat.loc[b, "Scot_vs_Eng_%"]
        hl = pd.notna(diff) and abs(diff) > 0.05
        if hl:
            ax2.add_patch(plt.Rectangle((0, y - 0.026), 1.0, 0.052,
                                        color="#fff4e5", zorder=0))
        ax2.text(xs[0], y, b, fontsize=9.5, fontweight="bold", va="center")
        for i, v in enumerate(vals):
            ax2.text(xs[i + 1], y, "—" if pd.isna(v) else f"{v:.4f}",
                     fontsize=9.5, va="center",
                     color="#a30000" if (i == 2 and hl) else "#222",
                     fontweight="bold" if (i == 2 and hl) else "normal")
        ax2.text(xs[4], y, "—" if pd.isna(diff) else f"+{diff:.1f}%",
                 fontsize=9.5, va="center",
                 color="#a30000" if hl else "#999",
                 fontweight="bold" if hl else "normal")
        y -= 0.058

    ax2.text(0, y - 0.02,
             "England & Wales: LGFA 1992 s.5 (Wales adds Band I at 21/9 since the "
             "2003 revaluation).\n"
             "Scotland: LGFA 1992 s.74, substituted by SSI 2016/368 from 1 April 2017.",
             fontsize=8.2, color="#666", va="top", linespacing=1.55)

    fig.suptitle("Council Tax Comparison Across the UK — how the bands align by nation",
                 fontsize=16, fontweight="bold", x=0.012, ha="left", y=0.985)
    fig.text(0.012, 0.945,
             "Multipliers computed from published 2026-27 charges (charge ÷ Band D) "
             "for all 350 councils, then aggregated. A–D are identical in all three "
             "nations; Scotland's E–H are steeper.",
             fontsize=9.3, color="#555", ha="left")
    plt.tight_layout(rect=[0, 0, 1, 0.925])
    out = OUT_FIG / "multipliers.png"
    plt.savefig(out, dpi=155, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    print(f"  {out.name}")


def main():
    print("Rendering figures ->", OUT_FIG)
    df = pd.read_csv(DATA_PROC / "uk_council_tax_full.csv")
    geo = load_geo()
    attach_values(geo, df, ["band_a", "band_d", "band_h", "mult_h",
                            "band_d_pct_pay", "median"])

    # rename for the affordability renderer
    for f in geo["features"]:
        p = f["properties"]
        p["pct_pay"] = p.pop("band_d_pct_pay", None)

    fig_band_levels(geo, df)
    fig_affordability(geo, df)
    fig_multipliers(df)


if __name__ == "__main__":
    main()
