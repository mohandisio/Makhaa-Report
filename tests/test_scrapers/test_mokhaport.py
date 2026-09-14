"""Offline parse checks against the saved Mokhaport home page.

When the brand redesigns its site: re-save the fixture, fix the scraper,
and update the expectations here.
"""

from makhaa_report.scrapers.brands.mokhaport import Mokhaport


def test_mokhaport_reads_structured_data(fixture_fetch):
    rows = Mokhaport.scrape(fixture_fetch("mokhaport"))

    assert len(rows) == 1

    store = rows[0]
    assert store.street == "1861 Mountain Industrial Blvd, Suite 106A"
    assert store.city == "Tucker"
    assert store.state == "GA"
    assert store.postal == "30084"
    assert store.status == "open"
    assert store.lat == 33.8379535
    assert store.lon == -84.2002513
    assert store.phone == "+16786918230"


def test_mokhaport_ignores_product_blocks(fixture_fetch):
    rows = Mokhaport.scrape(fixture_fetch("mokhaport"))

    # The page also carries two Product ld+json blocks for bean bags.
    # Those have no address, so a leak shows up as an extra row or one
    # with no street.
    assert all(r.brand == "mokhaport" for r in rows)
    assert all(r.street.strip() and r.city.strip() for r in rows)
