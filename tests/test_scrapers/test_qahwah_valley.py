"""Offline parse checks against saved Qahwah Valley home-page payloads.

When the brand redesigns its site: re-save the fixture, fix the scraper,
and update the expectations here.
"""

from makhaa_report.scrapers.brands.qahwah_valley import QahwahValley


def test_qahwah_valley_reads_ld_json_locations(fixture_fetch):
    rows = QahwahValley.scrape(fixture_fetch("qahwah_valley"))

    assert len(rows) == 2
    assert all(r.brand == "qahwah_valley" for r in rows)
    assert all(r.lat is not None and r.lon is not None for r in rows)


def test_qahwah_valley_pinned_store(fixture_fetch):
    rows = QahwahValley.scrape(fixture_fetch("qahwah_valley"))

    manhattan = next(r for r in rows if r.street == "630 1st Avenue")
    assert manhattan.city == "Manhattan"
    assert manhattan.state == "NY"
    assert manhattan.postal == "10016"
    assert manhattan.status == "open"
    assert manhattan.phone == "+19179390628"
    assert manhattan.lat == 40.7453153
    assert manhattan.lon == -73.9718401


def test_qahwah_valley_ignores_the_website_block(fixture_fetch):
    rows = QahwahValley.scrape(fixture_fetch("qahwah_valley"))

    # The page also carries a plain WebSite ld+json block with no
    # location data; it must not leak a row with no street.
    assert all(r.street.strip() and r.city.strip() for r in rows)
