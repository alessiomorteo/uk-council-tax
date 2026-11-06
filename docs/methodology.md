# Methodology

How the numbers are produced, and why each choice was made.

## 1. Discovery: why this is three downloads

The instinct is to scrape ~370 council websites. That is wrong here. Official
statistics bodies publish bulk files containing the full cross-tab; the work is
finding them.

| Nation | Route | Difficulty |
|---|---|---|
| England | MHCLG *Tables 1–9*, sheet `Table_9` | easy once found |
| Wales | StatsWales API v2, `format=csv` | easy |
| Scotland | gov.scot CTAS *Council Tax by Band* | easy |
| N. Ireland | none — no band system | n/a |

### The England trap

The *Live tables on Council Tax* index page advertises **Band D only**. The full
A–H cross-tab is in `Table_9` of a 17-sheet workbook that the index does not link
to. Anyone trusting the page description concludes per-band data does not exist
and starts building scrapers.

### The data.gov.uk trap

`data.gov.uk` hosts datasets titled "Council tax charges" that look national.
They are single-council uploads: Data Mill North is **Leeds only**, Calderdale is
**Calderdale only**. Always check the publisher field and count distinct entities
before treating a portal dataset as national.

### The third-party API trap

`civaccount.co.uk` offers a free JSON API with no key. It reports
`total: 163` councils (not the advertised 317) and carries **Band D only** — no
A–H. Useful for narrative fields, useless for band tables.

## 2. Parsing: the traps that silently corrupt

### Header/row length mismatch

The Band D live table's header carries a trailing `Notes` label that the data
rows omit. Mapping year columns by position shifts every value by one year —
Adur's 2026-27 Band D read £376 instead of £2,548. Fix: drop the trailing label
before mapping, and assert `len(header) == len(row)`.

### Repeated-cell padding

ODS stores runs of empty cells as one cell with a large `number-columns-repeated`.
Expanding those faithfully pads the header and breaks alignment. Cap the
expansion (200) and strip trailing empties.

### Footnote rows parse as data

Statistical workbooks append prose below the table — `Excludes Water and
Sewerage`, `1 Footnote: Subsequent to the original publication…`. These survive a
numeric cast when they land in the label column. Scotland's file yielded 37
"authorities" instead of 32. Fix: filter the entity column for prose, then
reconcile the count against the known population.

### Entity name drift

The same council appears as `Edinburgh, City of` and `City of Edinburgh`, or
`Eilean Siar` and `Na h-Eileanan Siar`. Without an alias map one council splits
into two across years.

### Column names that shadow DataFrame methods

A column called `median` makes `df.median` return the *method*, so
`df.median.isna()` raises `AttributeError`. Use bracket access for `median`,
`mean`, `count`, `sum`, `min`, `max`, `std`.

## 3. Alignment: which axis actually works

There are two candidate axes and only one is safe.

| Axis | What aligns | Safe? |
|---|---|---|
| **Ratio** (band ÷ Band D) | proportion of the reference band | **yes** |
| **Nominal value** (band → property value) | the underlying valuation | **no** |

### Why value alignment is impossible

The three nations reference two different dates (1991 and 2003) *and* three
different threshold ladders. Band D means a £68k–£88k house in England, £45k–£58k
in Scotland and £91k–£123k in Wales. There is no official crosswalk, and the VOA
explicitly does not use price indices. Aligning on value requires restating all
three onto a common date with a house-price index — and the result is an
estimate, not a fact.

### Why ratio alignment works

Every band's charge is defined by statute as a fixed multiple of Band D. Divide
each band by Band D and the multiplier pops out. It is identical for A–D in all
three nations.

### The time-varying ladder

**This is the trap most comparisons fall into.** Scotland's ladder is not
constant:

- 1993-94 → 2016-17: `6/9, 7/9, 8/9, 9/9, 11/9, 13/9, 15/9, 18/9`
- 2017-18 → now: `240/360, 280/360, 320/360, 360/360, 473/360, 585/360, 705/360, 882/360`

The change is **SSI 2016/368**, in force 1 April 2017 — the first change to the
Scottish proportion since 1992. So the expected ladder must be `f(nation, year)`,
never a global constant.

The Scottish workbooks themselves are inconsistent about this: the 2012-13 to
2016-17 files print `11/9 … 18/9` in their `Ratio to Band D` row, while 2017-18
onward print `473/360 …`. **Always derive the implied ratio from the values and
compare it to the declared label** — a mismatch is a finding, not a bug.

## 4. Validation: the load-bearing check

The ratio identity is asserted on **every row**:

```python
dev = (df.charge_gbp / df.band_d - expected_multiplier(nation, year, band)).abs()
assert (dev < 1e-3).all()
```

8,564 checks, 0 violations, max deviation 1.2e-5 (rounding in the published
figures). This catches column-offset bugs that spot checks miss — it is how the
`Notes` header shift was found.

`src/validate.py` additionally asserts coverage counts, ladder uniformity within
nations, the 2017 switch, the England/Wales/I band structure, and that the
affordability file drops exactly the two ONS-suppressed councils.

## 5. Geography: joining on codes, not names

Boundaries come from the ONS Open Geography Portal ArcGIS REST service. Query the
FeatureServer directly — the portal's `/api/download/` GeoJSON endpoint returns
HTTP 202 with an async job stub that parses as invalid JSON.

Join on `LAD24CD`. Name joins fail on punctuation variants. **ONS also recodes
authorities without renaming them**: Barnsley moved `E08000016` → `E08000038` and
Sheffield `E08000019` → `E08000039`. A boundary file and a statistics file can
both be current yet disagree. Match by name to discover the recode, then add an
explicit alias map. Never accept a 99% code join without investigating every miss.

## 6. Affordability

`Band D ÷ median gross annual pay (ASHE 2025, place of residence)`.

This is a **relative indicator**, not a household's bill. Caveats:

- Pay is per *job*; council tax is per *dwelling* and assumes two adults.
- No discounts, single-occupancy reduction or Council Tax Reduction applied.
- Pay is 2025, council tax is 2026-27 — one year apart, no uprating.

Its value is comparative: it reveals that absolute level and affordability are
close to negatively correlated at the top of the distribution, which a level-only
map cannot show.

## 7. Rendering

- **Static figures** via matplotlib. Choropleths for continuous measures;
  a categorical two-colour map where the data is genuinely binary (the Band H
  multiplier is 2.000× or 2.450×, nothing between).
- **Interactive pages** are single self-contained HTML files. GeoJSON and rows are
  inlined as JS literals because `fetch()` of a sibling file is blocked by CORS
  on `file://`. Coordinates rounded to 3dp (~110 m), which took a 1.1 MB boundary
  file to ~520 KB.
- **The multiplier gets a table, not a map.** It is a national constant, so a
  choropleth adds nothing — every council in Scotland is identical.
