"""Scrape-twice idempotency, and what happens when a scraper misbehaves."""

import sqlite3
from dataclasses import replace

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


class _FakeConfirmer:
    """Records its call and returns rows rewritten by `corrections`."""

    def __init__(self, corrections=None):
        self.corrections = corrections or {}
        self.calls: list[tuple[list[RawLocation], set[str]]] = []

    def confirm(self, rows, *, leave=()):
        self.calls.append((list(rows), set(leave)))
        out = []
        for row in rows:
            fix = self.corrections.get(row.street)
            out.append(replace(row, **fix) if fix else row)
        return out


def test_confirmer_receives_scraped_rows_and_override_uids_to_leave(
    conn, manual_csv, monkeypatch, tmp_path
):
    monkeypatch.setitem(pipeline.SCRAPERS, "haraz", lambda fetch: [SCRAPED])
    (tmp_path / "overrides.csv").write_text(
        "action,uid,brand,street,city,state,postal,status,status_note,lat,lon,"
        "phone,hours,source_url,note\n"
        "patch,some-uid-123,haraz,,,,,,,,,,,,typo\n"
    )
    confirmer = _FakeConfirmer()

    pipeline.run_scrape(conn, fetch=_fetch_never_called, confirmer=confirmer)

    assert len(confirmer.calls) == 1
    rows, leave = confirmer.calls[0]
    assert rows == [SCRAPED]
    assert leave == {"some-uid-123"}


def test_confirmer_corrections_are_what_gets_written(conn, manual_csv, monkeypatch):
    monkeypatch.setitem(pipeline.SCRAPERS, "haraz", lambda fetch: [SCRAPED])
    confirmer = _FakeConfirmer({SCRAPED.street: {"street": "123 Grand Blvd", "city": "Piedmont"}})

    pipeline.run_scrape(conn, fetch=_fetch_never_called, confirmer=confirmer)

    row = conn.execute(
        "SELECT uid, street, city FROM locations WHERE brand='haraz'"
    ).fetchone()
    assert (row["street"], row["city"]) == ("123 Grand Blvd", "Piedmont")
    assert row["uid"] == pipeline.make_uid("haraz", "123 Grand Blvd", "Piedmont", "CA")


def test_confirmer_flag_is_written_and_cleared_on_next_run(conn, manual_csv, monkeypatch):
    monkeypatch.setitem(pipeline.SCRAPERS, "haraz", lambda fetch: [SCRAPED])

    flagged = _FakeConfirmer({SCRAPED.street: {"geocode_flagged": True}})
    pipeline.run_scrape(conn, fetch=_fetch_never_called, confirmer=flagged)
    row = conn.execute(
        "SELECT geocode_flagged FROM locations WHERE brand='haraz'"
    ).fetchone()
    assert row["geocode_flagged"] == 1

    cleared = _FakeConfirmer({SCRAPED.street: {"geocode_flagged": False}})
    pipeline.run_scrape(conn, fetch=_fetch_never_called, confirmer=cleared)
    row = conn.execute(
        "SELECT geocode_flagged FROM locations WHERE brand='haraz'"
    ).fetchone()
    assert row["geocode_flagged"] == 0


def test_confirmer_geocode_source_census_is_written(conn, manual_csv, monkeypatch):
    monkeypatch.setitem(pipeline.SCRAPERS, "haraz", lambda fetch: [SCRAPED])
    confirmer = _FakeConfirmer(
        {SCRAPED.street: {"lat": 40.1, "lon": -80.1, "geocode_source": "census"}}
    )

    pipeline.run_scrape(conn, fetch=_fetch_never_called, confirmer=confirmer)

    row = conn.execute(
        "SELECT lat, lon, geocode_source FROM locations WHERE brand='haraz'"
    ).fetchone()
    assert (row["lat"], row["lon"], row["geocode_source"]) == (40.1, -80.1, "census")


def test_no_confirmer_means_no_confirmation_and_flags_left_alone(conn, manual_csv, monkeypatch):
    monkeypatch.setitem(pipeline.SCRAPERS, "haraz", lambda fetch: [SCRAPED])

    pipeline.run_scrape(conn, fetch=_fetch_never_called)

    row = conn.execute(
        "SELECT geocode_flagged FROM locations WHERE brand='haraz'"
    ).fetchone()
    assert row["geocode_flagged"] == 0


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


def test_confirmer_correction_moves_a_row_stored_under_its_published_uid(
    conn, manual_csv, monkeypatch
):
    """A row a Census outage left filed under its published spelling must be
    moved, not duplicated, once a later run confirms the real address.
    """
    monkeypatch.setitem(pipeline.SCRAPERS, "haraz", lambda fetch: [SCRAPED])

    # Run 1: the confirmer can't confirm, so the row is left with its
    # published spelling and flagged.
    left_alone = _FakeConfirmer({SCRAPED.street: {"geocode_flagged": True}})
    pipeline.run_scrape(conn, fetch=_fetch_never_called, confirmer=left_alone)
    published_uid = conn.execute(
        "SELECT uid FROM locations WHERE brand='haraz'"
    ).fetchone()["uid"]
    first_seen = conn.execute(
        "SELECT first_seen FROM locations WHERE brand='haraz'"
    ).fetchone()["first_seen"]

    # Run 2: the confirmer now returns the corrected address, and names the
    # uid the row is already stored under via published_uid.
    confirmed_uid = pipeline.make_uid("haraz", "123 Grand Blvd", "Piedmont", "CA")
    fixed = _FakeConfirmer({SCRAPED.street: {
        "street": "123 Grand Blvd", "city": "Piedmont",
        "published_uid": published_uid,
    }})
    pipeline.run_scrape(conn, fetch=_fetch_never_called, confirmer=fixed)

    rows = conn.execute("SELECT * FROM locations WHERE brand='haraz'").fetchall()
    assert len(rows) == 1, "the confirmed row was duplicated instead of moved"
    row = rows[0]
    assert row["uid"] == confirmed_uid
    assert (row["street"], row["city"]) == ("123 Grand Blvd", "Piedmont")
    assert row["first_seen"] == first_seen

    snaps = conn.execute(
        "SELECT COUNT(*) FROM snapshots WHERE uid=?", (confirmed_uid,)
    ).fetchone()[0]
    assert snaps == 2  # both runs' observations followed the row to its new uid


def test_confirmer_correction_merges_when_both_uids_already_exist(
    conn, manual_csv, monkeypatch
):
    """The table already holds a row under each uid — set up by two earlier
    runs, each returning a different address for the brand — so a run that
    confirms the address must fold onto the existing confirmed row rather
    than leave a duplicate behind.
    """
    published = RawLocation(brand="haraz", street="123 Grand Ave", city="Oakland",
                            state="CA", postal="94610", status="open")
    confirmed = RawLocation(brand="haraz", street="123 Grand Blvd", city="Piedmont",
                            state="CA", postal="94611", status="open")
    confirmed_uid = pipeline.make_uid("haraz", "123 Grand Blvd", "Piedmont", "CA")
    published_uid = pipeline.make_uid("haraz", "123 Grand Ave", "Oakland", "CA")

    # Run 1 writes the confirmed-address row (no confirmer involved — this
    # is just how the store already sits in the table).
    monkeypatch.setitem(pipeline.SCRAPERS, "haraz", lambda fetch: [confirmed])
    pipeline.run_scrape(conn, fetch=_fetch_never_called)

    # Run 2: the scraper now reports the published spelling instead — a
    # different row, so it's added rather than replacing run 1's, standing
    # in for a row an earlier confirmer run left under its published uid.
    monkeypatch.setitem(pipeline.SCRAPERS, "haraz", lambda fetch: [published])
    pipeline.run_scrape(conn, fetch=_fetch_never_called)
    assert conn.execute(
        "SELECT COUNT(*) FROM locations WHERE brand='haraz'"
    ).fetchone()[0] == 2

    # Run 3: the confirmer returns the confirmed address again, naming the
    # published uid — both rows already exist, so this must merge.
    confirmer = _FakeConfirmer({published.street: {
        "street": "123 Grand Blvd", "city": "Piedmont",
        "published_uid": published_uid,
    }})
    pipeline.run_scrape(conn, fetch=_fetch_never_called, confirmer=confirmer)

    rows = conn.execute("SELECT * FROM locations WHERE brand='haraz'").fetchall()
    assert len(rows) == 1, "the published row was left behind instead of merged"
    assert rows[0]["uid"] == confirmed_uid

    # merge_into moves snapshots via UPDATE OR IGNORE: a run's observation
    # only gets dropped if that same run already has a snapshot under the
    # destination uid. Nothing collides here — run 1 and run 3 both land
    # directly on confirmed_uid (the row's own uid each time), run 2 lands
    # on published_uid and then moves across cleanly — so all three survive.
    snaps = conn.execute(
        "SELECT COUNT(*) FROM snapshots WHERE uid=?", (confirmed_uid,)
    ).fetchone()[0]
    assert snaps == 3


def test_confirmer_spelling_fix_rewrites_a_row_already_in_the_table(
    conn, manual_csv, monkeypatch
):
    """The uid is punctuation-blind, so a spelling fix never moves it — but
    the corrected spelling still has to land on the row already stored
    under that uid, not just on rows written for the first time.
    """
    raw = RawLocation(brand="haraz", street="343 N Main St.", city="Anytown",
                       state="TX", postal="75001", status="open")
    monkeypatch.setitem(pipeline.SCRAPERS, "haraz", lambda fetch: [raw])
    pipeline.run_scrape(conn, fetch=_fetch_never_called)

    own_uid = pipeline.make_uid("haraz", raw.street, raw.city, "TX")
    first_seen = conn.execute(
        "SELECT first_seen FROM locations WHERE uid=?", (own_uid,)
    ).fetchone()["first_seen"]

    confirmer = _FakeConfirmer(
        {raw.street: {"street": "343 N Main St", "published_uid": own_uid}}
    )
    pipeline.run_scrape(conn, fetch=_fetch_never_called, confirmer=confirmer)

    rows = conn.execute("SELECT * FROM locations WHERE brand='haraz'").fetchall()
    assert len(rows) == 1
    assert rows[0]["uid"] == own_uid
    assert rows[0]["street"] == "343 N Main St"
    assert rows[0]["first_seen"] == first_seen
    snaps = conn.execute(
        "SELECT COUNT(*) FROM snapshots WHERE uid=?", (own_uid,)
    ).fetchone()[0]
    assert snaps == 2


@pytest.mark.parametrize("corrections", [None, {}])
def test_no_address_change_leaves_a_stored_spelling_untouched(
    conn, manual_csv, monkeypatch, corrections
):
    """No confirmer at all, or one that doesn't touch this row (so
    published_uid comes back None): either way the stored spelling stands.
    """
    raw = RawLocation(brand="haraz", street="343 N Main St.", city="Anytown",
                       state="TX", postal="75001", status="open")
    monkeypatch.setitem(pipeline.SCRAPERS, "haraz", lambda fetch: [raw])
    pipeline.run_scrape(conn, fetch=_fetch_never_called)

    confirmer = None if corrections is None else _FakeConfirmer(corrections)
    pipeline.run_scrape(conn, fetch=_fetch_never_called, confirmer=confirmer)

    row = conn.execute(
        "SELECT street FROM locations WHERE brand='haraz'"
    ).fetchone()
    assert row["street"] == "343 N Main St."
