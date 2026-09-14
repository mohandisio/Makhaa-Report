"""Offline parse checks against saved Yafa locator payloads.

When the brand redesigns its locator: re-save the fixture, fix the
scraper, and update the expectations here.
"""

from makhaa_report.scrapers.brands.yafa import Yafa


def test_yafa_reads_both_location_cards(fixture_fetch):
    rows = Yafa.scrape(fixture_fetch("yafa"))

    assert len(rows) == 2
    assert all(r.brand == "yafa" for r in rows)
    assert all(r.city == "Brooklyn" and r.state == "NY" for r in rows)
    assert all(r.status == "open" for r in rows)


def test_yafa_flagship_gets_its_zip_from_the_footer(fixture_fetch):
    rows = Yafa.scrape(fixture_fetch("yafa"))

    sunset_park = next(r for r in rows if r.street == "4415 4th Ave")
    assert (sunset_park.city, sunset_park.state, sunset_park.postal) == (
        "Brooklyn",
        "NY",
        "11220",
    )


def test_yafa_keeps_the_store_published_without_a_zip(fixture_fetch):
    rows = Yafa.scrape(fixture_fetch("yafa"))

    # Downtown Brooklyn's card carries no ZIP anywhere on the page, unlike
    # the flagship, which the footer's own contact block spells out.
    downtown = next(r for r in rows if r.street == "505 State St.")
    assert (downtown.city, downtown.state, downtown.postal) == (
        "Brooklyn",
        "NY",
        None,
    )


def test_yafa_ignores_the_sitewide_ld_json_and_the_photo_tile_links(fixture_fetch):
    rows = Yafa.scrape(fixture_fetch("yafa"))

    # The ld+json LocalBusiness block only names the flagship and would
    # under-count if it were the source of truth; the photo tiles repeat
    # the same two map links with no address text of their own. Neither
    # should add or duplicate a row.
    streets = sorted(r.street for r in rows)
    assert streets == ["4415 4th Ave", "505 State St."]
