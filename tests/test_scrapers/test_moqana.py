"""Offline parse checks against saved MoQana Coffee locator payloads.

When the brand redesigns its locator: re-save the fixture, fix the
scraper, and update the expectations here.
"""

import json

from makhaa_report.scrapers.brands.moqana import Moqana


def test_moqana_parses_locations(fixture_fetch):
    rows = Moqana.scrape(fixture_fetch("moqana"))

    assert len(rows) == 3

    edmond = next(r for r in rows if r.city == "Edmond")
    assert edmond.street == "432 S Santa Fe Ave"
    assert edmond.state == "OK"
    assert edmond.postal == "73003"
    assert edmond.status == "open"
    assert edmond.phone == "4059062268"
    assert edmond.lat == 35.65181
    assert edmond.lon == -97.51381
    assert edmond.hours.startswith("Mon-Thurs 7am-10pm")


def test_moqana_status_field_drives_coming_soon(fixture_fetch):
    rows = Moqana.scrape(fixture_fetch("moqana"))

    # The API's `status` field carries "coming_soon"/"open" directly; the
    # separate `active` boolean is true on every record in this snapshot
    # (including the coming-soon one), so it cannot be the status signal —
    # `status` is. Also checks the trailing double space on Norman's raw
    # address string doesn't survive into the parsed street.
    norman = next(r for r in rows if r.city == "Norman")
    assert norman.status == "coming_soon"
    assert norman.street == "1808 W Lindsey St"

    fragments = [json.loads(r.fragment) for r in rows]
    assert all(f["active"] is True for f in fragments)
