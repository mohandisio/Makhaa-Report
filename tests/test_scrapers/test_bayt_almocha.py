"""Offline parse checks against a saved Bayt Almocha /find-location page.

When the brand redesigns its locator: re-save the fixture, fix the
scraper, and update the expectations here.
"""

from makhaa_report.scrapers.brands.bayt_almocha import BaytAlmocha


def test_bayt_almocha_reads_the_inline_static_points_array(fixture_fetch):
    rows = BaytAlmocha.scrape(fixture_fetch("bayt_almocha"))

    assert len(rows) == 7

    # Every record carries its own lat/lng, so none need geocoding.
    assert all(r.lat is not None and r.lon is not None for r in rows)

    cardinal = next(r for r in rows if r.street == "327 W Cardinal Blvd")
    assert cardinal.city == "Louisville"
    assert cardinal.state == "KY"
    assert cardinal.postal == "40208"
    assert cardinal.status == "open"
    assert cardinal.lat == 38.2208219
    assert cardinal.lon == -85.7621949


def test_bayt_almocha_keeps_a_row_with_no_comma_before_the_city(fixture_fetch):
    rows = BaytAlmocha.scrape(fixture_fetch("bayt_almocha"))

    # "1541 Highland Avenue Louisville, KY, 40204 USA" has no comma
    # separating the street from the city; split_us_address still finds
    # the cut on the street-type token.
    highland = next(r for r in rows if r.street == "1541 Highland Avenue")
    assert (highland.city, highland.state, highland.postal) == (
        "Louisville",
        "KY",
        "40204",
    )


def test_bayt_almocha_keeps_the_row_with_two_published_zips(fixture_fetch):
    rows = BaytAlmocha.scrape(fixture_fetch("bayt_almocha"))

    # "655 S 4th St, Louisville, KY 40202, 40204 USA" carries a second
    # ZIP glued onto the tail; the one next to the state is kept and the
    # second is dropped rather than losing the row every run.
    fourth = next(r for r in rows if r.street == "655 S 4th St")
    assert (fourth.city, fourth.state, fourth.postal) == (
        "Louisville",
        "KY",
        "40202",
    )
