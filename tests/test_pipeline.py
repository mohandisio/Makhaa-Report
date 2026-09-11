"""Scrape-twice idempotency, and what happens when a scraper misbehaves."""

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
    _manual_csv(manual_dir / "mohka_house.csv", street="123 Grand Ave",
                city="Oakland", state="CA", postal="94610", status="open")
    monkeypatch.setattr("makhaa_report.config.MANUAL_DIR", manual_dir)
    monkeypatch.setattr("makhaa_report.config.OVERRIDES_PATH", tmp_path / "overrides.csv")
    monkeypatch.setattr("makhaa_report.config.EXPORT_DIR", tmp_path / "exports")
    return manual_dir


def _fetch_never_called(url: str) -> str:
    raise AssertionError(f"network fetch attempted in test: {url}")


def _manual_row(**fields: str) -> str:
    """One manual CSV line, written by field name rather than by position."""
    unknown = set(fields) - set(manual.MANUAL_FIELDS)
    assert not unknown, f"not manual fields: {unknown}"
    return ",".join(fields.get(f, "") for f in manual.MANUAL_FIELDS) + "\n"


def _manual_csv(path, **fields: str) -> None:
    path.write_text(",".join(manual.MANUAL_FIELDS) + "\n" + _manual_row(**fields))


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


def test_a_short_scrape_is_written_not_rejected(conn, manual_csv, monkeypatch):
    """Whatever a scraper returns is what the brand has that run.

    There is no expected row count to measure against: a count in range
    proves nothing about whether the rows are the right rows. A scraper
    that returns one store writes one store, and the sixty it did not
    return keep their old last_seen rather than being deleted.
    """
    one_row = [
        RawLocation(brand="haraz", street="1 Test St",
                    city="Dearborn", state="MI", status="open")
    ]
    monkeypatch.setitem(pipeline.SCRAPERS, "haraz", lambda fetch: one_row)

    stats = pipeline.run_scrape(conn, fetch=_fetch_never_called)

    assert "haraz" not in stats.brands_failed
    haraz_rows = conn.execute(
        "SELECT COUNT(*) FROM locations WHERE brand='haraz'"
    ).fetchone()[0]
    assert haraz_rows == 1


def test_a_raising_scraper_fails_the_brand_and_writes_nothing(conn, manual_csv, monkeypatch):
    def broken(fetch):
        raise RuntimeError("locator rebuilt")

    monkeypatch.setitem(pipeline.SCRAPERS, "haraz", broken)

    stats = pipeline.run_scrape(conn, fetch=_fetch_never_called)

    assert "haraz" in stats.brands_failed
    haraz_rows = conn.execute(
        "SELECT COUNT(*) FROM locations WHERE brand='haraz'"
    ).fetchone()[0]
    assert haraz_rows == 0


def test_manual_entry_replaces_a_scraped_row(conn, manual_csv, monkeypatch):
    """A manual entry is the source of truth for the address it covers."""
    scraped = [
        RawLocation(brand="haraz", street="123 Grand Ave",
                    city="Oakland", state="CA", postal="94610", status="open")
    ]
    monkeypatch.setitem(pipeline.SCRAPERS, "haraz", lambda fetch: scraped)

    # The manual CSV covers the same address under mohka_house, so the
    # two only collide when a brand shares it; use haraz's own entry.
    _manual_csv(manual_csv / "haraz.csv", street="123 Grand Ave", city="Oakland",
                state="CA", postal="94610", status="open",
                status_note="checked by hand")

    pipeline.run_scrape(conn, fetch=_fetch_never_called)

    row = conn.execute(
        "SELECT status_note, is_manual FROM locations WHERE brand='haraz'"
    ).fetchone()
    assert row["status_note"] == "checked by hand"
    assert row["is_manual"] == 1
    assert conn.execute(
        "SELECT COUNT(*) FROM locations WHERE brand='haraz'"
    ).fetchone()[0] == 1


def _run_with(conn, monkeypatch, manual_dir, scraped_rows, **entry):
    monkeypatch.setitem(pipeline.SCRAPERS, "haraz", lambda fetch: scraped_rows)
    _manual_csv(manual_dir / "haraz.csv", **entry)
    pipeline.run_scrape(conn, fetch=_fetch_never_called)
    return conn.execute("SELECT * FROM locations WHERE brand='haraz'").fetchall()


SCRAPED = RawLocation(
    brand="haraz", street="123 Grand Ave", city="Oakland",
    state="CA", postal="94610", status="open", lat=37.8, lon=-122.2,
    phone="(510) 111-2222", hours="Mon-Sun: 7-7",
)


def test_manual_entry_fills_blanks_and_keeps_scraped_detail(conn, manual_csv, monkeypatch):
    """Same address: the entry corrects what it states, nothing else."""
    rows = _run_with(
        conn, monkeypatch, manual_csv, [SCRAPED],
        # Only the note is supplied; everything else stays as scraped.
        street="123 Grand Ave", city="Oakland", state="CA",
        status_note="checked by hand",
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["status_note"] == "checked by hand"
    assert row["is_manual"] == 1
    # The scraper's coordinates, phone and hours survive.
    assert (row["lat"], row["lon"]) == (37.8, -122.2)
    assert row["phone"] == "(510) 111-2222"
    assert row["hours"] == "Mon-Sun: 7-7"
    assert row["postal"] == "94610"


def test_manual_entry_corrects_a_wrong_address_without_losing_data(conn, manual_csv, monkeypatch):
    """A corrected street and city re-key the row, so the house number matches it.

    This is the real shape of a correction: matari publishes
    "285 South Broadway, Long Isand" for a store on S Broadway in
    Hicksville. Street and city are both wrong; 285 and NY are not.
    """
    rows = _run_with(
        conn, monkeypatch, manual_csv, [SCRAPED],
        street="123 Grand Blvd", city="Piedmont", state="CA", postal="94611",
    )

    assert len(rows) == 1  # corrected, not duplicated
    row = rows[0]
    assert (row["street"], row["city"], row["postal"]) == ("123 Grand Blvd", "Piedmont", "94611")
    # Everything the entry did not mention is still there.
    assert (row["lat"], row["lon"]) == (37.8, -122.2)
    assert row["hours"] == "Mon-Sun: 7-7"


def test_a_wholly_different_address_is_a_new_store(conn, manual_csv, monkeypatch):
    """The limit of address matching, recorded on purpose.

    Nothing links "123 Grand Ave, Oakland" to "901 K St, Sacramento" —
    not the uid, not the house number, and the entry supplies no phone.
    Adding a row is the safe reading; merging would be a guess.
    """
    rows = _run_with(
        conn, monkeypatch, manual_csv, [SCRAPED],
        street="901 K St", city="Sacramento", state="CA", postal="95814",
    )

    assert len(rows) == 2
    assert {r["city"] for r in rows} == {"Oakland", "Sacramento"}


def test_a_mistyped_house_number_still_matches_on_phone(conn, manual_csv, monkeypatch):
    """Phone is the last resort, for when the house number itself is wrong."""
    rows = _run_with(
        conn, monkeypatch, manual_csv, [SCRAPED],
        street="1233 Grand Ave", city="Oakland", state="CA",
        phone="(510) 111-2222",
    )

    assert len(rows) == 1
    assert rows[0]["street"] == "1233 Grand Ave"


def test_manual_entry_for_an_unknown_store_is_added(conn, manual_csv, monkeypatch):
    rows = _run_with(
        conn, monkeypatch, manual_csv, [SCRAPED],
        street="1 Far St", city="Fresno", state="CA", postal="93650",
    )

    assert len(rows) == 2
    assert {r["city"] for r in rows} == {"Oakland", "Fresno"}


def test_an_override_correction_survives_a_second_scrape(conn, manual_csv, monkeypatch, tmp_path):
    """Re-applying the same override must not duplicate the store.

    An override patches the fields of a row but leaves it filed under the
    uid the scraped address hashed to. The run that first applies it moves
    the row to the corrected uid; every run after that finds that uid
    already taken — by this same store — and has to adopt it. Inserting
    the old uid instead collides on UNIQUE (brand, street, city, state).
    """
    monkeypatch.setitem(pipeline.SCRAPERS, "haraz", lambda fetch: [SCRAPED])
    pipeline.run_scrape(conn, fetch=_fetch_never_called)
    scraped_uid = conn.execute(
        "SELECT uid FROM locations WHERE brand='haraz'"
    ).fetchone()["uid"]

    columns = ("action", "uid", "brand", *manual.MANUAL_FIELDS, "note")
    cells = {"action": "patch", "uid": scraped_uid, "street": "123 Grand Blvd",
             "city": "Piedmont", "postal": "94611", "note": "typo"}
    (tmp_path / "overrides.csv").write_text(
        ",".join(columns) + "\n"
        + ",".join(cells.get(c, "") for c in columns) + "\n"
    )

    pipeline.run_scrape(conn, fetch=_fetch_never_called)
    pipeline.run_scrape(conn, fetch=_fetch_never_called)

    rows = conn.execute(
        "SELECT uid, street, city FROM locations WHERE brand='haraz'"
    ).fetchall()
    assert len(rows) == 1, "the override duplicated the store on re-scrape"
    assert (rows[0]["street"], rows[0]["city"]) == ("123 Grand Blvd", "Piedmont")
    orphans = conn.execute(
        "SELECT COUNT(*) FROM snapshots s WHERE NOT EXISTS "
        "(SELECT 1 FROM locations l WHERE l.uid = s.uid)"
    ).fetchone()[0]
    assert orphans == 0
