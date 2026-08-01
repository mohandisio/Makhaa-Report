"""Offline parse checks against saved locator payloads.

When a brand redesigns its locator: re-save the fixture, fix the scraper,
and update the expectations here.
"""

from makhaa_report.registry import get_brand
from makhaa_report.scrapers.json_sites import scrape_qamaria


def test_qamaria_parses_us_cafes(fixture_fetch):
    rows = scrape_qamaria(fixture_fetch("qamaria"))

    low, high = get_brand("qamaria").band
    assert low <= len(rows) <= high

    allen_park = next(r for r in rows if r.city == "Allen Park")
    assert allen_park.street == "7706 Allen Rd"
    assert allen_park.state == "MI"
    assert allen_park.postal == "48101"
    assert allen_park.phone == "(313) 406-6911"
    assert allen_park.lat == 42.252666
    assert allen_park.hours.startswith("monday: 8am - 10pm")


def test_qamaria_excludes_catering_and_non_us(fixture_fetch):
    rows = scrape_qamaria(fixture_fetch("qamaria"))

    # Service-area listings reuse a real cafe's address; counting them
    # would inflate every Qamaria figure.
    assert not any(r.name.endswith(" Area") for r in rows)
    # Canada, Saudi Arabia and Qatar are out of scope.
    assert {r.state for r in rows} <= set(
        "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN "
        "MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA "
        "WA WV WI WY DC".split()
    )
