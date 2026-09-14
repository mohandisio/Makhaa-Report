"""Offline parse check against a saved locator page.

When Biladi redesigns its locator: re-save the fixture, fix the scraper,
and update the expectations here.
"""

from makhaa_report.scrapers.brands.biladi import Biladi


def test_biladi_parses_its_store(fixture_fetch):
    rows = Biladi.scrape(fixture_fetch("biladi"))

    assert len(rows) == 1

    store = rows[0]
    assert store.street == "1185 Sweet Home Rd"
    assert store.city == "Buffalo"
    assert store.state == "NY"
    assert store.postal == "14226"
    assert store.brand == "biladi"
