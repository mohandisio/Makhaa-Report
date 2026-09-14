"""Offline parse checks against saved app bundles.

These scrapers read minified JavaScript, so they are the most fragile in
the set. When one breaks: re-save the fixture slices, fix the pattern,
and update the expectations here.
"""

from makhaa_report.scrapers.brands.port import Port


def test_port_reads_store_records_from_the_bundle(fixture_fetch):
    rows = Port.scrape(fixture_fetch("port"))

    assert len(rows) == 6

    # Every record carries a Maps place link, so none need geocoding.
    assert all(r.lat is not None and r.lon is not None for r in rows)

    harvey = next(r for r in rows if r.city == "Harvey")
    assert harvey.street == "1901 Manhattan Blvd Bldg B, Suite 100"
    assert harvey.state == "LA"
    assert harvey.postal == "70058"
    assert harvey.phone == "(504) 264-7752"
    assert harvey.hours == (
        "Mon–Thu: 7 AM–10 PM; Fri: 7 AM–11 PM; Sat: 8 AM–11 PM; Sun: 8 AM–10 PM"
    )
    assert harvey.lat == 29.8863139
    assert harvey.lon == -90.0537436

    # No store carries a status field any more, so every one reads as open.
    assert {r.status for r in rows} == {"open"}

    # A record with no phone key still parses cleanly.
    greenville = next(r for r in rows if r.city == "Greenville")
    assert greenville.phone is None
