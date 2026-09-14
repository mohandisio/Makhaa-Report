"""Offline parse check against a saved locator page.

When Socotra redesigns its locator: re-save the fixture, fix the
scraper, and update the expectations here.
"""

from makhaa_report.scrapers.brands.socotra import Socotra


def test_socotra_parses_its_store(fixture_fetch):
    rows = Socotra.scrape(fixture_fetch("socotra"))

    assert len(rows) == 1

    store = rows[0]
    assert store.street == "3130 Packard St"
    assert store.city == "Ann Arbor"
    assert store.state == "MI"
    assert store.postal == "48108"
    assert store.brand == "socotra"
