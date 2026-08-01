# makhaa-report

Census of US Yemeni coffee chain locations, scraped weekly from each
brand's own store locator into SQLite + CSVs, with a self-contained HTML
report generated from the database.

22 brands tracked. All but Mohka House are scraped; it has no website of
its own, so its stores arrive by manual entry. See
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
challenges scraping, move it to manual entry in `data/manual/`
rather than escalating.

## Data

Nothing under `data/` is committed. Back the directory up — git will not
do it for you.

- `data/makhaa.sqlite` — the database. Re-scraping rebuilds the scraped
  rows, but the append-only `snapshots` table is the run history and
  cannot be backfilled.
- `data/manual/<slug>.csv` — manual entries, written by `manual-entry`.
  The source of truth for the rows they cover, and unrecoverable if lost.
- `data/overrides.csv` — hand corrections, applied last.
- `data/exports/` — CSV mirror, rewritten every run.
- `data/geo/`, `data/reports/` — caches and report output.

## How a row is decided

1. Scrapers run; two scraped rows sharing a uid means something is wrong,
   so the first wins and the run says so.
2. Manual entries land on top. A manual row for an address a scraper also
   found **replaces** it — somebody checked that one by hand.
3. `overrides.csv` applies last, so a correction beats everything.

The uid is a hash of brand plus normalized address, which is what lets a
manual entry line up with the scraped row it corrects.

## Development

```
uv run pytest
```

Scraper tests run offline against saved pages in `tests/fixtures/<brand>/`
(`manifest.json` maps URL → file). When a brand redesigns its site:
re-save the page over the fixture, fix the one scraper function, re-run.
