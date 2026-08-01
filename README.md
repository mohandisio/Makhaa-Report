# makhaa-report

Census of US Yemeni coffee chain locations, scraped weekly from each
brand's own store locator into SQLite + CSVs, with a self-contained HTML
report generated from the database.

14 brands tracked: 12 scraped, 2 hand-maintained (Mohka House has no
website; Sana'a Cafe's locator is provably incomplete). See
`src/makhaa_report/registry.py` for the full registry including known
lookalike exclusions (qatracafe.com ≠ qatracoffee.com, etc.).

## Commands

```
uv run makhaa-report scrape     # all brands -> snapshots + locations, idempotent
uv run makhaa-report geocode    # fill missing coordinates (Census batch geocoder)
uv run makhaa-report export     # database -> data/exports/*.csv
uv run makhaa-report report     # -> one self-contained HTML file
uv run makhaa-report diff A B   # compare two runs
```

Exit codes: 0 ok, 1 any brand failed or drifted, 2 usage error.

## Weekly ritual (manual for now)

1. `uv run makhaa-report scrape` — a brand whose row count falls outside
   its expected band is quarantined (old rows untouched, loud log, exit 1).
2. `uv run makhaa-report diff <prev> <latest>` — triage added/removed
   stores.
3. Removals and closures are recorded by hand in `data/overrides.csv`
   (`patch`/`add`/`drop`; manual edits always win). A scraper can observe
   absence, not closure.
History lives in the database's append-only `snapshots` table, not in git.
Nothing generated is committed.

## Crawl posture

Honest User-Agent with contact address, one request per second,
single-threaded, weekly (~40 requests per sweep). If a brand actively
challenges scraping, move it to a hand-maintained CSV in `data/manual/`
rather than escalating.

## Data

Committed — the hand-maintained inputs:

- `data/manual/<slug>.csv` — brands with no scrapable locator
- `data/overrides.csv` — hand edits merged after every scrape

Gitignored — everything the pipeline generates:

- `data/makhaa.sqlite` — the database. Rebuildable by re-scraping, except
  the append-only `snapshots` table, which is the run history and cannot
  be backfilled. Back it up rather than relying on git.
- `data/exports/` — CSV mirror of the database, rewritten every run
- `data/geo/`, `data/reports/` — caches and report output

## Development

```
uv run pytest
```

Scraper tests run offline against saved pages in `tests/fixtures/<brand>/`
(`manifest.json` maps URL → file). When a brand redesigns its site:
re-save the page over the fixture, fix the one scraper function, re-run.
