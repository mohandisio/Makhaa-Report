"""Offline parse check against the saved locator page."""

from makhaa_report.scrapers.brands.qishr import Qishr


def test_qishr_reads_the_address_block(fixture_fetch):
    rows = Qishr.scrape(fixture_fetch("qishr"))

    assert len(rows) == 1

    store = rows[0]
    assert store.street == "90 Skyport Dr #140"
    assert (store.city, store.state, store.postal) == ("San Jose", "CA", "95110")
    assert store.status == "open"
