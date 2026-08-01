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


def test_manual_entry_replaces_a_scraped_row(conn, manual_csv, monkeypatch):
    """A manual entry is the source of truth for the address it covers."""
    scraped = [
        RawLocation(brand="haraz", name="Scraped Name", street="123 Grand Ave",
                    city="Oakland", state="CA", postal="94610", status="open")
    ]
    monkeypatch.setitem(pipeline.SCRAPERS, "haraz", lambda fetch: scraped)

    # The manual CSV covers the same address under mohka_house, so the
    # two only collide when a brand shares it; use haraz's own entry.
    (manual_csv / "haraz.csv").write_text(
        ",".join(manual.MANUAL_FIELDS) + "\n"
        "Corrected Name,123 Grand Ave,Oakland,CA,94610,open,,,,,,\n"
    )

    pipeline.run_scrape(conn, fetch=_fetch_never_called, allow_drift=True)

    row = conn.execute(
        "SELECT name, is_manual FROM locations WHERE brand='haraz'"
    ).fetchone()
    assert row["name"] == "Corrected Name"
    assert row["is_manual"] == 1
    assert conn.execute(
        "SELECT COUNT(*) FROM locations WHERE brand='haraz'"
    ).fetchone()[0] == 1


def _run_with(conn, monkeypatch, manual_dir, scraped_rows, manual_csv_text):
    monkeypatch.setitem(pipeline.SCRAPERS, "haraz", lambda fetch: scraped_rows)
    (manual_dir / "haraz.csv").write_text(
        ",".join(manual.MANUAL_FIELDS) + "\n" + manual_csv_text
    )
    pipeline.run_scrape(conn, fetch=_fetch_never_called, allow_drift=True)
    return conn.execute("SELECT * FROM locations WHERE brand='haraz'").fetchall()


SCRAPED = RawLocation(
    brand="haraz", name="Dearborn", street="123 Grand Ave", city="Oakland",
    state="CA", postal="94610", status="open", lat=37.8, lon=-122.2,
    phone="(510) 111-2222", hours="Mon-Sun: 7-7",
)


def test_manual_entry_fills_blanks_and_keeps_scraped_detail(conn, manual_csv, monkeypatch):
    """Same address: the entry corrects what it states, nothing else."""
    rows = _run_with(
        conn, monkeypatch, manual_csv, [SCRAPED],
        # Only the name is supplied; everything else stays as scraped.
        "Corrected Name,123 Grand Ave,Oakland,CA,,,,,,,,\n",
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["name"] == "Corrected Name"
    assert row["is_manual"] == 1
    # The scraper's coordinates, phone and hours survive.
    assert (row["lat"], row["lon"]) == (37.8, -122.2)
    assert row["phone"] == "(510) 111-2222"
    assert row["hours"] == "Mon-Sun: 7-7"
    assert row["postal"] == "94610"


def test_manual_entry_corrects_a_wrong_address_without_losing_data(conn, manual_csv, monkeypatch):
    """A corrected street re-keys the row, so it is matched by name."""
    rows = _run_with(
        conn, monkeypatch, manual_csv, [SCRAPED],
        "Dearborn,901 K St,Sacramento,CA,95814,,,,,,,\n",
    )

    assert len(rows) == 1  # corrected, not duplicated
    row = rows[0]
    assert (row["street"], row["city"], row["postal"]) == ("901 K St", "Sacramento", "95814")
    # Everything the entry did not mention is still there.
    assert (row["lat"], row["lon"]) == (37.8, -122.2)
    assert row["hours"] == "Mon-Sun: 7-7"


def test_manual_entry_for_an_unknown_store_is_added(conn, manual_csv, monkeypatch):
    rows = _run_with(
        conn, monkeypatch, manual_csv, [SCRAPED],
        "Somewhere Else,1 Far St,Fresno,CA,93650,,,,,,,\n",
    )

    assert len(rows) == 2
    assert {r["city"] for r in rows} == {"Oakland", "Fresno"}
