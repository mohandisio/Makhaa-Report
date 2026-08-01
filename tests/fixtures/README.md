# Locator fixtures

One directory per brand. `manifest.json` maps each URL the scraper
requests to a saved file, so tests run entirely offline.

## Fixtures are trimmed, not saved verbatim

A brand's locator page is mostly theme markup, inline CSS, and menus —
Moka & Co's is 460 KB, of which the scraper reads a few hundred bytes.
Committing pages whole buries every code review under thousands of lines
of vendored HTML, so fixtures keep only what the scraper looks at:

- **HTML**: the locator markup, plus anything a test asserts is *ignored*
  (Moka's corporate contact block is kept so the test proving HQ addresses
  aren't counted as stores still means something). Scripts, styles, images
  and `style` attributes are stripped.
- **JSON**: every record, but only the fields the scraper reads,
  pretty-printed so a diff is legible.

Every store the live page lists is kept. That way the row count stays
honest and a parser change that quietly drops rows fails the tests — which
is how the numbered-route address bug was caught.

What this deliberately gives up: a redesign that only touches the
surrounding page structure won't fail a test. The per-brand row-count band
on the live scrape catches that instead.

## Refreshing a fixture after a redesign

1. Fetch the live page and confirm what changed.
2. Trim it the same way — locator markup only — and overwrite the file.
3. Fix the scraper and update the expectations in
   `tests/test_scrapers/`.
4. Re-run the live scrape and reset the brand's band in `registry.py` if
   the real count moved.
