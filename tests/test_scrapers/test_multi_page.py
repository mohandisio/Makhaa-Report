"""Offline parse checks against saved locator pages.

When a brand redesigns its locator: re-save the fixture, fix the scraper,
and update the expectations here.
"""

from makhaa_report.registry import get_brand
from makhaa_report.scrapers.multi_page import scrape_haraz


def test_haraz_parses_every_state_page(fixture_fetch):
    rows = scrape_haraz(fixture_fetch("haraz"))

    low, high = get_brand("haraz").band
    assert low <= len(rows) <= high
    assert len({r.state for r in rows}) == 16

    # Discovered from the sitemap, so a new state page is picked up
    # without anyone editing a list.
    assert {r.source_url for r in rows} == {
        f"https://harazcoffeehouse.com/pages/{slug}-locations"
        for slug in (
            "california", "florida", "georgia", "illinois", "maryland",
            "michigan", "minnesota", "new-jersey", "new-york",
            "north-carolina", "pennsylvania", "south-carolina", "tennessee",
            "texas", "virginia", "wisconsin",
        )
    }


def test_haraz_ignores_the_stale_summary_page(fixture_fetch):
    rows = scrape_haraz(fixture_fetch("haraz"))

    assert not any("locations-and-hours" in r.source_url for r in rows)


def test_haraz_takes_coordinates_from_place_links(fixture_fetch):
    rows = scrape_haraz(fixture_fetch("haraz"))

    dearborn = next(r for r in rows if r.street == "13810 Michigan Ave")
    assert (dearborn.lat, dearborn.lon) == (42.3217038, -83.1786541)

    # Cards linking to a Maps *search* rather than a place carry no
    # coordinates; those rows fall through to the geocoder.
    minneapolis = next(r for r in rows if r.city == "Minneapolis")
    assert minneapolis.lat is None


def test_haraz_trusts_the_address_over_the_heading(fixture_fetch):
    rows = scrape_haraz(fixture_fetch("haraz"))

    # This store is headed "Plano" but sits in Pearland; the address wins.
    pearland = next(r for r in rows if r.street == "11401 Broadway St Ste 101")
    assert pearland.city == "Pearland"
