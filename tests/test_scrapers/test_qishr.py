"""Offline parse checks against saved app bundles.

These scrapers read minified JavaScript, so they are the most fragile in
the set. When one breaks: re-save the fixture slices, fix the pattern,
and update the expectations here.
"""

from makhaa_report.scrapers.brands.qishr import Qishr


def test_qishr_reads_the_footer_address(fixture_fetch):
    rows = Qishr.scrape(fixture_fetch("qishr"))

    assert len(rows) == 1

    # The address is split across two string literals in the markup.
    store = rows[0]
    assert store.street == "90 Skyport Dr #140"
    assert (store.city, store.state, store.postal) == ("San Jose", "CA", "95110")
