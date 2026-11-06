# Preparatory scoping: Council Taxbase and deprivation, all three nations

Two datasets that extend the existing council tax work across **England, Wales
and Scotland**. Every factual claim below is asserted in
`src/verify_three_nations.py` against the downloaded files.

The original plan was England-only. Wales and Scotland publish equivalents, and
all three are obtainable, so the scope is now GB-wide to match the existing band
data.

---

# Part 1 — Council Taxbase

## Why this first

The current project holds the **rate** (what each band costs). Taxbase holds the
**count** (how many dwellings sit in each band). Multiply them and you get
**revenue per band per council** — a number neither dataset contains alone.

It also allows a Band D equivalent taxbase calculation that can be checked
against each nation's published figure, which is a hard correctness test rather
than just another layer.

## The three sources

| Nation | Source | Shape | Years |
|---|---|---|---|
| **England** | MHCLG `2025_Local_Authority_Drop_Down.xlsx` | 336-col wide sheet, 35 tables side by side | 2010–2025 |
| **Wales** | StatsWales API, dataset `062488e2-…` | long CSV, 152,362 rows | **31 years** |
| **Scotland** | gov.scot `CTAXBASE 2026 - Tables - Chargeable Dwellings.xlsx` | single clean sheet | current only |

All Open Government Licence v3.0.

### England

<https://assets.publishing.service.gov.uk/media/696f605ff6aa424b452e3359/2025_Local_Authority_Drop_Down.xlsx>
(1.8 MB)

**The layout trap.** `Council Taxbase Data` is **35 tables laid side by side** in
one 336-column sheet. Row 4 carries block titles, row 5 the leaf headers, data
from row 6. There are **31 duplicate `"Band A"` headers** — read it naively and
pandas silently mangles the columns.

The first block (columns 0–13) is the one needed:

| col | field |
|---|---|
| 0 | E-code |
| 1 | ONS Code |
| 2 | Region |
| 3 | Local Authority |
| 4 | Notes |
| 5–12 | Band A–H dwelling counts |
| 13 | Total |

```python
raw = pd.read_excel(path, sheet_name="Council Taxbase Data", header=None)
body = raw.iloc[6:].copy()
body.columns = range(len(raw.columns))     # positional; avoids duplicates
keep = {0:"ecode", 1:"ons_code", 2:"region", 3:"authority",
        5:"band_a", 6:"band_b", 7:"band_c", 8:"band_d",
        9:"band_e", 10:"band_f", 11:"band_g", 12:"band_h", 13:"total"}
frame = body[list(keep)].rename(columns=keep)
frame = frame[frame.ons_code.astype(str).str.match(r"^E\d{8}$")]
```

**297 rows** with a valid ONS code. The first is `England` (`E92000001`), an
aggregate — drop it, leaving **296 billing authorities**, matching the council
tax dataset exactly.

### Wales

StatsWales API, same pattern as the existing Wales band data:

```
https://api.stats.gov.wales/v2/062488e2-3fd6-4755-9b0b-a64547fc570f/data?format=csv&lang=en-gb
```

Long format, 13 MB, **152,362 rows**. Columns:
`Data values | Data description | Year | Row | Band | Authority | Notes`

- **31 years** of history, 1996-97 to 2026-27
- **23 authorities** — 22 plus a total row
- **Bands A to I plus Total** — Wales has nine bands, as with the charges
- **64 row types** in the `Row` column

That last point is the trap. Wales does not publish one number per band; it
publishes 64 different measures, of which `A1 - All chargeable dwellings` is the
headline count. Others include disability reduction, discount bands, second homes
and empty properties.

**Filter to the row type you want before aggregating**, or you will sum unrelated
measures. `A1` is the direct equivalent of the England and Scotland counts.

### Scotland

<https://www.gov.scot/binaries/content/documents/govscot/publications/statistics/2019/04/council-tax-datasets/documents/number-of-chargeable-dwellings/chargeable-dwellings--september-2026-data/chargeable-dwellings--september-2026-data/govscot:document/CTAXBASE+2026+-+Tables+-+Chargeable+Dwellings+%25281%2529.xlsx>
(19.6 KB)

Single sheet, cleanest of the three:

```
row 0-2   prose
row 3     blank
row 4     Band A | Band B | ... | Band H
row 5     valuation band ranges
row 6     Ratio to Band D
row 7     Scotland  (national total)
row 8+    32 councils
```

**The trap is the same one as the charges file:** two prose rows follow the 32
councils — a `Source:` line and a `Note:` line. Left unfiltered they parse as
authorities and give **34 councils**. Filter the name column for prose, then
assert the count is 32.

Verified total: Scotland Band D = **373,124** dwellings.

## Coverage summary

| | England | Wales | Scotland |
|---|---|---|---|
| Authorities | 296 | 22 | 32 |
| Bands | A–H | A–I | A–H |
| Grain | one row per LA, wide | long, 64 row types | one row per LA |
| Years | 16 | 31 | current |

**England and Scotland have eight bands; Wales has nine.** Any pipeline sized to
A–H silently drops Welsh Band I — the same trap as the charges work.

## What it unlocks

1. **Revenue per band** — `dwellings × charge`, per council, per band. Answers
   "which councils raise most from Band H" and "what share of a taxbase is Band D".
2. **Band D equivalent taxbase** — `Σ(dwellings_band × multiplier_band)`,
   checkable against each nation's published figure.
3. **A second map layer** — the existing choropleth gains a revenue view with no
   new geography.
4. **Rate against base** — a high charge on a small taxbase behaves very
   differently from a low charge on a large one. Invisible in either dataset alone.

## Risks

| Risk | Mitigation |
|---|---|
| England: 35 tables in one sheet | Positional column selection |
| England: duplicate column names | Integer columns before selecting |
| Wales: 64 row types | Filter to `A1` before aggregating |
| Scotland: 2 prose rows parse as councils | Filter names; assert count is 32 |
| Wales has 9 bands, not 8 | Enumerate per nation |
| England/Scotland current year only vs Wales 31 years | Decide whether the series is comparable before charting |

## Effort

**About two hours** for all three, versus one hour for England alone. The extra
work is two more parsers; the join and render are shared.

---

# Part 2 — Deprivation

## Why this one

The project found Band D costs **10.38%** of median pay in Nottingham and
**2.10%** in Wandsworth. Deprivation data answers the obvious next question: are
the least-affordable councils also the most deprived?

## The three sources

| Nation | Index | Source | Grain | Rows |
|---|---|---|---|---|
| **England** | IMD 2025 | `File_10_..._lower-tier__v2.xlsx` | LA summary | 297 |
| **Wales** | WIMD 2025 | StatsWales API `f30cc8bc-…` | LA summary | 1,782 |
| **Scotland** | SIMD 2020 | data.gov.scot CSV + lookup | data zone | 223,232 |

### England — IMD 2025

<https://www.gov.uk/government/statistics/english-indices-of-deprivation-2025>

**11 sheets**, one per domain:
`Notes, IMD, Income, Employment, Education, Health, Crime, Barriers, Living, IDACI, IDAOPI`

Header on row 0, **297 rows**, same columns on every sheet:

| col | meaning |
|---|---|
| 0 | LA District code |
| 1 | LA District name |
| 2 | IMD average rank |
| 3 | IMD rank of average rank |
| 4 | IMD average score |
| 5 | IMD rank of average score |
| 6 | Proportion of LSOAs in most deprived 10% |
| 7 | Rank of proportion |
| 8 | Extent |
| 9 | Rank of extent |

Verified: Blackpool 43.467 (rank 1), Hartlepool 37.58 (rank 6), Warrington
16.835 (rank 174).

An LSOA-level file also exists (`File_1`, 33,756 rows) carrying the LA code, so
aggregating is a groupby if a weighted average is wanted.

### Wales — WIMD 2025

StatsWales API, same pattern again:

```
https://api.stats.gov.wales/v2/f30cc8bc-8e97-449e-96a4-77b0400262d1/data?format=csv&lang=en-gb
```

170 KB, **1,782 rows**, **22 areas**, W06 codes.

Columns: `Data values | Data description | Area code | Area name | Domain | Deprivation group | Notes`

- **9 domains**: WIMD, Income, Employment, Health, Education, Access to services,
  Housing, Community safety, Physical environment
- **5 deprivation groups** per domain: Total LSOAs, most deprived 10%, 20%, 30%, 50%

This is a **count** table, not a score table — it gives you how many LSOAs fall in
each deprivation band, not an average score. To get a comparable measure to IMD's
average score you must derive one, or use the "most deprived 10% share" as the
common denominator.

### Scotland — SIMD 2020

Two files are required, which is the main difference from the other two nations.

**1. The data** — data.gov.scot CSV, 18.9 MB, **223,232 rows**:

```
https://data.gov.scot/dataset/scottish_index_of_multiple_deprivation_2020/resource/0786efac-2a01-404e-9966-e99e86a24950/download
```

Columns: `GeographyCode | GeographyName | GeographyType | DateCode | Measurement | Units | Value | Simd Domain`

- **Data zones only** — `GeographyType` has exactly one value, `2011 Data Zones`
- 7 domains plus SIMD
- Measurements: Decile, Quintile, Vigintile, Rank

**There is no council-area field.** The CSV cannot be joined to councils directly.

**2. The lookup** — `SIMD 2020v2 datazone lookup`, 1.3 MB, sheet
`SIMD 2020v2 DZ lookup data`, **6,976 data zones**:

```
https://gov.scot/binaries/content/documents/govscot/publications/statistics/2020/01/scottish-index-of-multiple-deprivation-2020-data-zone-look-up-file/documents/scottish-index-of-multiple-deprivation-data-zone-look-up/scottish-index-of-multiple-deprivation-data-zone-look-up/govscot:document/SIMD+2020v2+-+datazone+lookup+-+updated+2025.xlsx
```

This carries `DZ`, `SIMD2020v2_Rank`, `SIMD2020v2_Decile`, domain ranks,
`Population`, and crucially **`LAcode` and `LAname`**.

**The lookup already contains the ranks**, so for a council-level analysis the
lookup alone is sufficient — the 18.9 MB CSV is only needed for finer detail.

Roll up to councils with:

```python
lookup["rank"] = pd.to_numeric(lookup.SIMD2020v2_Rank, errors="coerce")
lookup["decile"] = pd.to_numeric(lookup.SIMD2020v2_Decile, errors="coerce")
council = lookup.groupby(["LAcode", "LAname"]).agg(
    data_zones=("rank", "size"),
    mean_rank=("rank", "mean"),
    share_decile1=("decile", lambda s: (s == 1).mean()),
).reset_index()
```

Verified: **32 council areas**, 6,976 data zones.

## The comparability problem — read this before building

**IMD, WIMD and SIMD are not comparable.** They differ in:

- **Methodology** — different domains, weights and indicator sets
- **Geography** — LSOA (England), LSOA (Wales), Data Zone (Scotland)
- **Scale** — IMD and SIMD publish scores and ranks; WIMD publishes counts
- **Vintage** — IMD 2025, WIMD 2025, **SIMD 2020**

Three options, in order of honesty:

1. **Rank within each nation, then compare ranks.** "Most deprived decile in
   England" against "most deprived decile in Wales". Defensible, clearly labelled.
2. **Use a shared denominator** — the share of small areas in the most deprived
   10% of *their own nation*. Comparable in shape, not in absolute terms.
3. **Do not combine.** Show three separate panels.

**Do not** put IMD, WIMD and SIMD scores on one axis. That would be a fabricated
comparison.

## Join to the existing work

| Nation | Join key | Result |
|---|---|---|
| England | ONS code on `LAD24CD` | 297 rows; Barnsley and Sheffield need `ONS_RECODE` |
| Wales | ONS code on `LAD24CD` | 22 of 22 |
| Scotland | `norm_name` on council name | **32 of 32 after normalisation** |

The Scotland name mismatch is four councils that differ only in punctuation:

| Existing data | SIMD lookup | `norm_name` |
|---|---|---|
| `Argyll & Bute` | `Argyll and Bute` | `argyll and bute` |
| `Dumfries & Galloway` | `Dumfries and Galloway` | `dumfries and galloway` |
| `Perth & Kinross` | `Perth and Kinross` | `perth and kinross` |
| `Shetland  Islands` | `Shetland Islands` | `shetland islands` |

The existing `norm_name` in `config.py` resolves all four — verified 32 of 32.

## What it unlocks

1. **Burden against deprivation** — Band D as % of pay against deprivation, per
   nation, on a shared rank axis.
2. **A deprivation map layer** — the choropleth gains a further view.
3. **A test of the affordability finding** — is the Nottingham/Wandsworth spread
   explained by deprivation, or independent of it?
4. **Rank correlation per nation** — Spearman within each nation, never pooled
   across them.

## Risks

| Risk | Mitigation |
|---|---|
| Indices not comparable | Rank within nation, or show separate panels |
| WIMD is counts, not scores | Use share-in-most-deprived-10%, or derive a score |
| SIMD needs a lookup file | Two downloads; the lookup alone suffices for LA work |
| SIMD is 2020, others 2025 | Note the five-year gap |
| Scotland name variants | `norm_name` — verified 32 of 32 |
| Decile vs score confusion | Score for arithmetic, rank/decile for display |

## Effort

**About two hours** for all three. Scotland is the slow one because of the
lookup and the rollup.

---

# Recommended sequence

1. **Council Taxbase, all three nations** — adds a denominator to data already
   built. Lowest risk, and the Band D equivalent check gives a hard validation.
2. **Deprivation, all three nations** — adds an explanatory variable. Higher
   analytical value, but the comparability problem needs a decision first.

## Decisions needed before building

1. **Which taxbase row type for Wales?** `A1 - All chargeable dwellings` is the
   direct equivalent of the other nations; the other 63 are a separate project.
2. **Which deprivation measure?** Average score (England only), rank, or
   share-in-most-deprived-10% (works for all three). The third is the only one
   available consistently.
3. **How to present non-comparable indices?** Per-nation panels, or a shared
   rank axis with a clear caveat.

## Shared work, already done

None of this needs rebuilding:

- ONS boundary join and `norm_name` normalisation
- `ONS_RECODE` for Barnsley and Sheffield
- The fetch, parse, align, join, render stage structure
- The map, table and site renderers
- The validation harness

New work is one parser per nation per dataset, plus the joins and figures.
