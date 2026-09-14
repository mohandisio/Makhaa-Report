"""The smaller brands: one or two stores each, every site built
differently. Each test pins the quirk that made its scraper necessary.
"""

from makhaa_report.scrapers.brands.original_mocha import OriginalMocha


def test_original_mocha_finds_store_pages_by_slug(fixture_fetch):
    rows = OriginalMocha.scrape(fixture_fetch("original_mocha"))

    assert len(rows) == 2
    assert {r.city for r in rows} == {"Murphy", "Tinley Park"}
    # Each store's own page is its provenance, not the home page.
    assert all(r.source_url.rstrip("/").endswith(r.city.lower().replace(" ", "-") + {
        "Murphy": "-texas", "Tinley Park": "-illinois"}[r.city]) for r in rows)
