"""Offline parse check against a saved locator page.

When House of Mokhah redesigns its locator: re-save the fixture, fix the
scraper, and update the expectations here.
"""

from makhaa_report.scrapers.brands.house_of_mokhah import HouseOfMokhah


def test_house_of_mokhah_parses_its_store(fixture_fetch):
    rows = HouseOfMokhah.scrape(fixture_fetch("house_of_mokhah"))

    assert len(rows) == 1

    store = rows[0]
    assert store.street == "137 North Main Street"
    assert store.city == "Manteca"
    assert store.state == "CA"
    assert store.postal == "95336"
    assert store.brand == "house_of_mokhah"
