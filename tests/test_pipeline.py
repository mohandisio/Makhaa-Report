"""Scrape-twice idempotency and drift quarantine — the two invariants
worth automating (spec Done-when #2 and #4)."""

import sqlite3

import pytest

from makhaa_report import db, manual, pipeline
from makhaa_report.models import RawLocation


@pytest.fixture
def conn(tmp_path):
    return db.connect(tmp_path / "test.sqlite")


@pytest.fixture
def manual_csv(tmp_path, monkeypatch):
    manual_dir = tmp_path / "manual"
    manual_dir.mkdir()
    (manual_dir / "mohka_house.csv").write_text(
        ",".join(manual.MANUAL_FIELDS) + "\n"
        "Mohka House,123 Grand Ave,Oakland,CA,94610,open,,,,,,\n"
    )
    monkeypatch.setattr("makhaa_report.config.MANUAL_DIR", manual_dir)
    monkeypatch.setattr("makhaa_report.config.OVERRIDES_PATH", tmp_path / "overrides.csv")
    monkeypatch.setattr("makhaa_report.config.EXPORT_DIR", tmp_path / "exports")
    return manual_dir


def _fetch_never_called(url: str) -> str:
    raise AssertionError(f"network fetch attempted in test: {url}")


def test_scrape_twice_locations_unchanged(conn, manual_csv):
    s1 = pipeline.run_scrape(conn, fetch=_fetch_never_called)
    s2 = pipeline.run_scrape(conn, fetch=_fetch_never_called)

    count = conn.execute("SELECT COUNT(*) FROM locations").fetchone()[0]
    assert count == 1  # idempotent: same store, one row
    snaps = conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
    assert snaps == 2  # append-only observation log grows per run

    row = conn.execute("SELECT first_seen, last_seen FROM locations").fetchone()
    assert row["first_seen"] <= row["last_seen"]
    assert s1.run_id != s2.run_id


def test_drift_quarantines_brand_only(conn, manual_csv, monkeypatch):
    too_few = [
        RawLocation(brand="haraz", name="Only One", street="1 Test St",
                    city="Dearborn", state="MI", status="open")
    ]
    monkeypatch.setitem(pipeline.SCRAPERS, "haraz", lambda fetch: too_few)

    stats = pipeline.run_scrape(conn, fetch=_fetch_never_called)

    assert "haraz" in stats.brands_failed  # 1 row vs band (55, 75)
    haraz_rows = conn.execute(
        "SELECT COUNT(*) FROM locations WHERE brand='haraz'"
    ).fetchone()[0]
    assert haraz_rows == 0  # quarantined: nothing written
    assert stats.total_rows == 1  # manual brand still landed
