"""Offline parse checks against a saved Albunn Coffee House home page.

When the brand redesigns its site: re-save the fixture, fix the scraper,
and update the expectations here.
"""

from makhaa_report.scrapers.brands.albunn import Albunn


def test_albunn_reads_the_root_restaurant_block(fixture_fetch):
    rows = Albunn.scrape(fixture_fetch("albunn"))

    assert len(rows) == 1

    store = rows[0]
    assert store.street == "333 East Ave"
    assert store.city == "Rochester"
    assert store.state == "NY"
    assert store.postal == "14604"
    assert store.status == "open"


def test_albunn_reads_coords_and_phone(fixture_fetch):
    rows = Albunn.scrape(fixture_fetch("albunn"))

    store = rows[0]
    assert store.lat == 43.155015
    assert store.lon == -77.595546
    assert store.phone == "5853194030"
