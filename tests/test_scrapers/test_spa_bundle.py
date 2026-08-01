"""Offline parse checks against saved app bundles.

These scrapers read minified JavaScript, so they are the most fragile in
the set. When one breaks: re-save the fixture slices, fix the pattern,
and update the expectations here.
"""

from makhaa_report.registry import get_brand
from makhaa_report.scrapers.spa_bundle import scrape_port, scrape_qishr


def test_port_reads_store_records_from_the_bundle(fixture_fetch):
    rows = scrape_port(fixture_fetch("port"))

    low, high = get_brand("port").band
    assert low <= len(rows) <= high

    # Every record carries a Maps place link, so none need geocoding.
    assert all(r.lat is not None and r.lon is not None for r in rows)

    harvey = next(r for r in rows if r.city == "Harvey")
    assert harvey.street == "1901 Manhattan Blvd Bldg B, Suite 100"
    assert harvey.state == "LA"
    assert harvey.phone == "(504) 264-7752"
    assert harvey.hours.startswith("Mon–Thu:")

    # The bundle carries its own status field.
    assert {r.status for r in rows} == {"open"}


def test_qishr_reads_the_footer_address(fixture_fetch):
    rows = scrape_qishr(fixture_fetch("qishr"))

    low, high = get_brand("qishr").band
    assert low <= len(rows) <= high

    # The address is split across two string literals in the markup.
    store = rows[0]
    assert store.street == "90 Skyport Dr #140"
    assert (store.city, store.state, store.postal) == ("San Jose", "CA", "95110")
