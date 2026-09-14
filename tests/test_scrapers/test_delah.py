"""Offline parse check against a saved locator page.

When Delah redesigns its locator: re-save the fixture, fix the scraper,
and update the expectations here.
"""

from makhaa_report.scrapers.brands.delah import Delah


def test_delah_reads_the_icon_list(fixture_fetch):
    rows = Delah.scrape(fixture_fetch("delah"))

    assert len(rows) == 7

    # Phone, email and social entries share the same markup and must not
    # become stores.
    assert all(r.street for r in rows)

    naperville = next(r for r in rows if r.city == "Naperville")
    assert naperville.street == "1336 Illinois Rte 59"
    assert naperville.state == "IL"

    # Two San Francisco stores stay distinct.
    assert sum(r.city == "San Francisco" for r in rows) == 2


def test_delah_takes_coordinates_only_from_place_links(fixture_fetch):
    rows = Delah.scrape(fixture_fetch("delah"))

    san_diego = next(r for r in rows if r.city == "San Diego")
    assert san_diego.lat == 32.7494607

    # The rest link to shortened g.co URLs, which carry no coordinates.
    assert sum(r.lat is None for r in rows) == 6
