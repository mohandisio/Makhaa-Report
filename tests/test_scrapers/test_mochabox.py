"""Offline parse check against a saved locator page.

When MochaBox redesigns its locator: re-save the fixture, fix the
scraper, and update the expectations here.
"""

from makhaa_report.scrapers.brands.mochabox import Mochabox


def test_mochabox_parses_its_store(fixture_fetch):
    rows = Mochabox.scrape(fixture_fetch("mochabox"))

    assert len(rows) == 1

    store = rows[0]
    assert store.street == "1050 Haywood Rd"
    assert store.city == "Asheville"
    assert store.state == "NC"
    assert store.postal is None
    assert store.brand == "mochabox"


def test_mochabox_drops_its_six_digit_postcode(fixture_fetch):
    rows = Mochabox.scrape(fixture_fetch("mochabox"))

    # The site publishes "Asheville, NC 208806". Truncating that to a
    # five-digit ZIP would invent a plausible-looking wrong postcode.
    assert rows[0].postal is None
