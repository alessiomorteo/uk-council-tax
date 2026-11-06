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
