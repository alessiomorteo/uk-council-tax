# Sources

All material is Open Government Licence v3.0 unless stated.

## Council tax charges by band

**England — 2026-27**
Ministry of Housing, Communities and Local Government (MHCLG).
*Council Tax levels set by local authorities in England 2026 to 2027*, Tables 1–9.
Sheet `Table_9` = "Area council tax by band".
<https://www.gov.uk/government/statistics/council-tax-levels-set-by-local-authorities-in-england-2026-to-2027>

**England — Band D history, 1993-94 onward**
MHCLG. *Band D Council Tax live table*.
Sheet `inc_PP` (incl. parish), `exc_PP` (excl. parish), `Area_CT` (area total).
<https://www.gov.uk/government/statistical-data-sets/live-tables-on-council-tax>

**Wales — 1996-97 to 2026-27**
Welsh Government / StatsWales.
*Council tax levels by billing authority and band*, dataset `1988b6af-2a9c-43b6-8939-83e6cceb3903`.
<https://stats.gov.wales>

**Scotland — 2026-27**
Scottish Government. *Council Tax Assumptions (CTAS) — Council Tax by Band 2026-27*.
<https://www.gov.scot/publications/council-tax-datasets/>

## Council Taxbase (dwellings per band)

**England — 2025**
MHCLG. *Council Taxbase 2025 in England (revised)*, local authority drop-down.
Sheet `Council Taxbase Data`, columns 5–12 (band counts) and 287 (Table 1.29,
tax base in Band D equivalents). The sheet holds 35 tables side by side with 31
duplicate `Band A` headers, so columns are selected by position.
<https://www.gov.uk/government/statistics/council-taxbase-2025-in-england>

**Wales — 1996-97 to 2026-27**
Welsh Government / StatsWales. *Council tax dwellings by band*, dataset
`062488e2-3fd6-4755-9b0b-a64547fc570f`.
Row type `A1 - All chargeable dwellings` = headline count;
`E1 - Total band D equivalent dwellings` = published tax base.
<https://statswales.gov.wales/Catalogue/Local-Government/Finance/Council-Tax>

**Scotland — 2026**
Scottish Government. *Council tax base: number of chargeable dwellings*, and
*Band D equivalents in Scotland, 1996-2026*.
<https://www.gov.scot/publications/council-tax-datasets/>

## Business rates (non-domestic rates)

**England — 2026-27**
MHCLG. *National non-domestic rates collected by councils: 2026-27 forecast*,
NNDR1 supplementary tables. Three sheets of per-authority data with ONS codes:
`NNDR1S Hdits Reliefs Data` (30 relief types), `NNDR1S Hdits Multipliers Data`
(hereditaments by multiplier), `NNDR1S Empty & SBRR Data` (relief values).
Header on row 5, data from row 6, aggregate rows first. `[x]` and `[z]` are the
workbook's not-applicable and not-available markers.
<https://www.gov.uk/government/statistics/national-non-domestic-rates-collected-by-councils-in-england-forecast-2026-to-2027>

**Wales — 2026-27**
Welsh Government / StatsWales. *Non-domestic rates estimates by local authority*,
dataset `8e0d656a-50ea-4509-8363-c52d8315b750`.
Hereditaments are published in thousands; money in thousands of pounds.
<https://statswales.gov.wales/Catalogue/Local-Government/Finance/Non-Domestic-Rates>

**Scotland — 2025-26**
Scottish Government. *Non-domestic rates relief statistics 2025*.
Table 12 = properties and rateable value by council area;
Table 4 = relief counts and values by council area (1 June 2025 snapshot).
<https://www.gov.scot/publications/non-domestic-rates-relief-statistics-2025/>

## Rateable value (England and Wales)

**2011 to 2025, by local authority**
Valuation Office Agency. *Non-domestic rating: stock of properties, 2025*.
Table SOP3.2 = total rateable value by administrative area and financial year;
Table SOP3.1 = number of rateable properties. Values in £ thousands.
Two filters are required: `LAUA` rows only (not `CTYMET`, which are counties at a
different geography level), and rows with no `abolished year` (the file retains
legacy districts merged away in 2019, 2021 and 2023).
<https://www.gov.uk/government/statistics/non-domestic-rating-stock-of-properties-2025>

## Earnings

**Median gross annual pay, 2025**
Office for National Statistics. *Annual Survey of Hours and Earnings (ASHE) 2025*,
Table 8.7a — annual pay, gross, by place of residence and local authority.
<https://www.ons.gov.uk/employmentandlabourmarket/peopleinwork/earningsandworkinghours/datasets/placeofresidencebylocalauthorityashetable8>

## Geography

**Local Authority Districts (December 2024) Boundaries UK BUC**
Office for National Statistics, Open Geography Portal.
Contains OS data (c) Crown copyright and database right 2025.
<https://geoportal.statistics.gov.uk>

## Legislation

| Instrument | Effect |
|---|---|
| Local Government Finance Act 1992, s.5 | Band multipliers, England and Wales |
| Local Government Finance Act 1992, s.74 | Band multipliers, Scotland |
| Council Tax (Valuation Bands) (Wales) Order 2003, SI 2003/3046 | Welsh A–I bands, 2003 revaluation |
| Council Tax (Substitution of Proportion) (Scotland) Order 2016, SSI 2016/368 | Scottish E–H ladder from 1 April 2017 |

## Not used, and why

- **VOA per-property band lookup** — works, but carries an explicit "not to be
  used for commercial use" notice, and postcodes are tokenised in the URL.
- **VOA bulk valuation list** — FOI refused under s.44(1)(a) FOIA and s.23(1)
  CRCA 2005. An absolute exemption; there is no bulk route.
- **Scottish Assessors (saa.gov.uk)** — behind a Cloudflare bot challenge.
- **data.gov.uk "Council tax charges"** — single-council uploads mislabelled as
  national (Data Mill North = Leeds only; Calderdale = Calderdale only).
- **civaccount.co.uk API** — free and keyless, but 163 councils not 317, and
  Band D only.
