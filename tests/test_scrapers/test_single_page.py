"""Offline parse checks against saved locator pages.

When a brand redesigns its locator: re-save the fixture, fix the scraper,
and update the expectations here.
"""

from makhaa_report.scrapers.single_page import (
    scrape_mokafe,
)


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


