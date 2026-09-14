"""Offline parse check against a saved locator page.

When Yemerica redesigns its locator: re-save the fixture, fix the
scraper, and update the expectations here.
"""

from makhaa_report.scrapers.brands.yemerica import Yemerica


def test_yemerica_parses_the_open_flagship(fixture_fetch):
    rows = Yemerica.scrape(fixture_fetch("yemerica"))

    assert len(rows) == 1

    flagship = rows[0]
    assert flagship.street == "1000 Farmington Ave, Suite 100"
    assert flagship.city == "West Hartford"
    assert flagship.state == "CT"
    assert flagship.postal == "06107"
    assert flagship.status == "open"


def test_yemerica_skips_coming_soon_placeholders_without_a_street(fixture_fetch):
    rows = Yemerica.scrape(fixture_fetch("yemerica"))

    # Southington, Orange CT, Storrs UCONN, West Springfield MA and the
    # unnamed Rhode Island card are all announced with a bare state name,
    # never a street address, so none of them produce a row.
    assert not any(r.city != "West Hartford" for r in rows)
