"""Offline parse checks against a saved Mocha Point Coffee locations page.

When the brand redesigns its locator: re-save the fixture, fix the
scraper, and update the expectations here.
"""

from makhaa_report.scrapers.brands.mocha_point import MochaPoint


def test_mocha_point_reads_the_one_published_store(fixture_fetch):
    rows = MochaPoint.scrape(fixture_fetch("mocha_point"))

    assert len(rows) == 1

    saint_charles = rows[0]
    assert saint_charles.street == "343 N Main St."
    assert saint_charles.city == "Saint Charles"
    assert saint_charles.state == "MO"
    assert saint_charles.postal == "63301"
    assert saint_charles.status == "open"


def test_mocha_point_drops_the_addressless_kansas_unit(fixture_fetch):
    # The nav lists a second unit, "Kansas", linked only to an Instagram
    # profile. The page publishes no street address for it anywhere, so
    # it must not turn into a fabricated row.
    rows = MochaPoint.scrape(fixture_fetch("mocha_point"))

    assert not any(r.city == "Kansas" for r in rows)
    assert not any("instagram" in (r.fragment or "").casefold() for r in rows)
