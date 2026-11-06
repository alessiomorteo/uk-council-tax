# Preparatory scoping: Council Taxbase, then IMD

Two datasets that extend the existing council tax work. Both are single-file,
local-authority-level, ONS-coded downloads, so they slot into the current
pipeline without new infrastructure.

Everything below was verified by downloading and opening the files, not read
from documentation.

---

# Part 1 — Council Taxbase

## Why this one first

The current project holds the **rate** (what each band costs). Taxbase holds the
**count** (how many dwellings sit in each band). Multiply them and you get
**revenue per band per council** — a number neither dataset contains alone.

It also lets us compute a Band D equivalent taxbase and check it against MHCLG's
published figure, which is a genuine validation opportunity rather than just
another layer.

## Source

| | |
|---|---|
| Publisher | Ministry of Housing, Communities and Local Government |
| Collection | <https://www.gov.uk/government/collections/council-taxbase-statistics> |
| Latest release | Council Taxbase 2025 in England (revised) |
| File | `2025_Local_Authority_Drop_Down.xlsx`, 1.8 MB |
| URL | <https://assets.publishing.service.gov.uk/media/696f605ff6aa424b452e3359/2025_Local_Authority_Drop_Down.xlsx> |
| Licence | Open Government Licence v3.0 |
| Years available | **2010 to 2025** — 16 annual releases in the collection |

## Structure

The workbook has **16 sheets**. The one we need is `Council Taxbase Data`.

```
Cover, Contents, Notes
CTB Form, CTB Supplementary Form, CT Support, Family Annexe   <- blank forms
Empty Properties, Second Homes                                <- blank forms
Council Taxbase Data          <- 303 rows x 336 cols   THE ONE
Supplementary Data            <- 303 x 92
Council Tax Support Data      <- 303 x 80
Family Annexe Data            <- 303 x 26
Empty Properties Data         <- 303 x 394
Second Homes Data             <- 303 x 116
LA list                       <- 298 x 2
```

### The layout trap

`Council Taxbase Data` is **35 tables laid side by side** in one sheet, not one
table. Row 4 carries the block titles; row 5 is the leaf header; data starts at
row 6.

```
row 0-3   prose notes
row 4     block titles  -> "Table 1.01 Total Number of Dwellings on Valuation List"
row 5     leaf headers  -> "E-code | ONS Code | Region | Local Authority | Notes | Band A ... Band H | Total"
row 6+    data
```

There are **31 occurrences of "Band A"** across 336 columns. Reading the sheet
naively gives you duplicate column names and pandas silently mangles them.

**The first block (columns 0 to 13) is the one we want:**

| col | field |
|---|---|
| 0 | E-code |
| 1 | ONS Code |
| 2 | Region |
| 3 | Local Authority |
| 4 | Notes |
| 5–12 | Band A, B, C, D, E, F, G, H (dwelling counts) |
| 13 | Total |

Later blocks are the derived series: line 4 chargeable dwellings, discounts,
second homes, empty properties, and so on. Valuable, but a separate decision.

### Extracting it safely

```python
raw = pd.read_excel(path, sheet_name="Council Taxbase Data", header=None)
body = raw.iloc[6:].copy()
body.columns = range(len(raw.columns))          # positional, avoids duplicates
keep = {0:"ecode", 1:"ons_code", 2:"region", 3:"authority",
        5:"band_a", 6:"band_b", 7:"band_c", 8:"band_d",
        9:"band_e", 10:"band_f", 11:"band_g", 12:"band_h", 13:"total"}
frame = body[list(keep)].rename(columns=keep)
frame = frame[frame.ons_code.astype(str).str.match(r"^E\d{8}$")]
```

Assigning `range(len(columns))` rather than the header row is what avoids the
duplicate-name problem.

## Grain and coverage

**297 rows** with a valid ONS code. The first row is `England` (`E92000001`), an
aggregate — drop it, leaving **296 billing authorities**, which matches the
council tax dataset exactly.

## Join to the existing work

Straight ONS-code join on `LAD24CD`.

**Verified: 292 of 294 English councils match.** The two misses are **Barnsley**
and **Sheffield** — the ONS recode already handled in `config.py`
(`E08000016 → E08000038`, `E08000019 → E08000039`). Applying the existing
`ONS_RECODE` map closes them.

Wales and Scotland are **not** in this dataset. It is England-only. That is a
real limitation for a UK-wide project: the revenue layer would cover England
alone.

## What it unlocks

1. **Revenue per band** — `dwellings × charge`, per council, per band. Answers
   "which councils raise most from Band H" and "what share of a council's taxbase
   is Band D".
2. **Band D equivalent taxbase** — `Σ(dwellings_band × multiplier_band)`,
   directly comparable to the published figure. A hard validation check.
3. **A second map layer** — the existing choropleth gains a revenue view with no
   new geography.
4. **Rate against base** — councils with a high Band D charge and a small taxbase
   behave very differently from those with a large base. That contrast is
   invisible in either dataset alone.

## Risks

| Risk | Mitigation |
|---|---|
| 35 tables in one sheet | Positional column selection, as above |
| Duplicate column names | Assign integer columns before selecting |
| England-only | State it plainly; do not imply UK coverage |
| ONS recode (Barnsley, Sheffield) | Reuse the existing `ONS_RECODE` map |
| 16 years of historical files may differ in layout | Verify the header row per year before parsing, as with the Band D live table |

## Effort

**About an hour.** Fetch, parse, join, one new figure, one new map layer. The
boundary join, `norm_name`, `ONS_RECODE` and the render pipeline are all reusable
unchanged.

---

# Part 2 — Indices of Deprivation

## Why this one

The current project found that Band D costs **10.38%** of median pay in
Nottingham and **2.10%** in Wandsworth. IMD answers the obvious next question:
are the least-affordable councils also the most deprived? That is the question a
reader actually asks, and it needs no new geography to answer.

## Source

| | |
|---|---|
| Publisher | Ministry of Housing, Communities and Local Government |
| Release | English indices of deprivation 2025 |
| Page | <https://www.gov.uk/government/statistics/english-indices-of-deprivation-2025> |
| Licence | Open Government Licence v3.0 |
| Coverage | **England only** |
| Frequency | Roughly every five years (2025, 2019, 2015, 2010) |

### Files available

| File | Grain | Size |
|---|---|---|
| `File_1_IoD2025_Index_of_Multiple_Deprivation.xlsx` | **LSOA** (33,756 rows) | 1.5 MB |
| `File_2_IoD2025_Domains_of_Deprivation.xlsx` | LSOA | — |
| `File_3_IoD2025_Supplementary_Indices_IDACI_and_IDAOPI.xlsx` | LSOA | — |
| `File_8_IoD2025_Underlying_Indicators.xlsx` | LSOA | — |
| `File_10_..._Local_Authority_District_Summaries__lower-tier__v2.xlsx` | **LA** (297 rows) | 226 KB |
| `File_11_..._Local_Authority_District_Summaries__upper-tier__v2.xlsx` | LA | — |
| `File_12_..._Local_Enterprise_Partnership__LEP__Summaries.xlsx` | LEP | — |
| `File_13_..._Integrated_Care_Board__ICB__Summaries.xlsx` | ICB | — |
| `File_14_..._Local_Resilience_Forum__LRG__Summaries_v2.xlsx` | LRG | — |
| `File_15_..._Built_Up_Area__BUA__Summaries.xlsx` | BUA | — |

**Start with File 10** (lower-tier LA summaries). It is 226 KB, already
aggregated, and joins directly.

## Structure — File 10

**11 sheets**, one per domain:

```
Notes, IMD, Income, Employment, Education, Health, Crime, Barriers, Living, IDACI, IDAOPI
```

Each sheet has the same shape. Header on row 0, data from row 1, **297 rows**:

| column | meaning |
|---|---|
| 0 | Local Authority District code (ONS) |
| 1 | Local Authority District name |
| 2 | IMD average rank |
| 3 | IMD rank of average rank |
| 4 | IMD average score |
| 5 | IMD rank of average score |
| 6 | Proportion of LSOAs in most deprived 10% nationally |
| 7 | Rank of proportion |
| 8 | Extent (share of LSOAs in most deprived 10%) |
| 9 | Rank of extent |

Verified sample: Hartlepool average score 37.58 (rank 6), Blackpool 43.47
(rank 1), Warrington 16.84 (rank 174).

### Choosing the measure

Three candidate measures, and they are not interchangeable:

- **Average score** — the intensity of deprivation. Best for a scatter against
  council tax burden.
- **Rank of average score** — ordinal, 1 = most deprived. Good for a choropleth.
- **Proportion of LSOAs in the most deprived 10%** — the "pockets" measure,
  which catches concentrated deprivation that an average can hide.

Use **average score** for correlation work and **rank** for mapping. Report both
if the finding depends on the choice.

## Structure — File 1 (if LSOA grain is needed)

Two sheets: `Notes` and `IMD25`. Header on row 0, **33,756 LSOA rows**:

| column | meaning |
|---|---|
| 0 | LSOA code (2021) |
| 1 | LSOA name (2021) |
| 2 | Local Authority District code (2021) |
| 3 | Local Authority District name (2021) |
| 4 | Index of Multiple Deprivation score |
| 5 | Index of Multiple Deprivation decile |

The LA code is already present, so aggregating to council level is a groupby —
useful if we want a **population-weighted** or **dwelling-weighted** average
rather than the published unweighted one.

## Join to the existing work

ONS-code join on `LAD24CD`, same as taxbase. **Expect the same Barnsley and
Sheffield recode.** The `ONS_RECODE` map handles it.

**England only.** Wales has the Welsh Index of Multiple Deprivation (WIMD) and
Scotland has the Scottish Index of Multiple Deprivation (SIMD) — separate
publications with different methodologies and **not comparable** to IMD. Do not
merge them into one axis without saying so.

## What it unlocks

1. **Burden against deprivation** — scatter of Band D as % of pay against IMD
   average score. The headline chart.
2. **A deprivation map layer** — the existing choropleth gains a fourth
   substantive view.
3. **A test of the affordability finding** — is the Nottingham/Wandsworth
   spread explained by deprivation, or independent of it? That is a real
   analytical question, not just a new visual.
4. **Rank correlation** — Spearman between burden and deprivation, with the
   caveat that both are England-only.

## Risks

| Risk | Mitigation |
|---|---|
| England-only | State it; do not imply UK coverage |
| Three different measures | Pick deliberately; report which and why |
| Not comparable across nations | Never merge IMD, WIMD and SIMD on one axis |
| Five-yearly, so 2025 data against 2026-27 tax | One to two years apart; note it |
| Decile vs score confusion | Score for arithmetic, decile/rank for display |

## Effort

**About an hour** for File 10. The join and render are identical to taxbase, so
doing both together is barely more work than doing one.

---

# Recommended sequence

1. **Council Taxbase** — adds a denominator to data already built. Lowest risk,
   immediate validation opportunity (the Band D equivalent check).
2. **IMD** — adds an independent explanatory variable. Higher analytical value,
   same mechanics.

Both are England-only, which is worth deciding on now: the existing project is
UK-wide for band data but would gain two England-only layers. The honest options
are to label those layers clearly as England-only, or to extend to WIMD and SIMD
later at materially higher cost.

## Shared work, already done

None of the following needs rebuilding:

- ONS boundary join and `norm_name` normalisation
- `ONS_RECODE` for Barnsley and Sheffield
- The fetch, parse, align, join, render stage structure
- The map, table and site renderers
- The validation harness

The new work is a parser per dataset and a join, plus figures.
