"""Offline parse check against a saved locator page.

When Queen redesigns its locator: re-save the fixture, fix the scraper,
and update the expectations here.
"""

from makhaa_report.scrapers.brands.queen import Queen


def test_queen_parses_its_store(fixture_fetch):
    rows = Queen.scrape(fixture_fetch("queen"))

    assert len(rows) == 1

    store = rows[0]
    assert store.street == "4753 N. Broadway"
    assert store.city == "Chicago"
    assert store.state == "IL"
    assert store.postal == "60640"
    assert store.brand == "queen"
