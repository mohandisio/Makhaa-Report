"""Offline parse check against a saved locator page.

When Sana'a Cafe redesigns its locator: re-save the fixture, fix the
scraper, and update the expectations here.
"""

from makhaa_report.scrapers.brands.sanaa_cafe import SanaaCafe


def test_sanaa_reads_the_current_location_cards(fixture_fetch):
    rows = SanaaCafe.scrape(fixture_fetch("sanaa_cafe"))

    assert len(rows) == 8

    flagship = next(r for r in rows if r.city == "San Francisco")
    assert flagship.street == "199 New Montgomery St"
    assert flagship.phone == "+1 (415) 932-6935"
    assert flagship.hours == "Mon-Sun: 6:00 AM - 12:00 AM"

    # The cards carry Sacramento's real address; the older blurb layout
    # still on the page gives it Oakland Broadway's, and is ignored.
    sacramento = next(r for r in rows if r.city == "Sacramento")
    assert sacramento.street == "901 K St"
    assert sum(r.street == "801 Broadway" for r in rows) == 1


def test_sanaa_handles_a_run_together_zip_plus_four(fixture_fetch):
    rows = SanaaCafe.scrape(fixture_fetch("sanaa_cafe"))

    # Published as "LAKE FOREST CA, 926301791, US".
    lake_forest = next(r for r in rows if r.city.casefold() == "lake forest")
    assert lake_forest.postal == "92630"
