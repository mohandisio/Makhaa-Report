"""Offline parse checks against the saved Qahwah Drip home page.

When the brand redesigns its site: re-save the fixture, fix the scraper,
and update the expectations here.
"""

from makhaa_report.scrapers.brands.qahwah_drip import QahwahDrip


def test_qahwah_drip_reads_the_single_store(fixture_fetch):
    rows = QahwahDrip.scrape(fixture_fetch("qahwah_drip"))

    assert len(rows) == 1

    store = rows[0]
    assert store.street == "6315 Leesburg Pike, Ste A"
    assert store.city == "Falls Church"
    assert store.state == "VA"
    assert store.postal == "22044"
    assert store.status == "open"


def test_qahwah_drip_reads_coords_phone_and_hours(fixture_fetch):
    rows = QahwahDrip.scrape(fixture_fetch("qahwah_drip"))
    store = rows[0]

    assert store.lat == 38.870886
    assert store.lon == -77.155263
    assert store.phone == "+1-703-763-2111"
    assert store.hours == "Monday, Tuesday, Wednesday, Thursday: 09:00-23:00; Friday, Saturday: 09:00-24:00; Sunday: 09:00-23:00"
