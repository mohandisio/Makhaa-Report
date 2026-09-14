"""Offline parse checks against saved locator pages.

When a brand redesigns its locator: re-save the fixture, fix the scraper,
and update the expectations here.
"""

from makhaa_report.scrapers.single_page import (
    scrape_caffeena,
    scrape_mokafe,
)


def test_caffeena_reads_status_from_the_section_heading(fixture_fetch):
    rows = scrape_caffeena(fixture_fetch("caffeena"))

    assert len(rows) == 7

    # One trading store, the rest announced under "Coming Soon Locations".
    open_rows = [r for r in rows if r.status == "open"]
    assert len(open_rows) == 1
    assert open_rows[0].street == "3101 Griffith St"
    assert sum(r.status == "coming_soon" for r in rows) == 6

    # Both Charlotte stores are listed, one per section.
    charlotte = [r for r in rows if r.city == "Charlotte"]
    assert {r.status for r in charlotte} == {"open", "coming_soon"}


def test_mokafe_splits_name_from_address(fixture_fetch):
    rows = scrape_mokafe(fixture_fetch("mokafe"))

    assert len(rows) == 10

    paterson = next(r for r in rows if r.city == "Paterson")
    assert paterson.street == "1022 Main St"

    # One store carries no colon, so the bullet separates the label from
    # the address instead.
    melville = next(r for r in rows if r.city == "Melville")
    assert melville.street == "606 Broadhollow Rd"

    # Two Brooklyn stores share Manhattan Ave; both must survive.
    manhattan_ave = [r for r in rows if r.street.endswith("Manhattan Ave")]
    assert len(manhattan_ave) == 2


