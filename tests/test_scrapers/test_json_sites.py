"""Offline parse checks against saved locator payloads.

When a brand redesigns its locator: re-save the fixture, fix the scraper,
and update the expectations here.
"""

from makhaa_report.scrapers.json_sites import (
    scrape_qahwah_house,
    scrape_qamaria,
    scrape_shibam,
)


def test_qamaria_parses_us_cafes(fixture_fetch):
    rows = scrape_qamaria(fixture_fetch("qamaria"))

    assert len(rows) == 51

    allen_park = next(r for r in rows if r.city == "Allen Park")
    assert allen_park.street == "7706 Allen Rd"
    assert allen_park.state == "MI"
    assert allen_park.postal == "48101"
    assert allen_park.phone == "(313) 406-6911"
    assert allen_park.lat == 42.252666
    assert allen_park.hours.startswith("monday: 8am - 10pm")


def test_qamaria_excludes_catering_and_non_us(fixture_fetch):
    rows = scrape_qamaria(fixture_fetch("qamaria"))

    # Service-area listings reuse a real cafe's address — "Bay Area" and
    # "Fremont, CA" both carry 4193 Cushing Pkwy — so one leaking through
    # shows up as a duplicate address, not just an extra row.
    addresses = [(r.street, r.city) for r in rows]
    assert len(addresses) == len(set(addresses))
    # Canada, Saudi Arabia and Qatar are out of scope.
    assert {r.state for r in rows} <= set(
        "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN "
        "MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA "
        "WA WV WI WY DC".split()
    )


def test_qahwah_house_reads_structured_data(fixture_fetch):
    rows = scrape_qahwah_house(fixture_fetch("qahwah_house"))

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
    rows = scrape_qahwah_house(fixture_fetch("qahwah_house"))

    # Several stores are published as "street, city, ST, USA".
    ann_arbor = next(r for r in rows if r.city == "Ann Arbor")
    assert (ann_arbor.street, ann_arbor.state, ann_arbor.postal) == (
        "211 North Maple Road",
        "MI",
        None,
    )


def test_qahwah_house_ignores_non_store_blocks(fixture_fetch):
    rows = scrape_qahwah_house(fixture_fetch("qahwah_house"))

    # The page also carries Organization and BreadcrumbList blocks.
    assert all(r.brand == "qahwah_house" for r in rows)
    # Those blocks carry no postal address, so a leak shows up as a row
    # with no street.
    assert all(r.street.strip() and r.city.strip() for r in rows)


def test_shibam_parses_cards_from_rendered_html(fixture_fetch):
    rows = scrape_shibam(fixture_fetch("shibam"))

    assert len(rows) == 20

    dearborn = next(r for r in rows if r.street == "5461 Schaefer Rd")
    assert dearborn.city == "Dearborn"
    assert dearborn.state == "MI"
    assert dearborn.postal == "48126"
    assert dearborn.phone == "+13136331624"
    assert dearborn.hours.startswith("Sun – Thu:")


def test_shibam_reads_status_from_prose(fixture_fetch):
    rows = scrape_shibam(fixture_fetch("shibam"))

    # Announced with wording, not a marker: "Soft opening coming soon!!"
    ann_arbor = next(r for r in rows if r.city == "Ann Arbor")
    assert ann_arbor.status == "coming_soon"
    assert sum(r.status == "coming_soon" for r in rows) == 1


def test_shibam_trusts_the_address_over_the_heading(fixture_fetch):
    rows = scrape_shibam(fixture_fetch("shibam"))

    # Headings are regional labels: this card is headed "CLEVELAND, OH"
    # but the address is the truth.
    north_olmsted = next(r for r in rows if r.street == "26745 Brookpark Ext")
    assert north_olmsted.city == "North Olmsted"
