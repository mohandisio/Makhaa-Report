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
    assert harvey.phone == "(504) 264-7752"
    assert harvey.hours.startswith("Mon–Thu:")

    # The bundle carries its own status field.
    assert {r.status for r in rows} == {"open"}
