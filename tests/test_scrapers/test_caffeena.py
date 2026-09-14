"""Offline parse check against a saved locator page.

When Caffeena redesigns its locator: re-save the fixture, fix the
scraper, and update the expectations here.
"""

from makhaa_report.scrapers.brands.caffeena import Caffeena


def test_caffeena_reads_status_from_the_section_heading(fixture_fetch):
    rows = Caffeena.scrape(fixture_fetch("caffeena"))

    assert len(rows) == 7

    # One trading store, the rest announced under "Coming Soon Locations".
    open_rows = [r for r in rows if r.status == "open"]
    assert len(open_rows) == 1
    assert open_rows[0].street == "3101 Griffith St"
    assert sum(r.status == "coming_soon" for r in rows) == 6

    # Both Charlotte stores are listed, one per section.
    charlotte = [r for r in rows if r.city == "Charlotte"]
    assert {r.status for r in charlotte} == {"open", "coming_soon"}
