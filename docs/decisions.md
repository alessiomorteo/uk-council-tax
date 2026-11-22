# Design decisions

Short records of the non-obvious choices, and what was rejected.

## Ratio axis, not value axis

**Chose:** align nations on `band ÷ Band D`.
**Rejected:** aligning on nominal property value.

Value alignment is impossible without inventing a crosswalk. The three nations
reference different dates (1991 vs 2003) and different threshold ladders, and the
VOA does not use price indices. Any value alignment would be an estimate dressed
as a fact. The ratio is statutory, exact, and verifiable — so it is the axis.

## Time-varying ladder, not a global constant

**Chose:** `ladder(nation, year)` applied per row.
**Rejected:** one ladder per nation.

Scotland changed its E–H multipliers on 1 April 2017 (SSI 2016/368). A global
constant silently mis-states one era. The function form makes the switch explicit
and testable.

## Fail the build on ratio violation

**Chose:** `align.py` exits non-zero if any charge disagrees with its multiplier.
**Rejected:** warn and continue.

The ratio identity is the only check that catches column-offset bugs across
thousands of rows. A warning would be ignored; a non-zero exit is not.

## Choropleth for continuous, table for constant

**Chose:** the Band H multiplier gets a **table**, not a map.
**Rejected:** colouring the map by multiplier.

The multiplier is a national constant — every council in Scotland is identical.
A choropleth of a two-value national variable is a lie about the data's
structure. The map has a "Band H multiplier" view only because it also carries
the no-data case; the *nation-level* comparison is a table.

## Inline data into HTML, don't fetch

**Chose:** embed GeoJSON and rows as JS literals.
**Rejected:** `fetch("map_data.geojson")`.

CORS blocks `fetch` of a sibling file on `file://`, so the page silently renders
nothing. Inlining makes each page a single portable artefact. Cost: ~550 KB per
page, mitigated by rounding coordinates to 3dp (~110 m).

## Separate map page and table page

**Chose:** two files, cross-linked.
**Rejected:** table underneath the map.

348 rows × 16 columns needs full width; the map needs full height. Putting them
in one page makes both worse. They share a title and footer so they read as one
deliverable.

## Boundaries from the ArcGIS REST API

**Chose:** query the FeatureServer directly.
**Rejected:** the portal's `/api/download/` GeoJSON link.

The download endpoint returns HTTP 202 with an async job stub, which parses as
invalid JSON. The REST query returns the data immediately.

## ONS recode map, not name matching

**Chose:** join on `LAD24CD` with an explicit old→new alias map.
**Rejected:** joining on authority name.

Names drift (`Bristol, City of`), and ONS recodes authorities without renaming
them (Barnsley `E08000016`→`E08000038`). Name matching as the primary key would
be silently wrong; as a *diagnostic* it is how the recode was found.

## Drop the two ONS-suppressed councils from affordability only

**Chose:** keep 350 in band data, 348 in affordability.
**Rejected:** dropping them everywhere, or imputing earnings.

City of London and Isles of Scilly have no ASHE estimate. Their council tax is
real and should still appear on band maps; their affordability is genuinely
unknown and should not be invented. The map shows them grey in the affordability
view only.

---

## Carry both gross revenue and the published tax base

**Decision:** compute `dwellings × charge` as `revenue_gross`, and separately
carry the published Band D equivalent tax base as `tax_base_published`, deriving
`revenue_tax_base = tax_base_published × band_d`.

**Why:** the naive product is wrong as a revenue estimate, and wrong in a way
that looks plausible. It overstates by 6 to 11 per cent because it ignores
single-occupancy discounts, second-home premiums and exemptions. England's
published tax base is 21.73m Band D equivalents against a naive 23.96m — a
9.3 per cent gap that no arithmetic on the charges alone would reveal.

**Rejected:** using `dwellings × charge` as "revenue". It reads as a revenue
figure but is a liability ceiling. Publishing it unlabelled would be a silent
error rather than a visible approximation.

Both are carried so the gap is auditable. `tax_base_ratio` is the second over
the first, and the validation asserts it stays between 0.75 and 1.05 for every
council.

## Join taxbase on code in England, on name elsewhere

**Decision:** England joins on ONS code with `ONS_RECODE` applied; Wales and
Scotland join on `norm_name(authority)`.

**Why:** the England workbook carries ONS codes, so the code is the safe key. The
Welsh and Scottish taxbase files carry no code at all — only names — so there is
no choice. `norm_name` already resolves the punctuation variants (`Argyll & Bute`
vs `Argyll and Bute`) and gives 32 of 32 for Scotland.

**Rejected:** name matching in England. It fails on exactly the councils the
recode exists for: Barnsley and Sheffield. Using the code plus recode gives
348 of 348.

---

## Price discounts in Band D equivalents, not dwellings

**Decision:** compute discount value as `(equivalents before discount - equivalents
after discount) x band_d`, working entirely in Band D equivalent units.

**Why:** the first attempt multiplied a *dwelling* shortfall by the Band D charge
and compared it against a *Band D equivalent* net figure. Those are different
units — a Band H dwelling is 2.0 to 2.45 equivalents — so 25 councils appeared to
have net liability above gross liability. That looked like a finding and was
actually a unit error.

The published chain is:

```
Table 1.26  dwelling equivalents after discounts and premiums
Table 1.27  the same in Band D equivalents
Table 1.28  contributions in lieu, added on top
Table 1.29  tax base = 1.27 + 1.28
Table 1.31  council tax support reduction, deducted from 1.29
```

Gross is Table 1.27 plus the discount shortfall. Net is Table 1.29 less Table
1.31, which gives 19,295,312 equivalents against the published 19.3m.

**Rejected:** using Table 1.33 (Band D equivalents after council tax support) as
the net figure. It is close but not the tax base for setting purposes, and it
leaves a £1bn gap against the published requirement.

## Negative discount values are genuine, not a bug

**Decision:** allow `discount_value` to be negative, and assert that only City of
London and Isles of Scilly are affected.

**Why:** a premium can raise more than discounts give away. City of London has a
25.6% second-homes premium against a small single-adult discount population, so
its equivalents *rise* after applying discounts and premiums. Forcing the figure
positive would misstate the council's position.

**Rejected:** clamping at zero, or treating it as a data error.

---

## Keep Scotland's designated utilities as their own row

**Decision:** retain the "Designated utilities" row from the Scottish valuation
roll, flagged `authority_type = "UTIL"`, rather than dropping it.

**Why:** it is not a council area, but it is not a rounding error either — 54
properties and £799m of rateable value, valued centrally because the properties
span council boundaries. Dropping it made Scotland's national total £6.78bn
against the published £7.58bn, a gap large enough to look like a parsing bug.
Assigning it to any single council would overstate that council by more than its
entire business base in some cases.

**Rejected:** dropping it (breaks the national reconciliation) and allocating it
proportionally (invents an allocation the source does not make).

## Normalise units at parse time, per source

**Decision:** convert each nation's money and counts to pounds and units inside
its own parser, then assert national totals against published figures.

**Why:** the three sources use three different conventions. England reports
pounds and counts. Wales reports thousands of pounds and thousands of
hereditaments. Scotland reports millions of pounds. A single conversion applied
to the combined frame produced Wales rateable value of £2.79 trillion and 125
hereditaments — both wrong by three orders of magnitude, and both plausible
enough at a glance to pass unnoticed.

**Rejected:** converting in the combined frame with one rule. The units genuinely
differ per source, so the conversion has to sit next to the parse.

---

## Take England and Wales rateable value from the VOA, not NNDR1

**Decision:** source rateable value from the VOA stock of properties release for
both England and Wales, rather than leaving England blank or using StatsWales for
Wales.

**Why:** the NNDR1 supplementary workbook has no rateable value at all, which
left the England column empty and made the map panel meaningless. The VOA
publishes it for every authority back to 2011. Using one source for both nations
means they share a basis and a vintage, which StatsWales would not: its aggregate
rateable value is £2.79bn against the VOA's £2.44bn for Wales, because it is an
estimate basis for billing rather than the rating list.

**Rejected:** leaving England blank (the gap is fillable), and mixing VOA for
England with StatsWales for Wales (two bases on one axis).

## Exclude abolished authorities from the VOA table

**Decision:** filter the VOA rows to those with no `abolished year`.

**Why:** the file is a time series, so it retains districts that no longer exist.
England has 332 `LAUA` rows but only 296 current authorities; the extra 36 are
Allerdale, Carlisle, Copeland, Barrow-in-Furness, Eden and others merged away in
2019, 2021 and 2023. Including them gives £72.4bn against the published £68.5bn.

The `CTYMET` rows are a second trap: they are counties and metropolitan counties,
which sit above districts and double-count the same properties.

---

## Business rates get their own pages, not a tab

**Decision:** publish `rates_map.html` and `rates_table.html` as separate pages
rather than adding views to the council tax map.

**Why:** business rates are a different tax on a different object. Council tax is
levied on dwellings through a local band ladder; business rates are levied on
non-domestic property through a national multiplier, and much of the yield is
pooled and redistributed rather than kept by the billing authority. Putting them
on the same map would invite the reader to add them together, which is
meaningless.

The two also have different coverage: council tax has 350 councils with complete
band data, business rates has 350 councils but with rateable value on a different
vintage and relief value on a third. A shared map would have to hide that.

**Rejected:** a fifth tab on the existing map. The council tax map already has six
views and the measures do not belong on one axis.

## Unify relief value across the three nations

**Decision:** build a single `relief_value` column from whichever column each
nation publishes.

**Why:** England publishes three separate relief values (small business, empty
property, other discretionary), Wales publishes one mandatory-relief total, and
Scotland publishes one relief-value total. Without unification the relief panels
covered only Scotland, 32 of 350 councils, which reads as missing data rather
than as a mapping problem.

**Caveat recorded in the page:** England's three published values are a partial
total — they cover small business, empty property and other discretionary, not
every relief type. The relief-share measure is therefore indicative, and the page
says so.

---

## Normalise with population rather than comparing raw totals

**Decision:** add ONS mid-year population estimates and derive
`council_tax_per_head` and `dwellings_per_1000`, rather than leaving size
comparisons on raw revenue.

**Why:** a raw revenue total mostly measures how many people live somewhere.
Normalising inverts the national ranking: Wales raises the most council tax per
head (£1,018) despite having lower Band D charges than England (£974), because
its stock sits lower in the bands and it has more dwellings per person. Scotland
raises least (£808). A Band D league table alone shows the opposite ordering, so
the per-head figure is the honest cross-nation comparison.

**Rejected:** comparing raw gross revenue, which rewards population and tells you
nothing about burden.

## Join population on ONS code, with the recode applied

**Decision:** match on the ONS code through `ONS_RECODE`, the same path used for
the taxbase join.

**Why:** the ONS population file uses the current codes but retains the older
Barnsley and Sheffield numbering in some editions. Applying the existing recode gives
348 of 348 against the affordability set with no name matching at all, which is
the cleanest join in the pipeline.

Note the population file interleaves countries, regions, counties and
metropolitan counties with the billing authorities. Filtering on the geography
type is required: counties sit above districts and would double-count the same
population, which is the same trap as the VOA `CTYMET` rows.
