"""Offline parse check against a saved locator page.

When Emari Roast redesigns its locations page: re-save the fixture, fix
the scraper, and update the expectations here.
"""

from makhaa_report.scrapers.brands.emari_roast import EmariRoast


def test_emari_roast_skips_the_coming_soon_teasers(fixture_fetch):
    rows = EmariRoast.scrape(fixture_fetch("emari_roast"))

    assert len(rows) == 1

    troy = rows[0]
    assert troy.street == "987 Wilshire Dr Suite C"
    assert troy.city == "Troy"
    assert troy.state == "MI"
    assert troy.postal == "48084"
    assert troy.status == "open"

    # New York / Dallas TX / Chicago IL are named with no street address;
    # they must not turn into rows.
    assert {r.city for r in rows} == {"Troy"}
