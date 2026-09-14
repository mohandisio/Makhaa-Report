"""Offline parse checks against saved Qahwah House locator payloads.

When the brand redesigns its locator: re-save the fixture, fix the
scraper, and update the expectations here.
"""

from makhaa_report.scrapers.brands.qahwah_house import QahwahHouse


def test_qahwah_house_reads_structured_data(fixture_fetch):
    rows = QahwahHouse.scrape(fixture_fetch("qahwah_house"))

    assert len(rows) == 26

    # Every store publishes coordinates, so none of these need geocoding.
    assert all(r.lat is not None and r.lon is not None for r in rows)

    west_dearborn = next(r for r in rows if r.street == "22000 Michigan Ave")
    assert west_dearborn.city == "Dearborn"
    assert west_dearborn.state == "MI"
    assert west_dearborn.postal == "48124"
    assert west_dearborn.phone == "(313) 427-8928"
    assert west_dearborn.lat == 42.3064061


def test_qahwah_house_keeps_stores_published_without_a_zip(fixture_fetch):
    rows = QahwahHouse.scrape(fixture_fetch("qahwah_house"))

    # Several stores are published as "street, city, ST, USA".
    ann_arbor = next(r for r in rows if r.city == "Ann Arbor")
    assert (ann_arbor.street, ann_arbor.state, ann_arbor.postal) == (
        "211 North Maple Road",
        "MI",
        None,
    )


def test_qahwah_house_ignores_non_store_blocks(fixture_fetch):
    rows = QahwahHouse.scrape(fixture_fetch("qahwah_house"))

    # The page also carries Organization and BreadcrumbList blocks.
    assert all(r.brand == "qahwah_house" for r in rows)
    # Those blocks carry no postal address, so a leak shows up as a row
    # with no street.
    assert all(r.street.strip() and r.city.strip() for r in rows)
