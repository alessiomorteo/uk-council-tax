"""Build the interactive map page and the sortable data table page.

Both are self-contained single files: the GeoJSON and the row data are inlined
as JS literals so they work from file:// without a server (a fetch() of a
sibling file is blocked by CORS).
"""
import json
import sys
import warnings
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import DATA_PROC, DATA_RAW, OUT_PAGES, norm_name  # noqa: E402

warnings.filterwarnings("ignore")

TEMPLATES = Path(__file__).resolve().parent / "templates"


def slim_geojson(bands: pd.DataFrame, full: pd.DataFrame) -> dict:
    """Boundaries + per-council values, coordinates rounded to 3dp (~110 m).

    Band fields come from the full 350-council set; affordability fields come
    from the 348-council set (two councils are ONS-suppressed for earnings).
    Merging both keeps the band maps complete while leaving affordability grey
    where there is genuinely no data.
    """
    geo = json.loads((DATA_RAW / "lad_boundaries.geojson").read_text())
    band_lut = {r.LAD24CD: r for _, r in bands.iterrows()}
    aff_lut = {r.LAD24CD: r for _, r in full.iterrows()}

    def rnd(c):
        if isinstance(c[0], (int, float)):
            return [round(c[0], 3), round(c[1], 3)]
        return [rnd(x) for x in c]

    feats = []
    for f in geo["features"]:
        code = f["properties"]["LAD24CD"]
        b = band_lut.get(code)
        a = aff_lut.get(code)
        props = {"code": code, "name": f["properties"]["LAD24NM"]}

        if b is not None:
            props.update({
                "authority": b.authority,
                "nation": b.nation,
                "band_a": round(float(b.band_a), 2),
                "band_d": round(float(b.band_d), 2),
                "band_h": round(float(b.band_h), 2),
                "band_h_ratio": round(float(b.band_h) / float(b.band_d), 4),
            })
        else:
            props.update({"authority": None, "nation": None, "band_a": None,
                          "band_d": None, "band_h": None, "band_h_ratio": None})

        if a is not None:
            props.update({
                "median_pay": round(float(a["median"]), 0),
                "pct_income": round(float(a.band_d_pct_pay), 2),
            })
        else:
            props.update({"median_pay": None, "pct_income": None})

        g = f["geometry"]
        if g["type"] == "Polygon":
            g["coordinates"] = [[rnd(p) for p in ring] for ring in g["coordinates"]]
        else:
            g["coordinates"] = [[[rnd(p) for p in ring] for ring in poly]
                                for poly in g["coordinates"]]
        feats.append({"type": "Feature", "properties": props, "geometry": g})
    return {"type": "FeatureCollection", "features": feats}


def build_map(bands: pd.DataFrame, full: pd.DataFrame):
    geo = slim_geojson(bands, full)
    tpl = (TEMPLATES / "map.html").read_text()
    html = tpl.replace("__GEODATA__", json.dumps(geo, separators=(",", ":")))
    (OUT_PAGES / "map.html").write_text(html)

    n_band = sum(1 for f in geo["features"] if f["properties"]["band_d"] is not None)
    n_aff = sum(1 for f in geo["features"] if f["properties"]["pct_income"] is not None)
    print(f"  map.html     {len(geo['features'])} features · "
          f"{n_band} with band data · {n_aff} with affordability · "
          f"{round(len(html)/1024)} KB")


def build_table(full: pd.DataFrame):
    rows = full[["nation", "authority", "LAD24CD", "band_a", "band_b", "band_c",
                 "band_d", "band_e", "band_f", "band_g", "band_h",
                 "median", "band_d_pct_pay", "band_h_pct_pay",
                 "mult_e", "mult_h"]].copy()
    rows = rows.rename(columns={"LAD24CD": "ons_code", "median": "median_pay"})
    rows = rows.sort_values(["nation", "authority"]).round(2)
    tpl = (TEMPLATES / "table.html").read_text()
    html = tpl.replace("__ROWDATA__",
                       json.dumps(rows.to_dict(orient="records"), separators=(",", ":")))
    (OUT_PAGES / "table.html").write_text(html)
    print(f"  table.html   {len(rows)} rows · {round(len(html)/1024)} KB")


def main():
    print("Building pages ->", OUT_PAGES)
    bands = pd.read_csv(DATA_PROC / "uk_council_tax_full.csv")
    # the full 350-council band table (before the earnings join dropped two)
    wide = pd.read_csv(DATA_PROC / "uk_bands_2026-27.csv")
    wide = wide.pivot_table(index=["nation", "authority"], columns="band",
                            values="charge_gbp", aggfunc="first").reset_index()
    wide.columns = [f"band_{c.lower()}" if c in list("ABCDEFGHI") else c
                    for c in wide.columns]

    # attach ONS codes from the boundary attribute table
    lad = json.loads((DATA_RAW / "lad_attributes.json").read_text())
    lad_df = pd.DataFrame([f["attributes"] for f in lad["features"]])
    lad_df["key"] = lad_df.LAD24NM.map(norm_name)
    lad_df["nation"] = lad_df.LAD24CD.str[0].map(
        {"E": "England", "W": "Wales", "S": "Scotland", "N": "Northern Ireland"})
    wide["key"] = wide.authority.map(norm_name)
    wide = wide.merge(lad_df[["LAD24CD", "key", "nation"]],
                      on=["key", "nation"], how="left")

    build_map(wide, bands)
    build_table(bands)


if __name__ == "__main__":
    main()
