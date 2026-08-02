# Known data issues

Rows that are wrong or unconfirmed and cannot be fixed automatically. Each
entry says what is wrong, how it was found, and what would settle it.

Fixes go in `data/overrides.csv`, which lives only on the maintainer's
machine and is not in git. This file is the committed record of *why* those
overrides exist, and of what is still outstanding.

Counts below were measured against the 283-row census on 2026-08-01. Re-run
`makhaa-report geocode` to refresh them; the run prints the same figures.

## Coordinates a locator published wrongly

Qahwah House's store locator serves its Dearborn coordinate as a default for
stores that have none of their own. Comparing every locator-supplied
coordinate against an exact Census match, four disagree by more than 2 km and
all four are this brand:

| Store | Stored coordinate | Off by |
|---|---|---|
| Brooklyn, NY | 42.307, -83.245 | 790 km |
| Skokie, IL | 42.310, -83.275 | 371 km |
| North Olmsted, OH | 42.307, -83.245 | 149 km |
| Dearborn, MI | 42.307, -83.245 | 7 km |

The same brand publishes `"latitude": 33.8915, "longitude": 35.5024` for
Montclair, NJ in its own JSON-LD — a point in Lebanon. That one is already
caught by the US bounds check and corrected in `data/overrides.csv`; the four
above are inside the country, so no bounds check will find them.

**What would settle it:** compare every locator coordinate against its Census
match during `geocode` and flag disagreements beyond a threshold, rather than
only checking that a point is inside the US. Until then these three interstate
rows are wrong on any map, and are excluded by hand from anything plotted.

## Addresses no source recognises

Eleven addresses are confirmed by neither the Census geocoder nor
OpenStreetMap. Five of them have no coordinates at all and cannot be plotted:

- `haraz` — 21800 Towncenter Plz #253, Sterling, VA
- `matari` — 25191 Lorain Ave., North Olmsted, OH
- `qatra` — 6311 Stadium Dr B, Clemmons, NC
- `sanaa_cafe` — 9135 WEST STOCKTON BOULE, ELK GROVE, CA
- `shibam` — 9006 Joseph Campau Ave, Hamtramck, MI

The other six carry locator coordinates, so they plot, but the address itself
is unconfirmed:

- `haraz` — 8320 University Executive Park Dr B, Charlotte, NC
- `haraz` — 7028 Elyson Exchange Wy #100, Cypress, TX
- `qamaria` — 9325 JW Clay Blvd. Suite 223, Charlotte, NC
- `qamaria` — 4980 Broadway Dr. Ste 2, Plano, TX
- `qamaria` — 12729 W Foothill Blvd, Rancho Cucamonga, CA
- `qamaria` — 1529 US-14 W, Rochester, MN

They fall into recognisable groups: numbered routes a gazetteer files under
another name (`US-14 W`, `Rte 59`, `Hwy 6`), addresses in developments too new
to have been ingested (`Elyson Exchange Wy` in Cypress), a suite letter glued
to the street with no marker to split on (`Stadium Dr B`, `South Blvd C`), and
one street the brand's own page publishes truncated (`WEST STOCKTON BOULE`).

**What would settle it:** a source with better coverage than TIGER. Geocodio's
free tier is 2,500 lookups a day and needs an API key; the USPS Addresses API
is free and authoritative but its OAuth needs a CRID and MID issued through a
Business Customer Gateway administrator.

## One store that splits in two on re-scrape

`mokafe` publishes `606 Broadhollow Rd, Melville, NY`; Census standardises it
to `606 Broad Hollow Rd`. Splitting a word is beyond any abbreviation rule, so
the two spellings hash to different uids and the next scrape inserts the
original alongside the correction.

Every other correction was brought under one uid by widening
`normalize_street`. This is the only survivor.

**What would settle it:** drop the duplicate through `data/overrides.csv` once
it appears, or stop adopting the correction for this row.

## Smaller discrepancies

- **Livermore ZIP.** `moka_and_co`'s locator gives `94551` for
  `4521 Livermore Outlets Dr`; OpenStreetMap records `94550` for that
  building. The override leaves the ZIP alone rather than pick a side.
- **`name` has no shared meaning across brands.** It holds `"Folsom, CA"`,
  `"Qahwah House West Dearborn"`, `"Mesa"`, and `"Bethlehem, Pennsylvania"`
  depending on which locator produced it. Nothing depends on it yet.
- **Two phone formats** — `(313) 406-6911` and `301-500-2060`.

## Non-issues, recorded so they are not re-investigated

- **`matari` publishes `285 South Broadway, Hicksville, Long Isand, NY`.** The
  city typo and the borough-for-city are on the brand's own page. The
  normalizer splitting that into `city="Long Isand"` is correct behaviour
  given the input; it is fixed by an override, not by a scraper change.
- **Addresses without a ZIP.** Only four rows lack one, and the geocoder is
  given the ZIP whenever there is one. A missing ZIP is not why an address
  fails to match.
