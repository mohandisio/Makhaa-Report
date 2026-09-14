"""Offline parse checks against saved Qamaria locator payloads.

When the brand redesigns its locator: re-save the fixture, fix the
scraper, and update the expectations here.
"""

import json

from makhaa_report.scrapers.brands.qamaria import Qamaria


def test_qamaria_parses_us_cafes(fixture_fetch):
    rows = Qamaria.scrape(fixture_fetch("qamaria"))

    assert len(rows) == 51

    allen_park = next(r for r in rows if r.city == "Allen Park")
    assert allen_park.street == "7706 Allen Rd"
    assert allen_park.state == "MI"
    assert allen_park.postal == "48101"
    assert allen_park.phone == "(313) 406-6911"
    assert allen_park.lat == 42.252666
    assert allen_park.hours.startswith("monday: 8am - 10pm")


def test_qamaria_excludes_catering_and_non_us(fixture_fetch):
    rows = Qamaria.scrape(fixture_fetch("qamaria"))

    # The fixture carries 14 catering-tagged records (of 71 total) — a
    # service-area listing that reuses a real cafe's address. `add()`
    # dedupes on (street, city, state), so a leaked catering row would be
    # silently collapsed rather than show up as a duplicate; check the
    # fragment (the raw record JSON) directly instead.
    fragments = [json.loads(r.fragment) for r in rows]
    assert not any("catering" in (f.get("tags") or "") for f in fragments)
    # Canada, Saudi Arabia and Qatar are out of scope.
    assert {r.state for r in rows} <= set(
        "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN "
        "MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA "
        "WA WV WI WY DC".split()
    )
