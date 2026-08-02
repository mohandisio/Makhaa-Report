"""Address resolution end to end, against a stubbed geocoder.

The uid is a hash of the address, so correcting an address moves the row.
These tests pin that the store stays one row with its history attached.
"""

import pytest

from makhaa_report import db, geo, geocode
from makhaa_report.models import RawLocation, utcnow_iso
from makhaa_report.normalize import make_uid, to_location


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr("makhaa_report.config.GEO_DIR", tmp_path / "geo")
    return db.connect(tmp_path / "test.sqlite")


def _store(conn, brand="haraz", street="1737 N Alafaya Trail", city="Orlando",
           state="FL", postal="32826"):
    """Put one location in the database, the way a scrape would."""
    conn.execute(
        "INSERT OR IGNORE INTO brands (slug, display_name, locator_url, method,"
        " band_low, band_high) VALUES (?,?,?,'scrape',0,99)",
        (brand, brand.title(), "https://example.test"),
    )
    now = utcnow_iso()
    loc = to_location(
        RawLocation(brand=brand, name="Test", street=street, city=city,
                    state=state, postal=postal),
        now,
    )
    db.upsert_location(conn, loc)
    conn.execute("INSERT INTO runs (started_at) VALUES (?)", (now,))
    db.insert_snapshot(conn, 1, loc.uid, now, "open", "")
    conn.commit()
    return loc.uid


def _responder(rows: dict[str, str]):
    """Answer a batch from {street queried: matched address}, else No_Match."""

    def post(body: str) -> str:
        out = []
        for line in body.splitlines():
            if not line:
                continue
            key, street, *_ = line.split(",")
            matched = rows.get(street)
            if matched is None:
                out.append(f'"{key}","echo","No_Match"')
            else:
                out.append(
                    f'"{key}","echo","Match","Exact","{matched}",'
                    f'"-81.2,28.6","1","R"'
                )
        return "\n".join(out) + "\n"

    return post


# --- resolve ------------------------------------------------------------

def test_exact_match_is_adopted_with_our_casing():
    match = geo.Match(True, True, "10009 N MACARTHUR BLVD", "IRVING", "TX", "75063")
    r = geo.resolve("k", match, "10009 N MacArthur Boulevard #101", "Irving", "75063")
    assert r.verdict == "adopted"
    # "Boulevard" shortens, "MacArthur" survives, "#101" comes back.
    assert r.street == "10009 N MacArthur Blvd #101"
    assert r.city == "Irving"


def test_non_exact_match_is_never_adopted():
    # The real store is on South Broadway in Hicksville; Census offers a
    # different street in a different town.
    match = geo.Match(True, False, "285 BROADWAY", "ISLAND PARK", "NY", "11558")
    r = geo.resolve("k", match, "285 South Broadway, Hicksville", "Long Isand", None)
    assert r.verdict == "inexact"
    assert (r.street, r.city) == ("285 South Broadway, Hicksville", "Long Isand")


def test_unmatched_row_keeps_everything():
    r = geo.resolve("k", geo.MISS, "21788 Katy Freeway Suite 400", "Katy", "77449")
    assert r.verdict == "unmatched"
    assert r.street == "21788 Katy Freeway Suite 400"


def test_missing_match_is_treated_as_unmatched():
    assert geo.resolve("k", None, "1 Main St", "Springfield", None).verdict == "unmatched"


def test_a_zip_we_lack_is_filled_in():
    match = geo.Match(True, True, "6290 HOLLYWOOD BLVD", "LOS ANGELES", "CA", "90028")
    r = geo.resolve("k", match, "6290 HOLLYWOOD BLVD", "LOS ANGELES", None)
    assert r.postal == "90028"
    assert r.city == "Los Angeles"


def test_an_address_already_canonical_is_unchanged():
    match = geo.Match(True, True, "2138 CATON AVE", "BROOKLYN", "NY", "11226")
    r = geo.resolve("k", match, "2138 Caton Ave", "Brooklyn", "11226")
    assert r.verdict == "unchanged"


# --- run_geocode --------------------------------------------------------

def test_adopting_moves_the_row_and_its_snapshots(conn):
    old_uid = _store(conn)
    post = _responder({"1737 N Alafaya Trail": "1737 N ALAFAYA TRL, ORLANDO, FL, 32826"})

    geocode.run_geocode(conn, post=post)

    new_uid = make_uid("haraz", "1737 N Alafaya Trl", "Orlando", "FL")
    assert new_uid != old_uid
    rows = conn.execute("SELECT uid, street FROM locations").fetchall()
    assert len(rows) == 1, "the store must not be duplicated by its correction"
    assert (rows[0]["uid"], rows[0]["street"]) == (new_uid, "1737 N Alafaya Trl")
    # History follows the row rather than being orphaned.
    assert conn.execute("SELECT uid FROM snapshots").fetchone()["uid"] == new_uid


def test_dry_run_writes_nothing(conn):
    old_uid = _store(conn)
    post = _responder({"1737 N Alafaya Trail": "1737 N ALAFAYA TRL, ORLANDO, FL, 32826"})

    stats = geocode.run_geocode(conn, dry_run=True, post=post)

    assert stats.counts["adopted"] == 1
    row = conn.execute("SELECT uid, street FROM locations").fetchone()
    assert (row["uid"], row["street"]) == (old_uid, "1737 N Alafaya Trail")


def test_unit_is_stripped_before_the_lookup_and_restored_after(conn):
    _store(conn, street="1561 Lee Rd Ste 102", city="Winter Park", postal="32789")
    asked: list[str] = []

    def post(body: str) -> str:
        street = body.split(",")[1]
        asked.append(street)
        return _responder({street: "1561 LEE RD, WINTER PARK, FL, 32789"})(body)

    geocode.run_geocode(conn, post=post)

    assert asked == ["1561 Lee Rd"], "the unit must not be sent to the geocoder"
    assert conn.execute("SELECT street FROM locations").fetchone()[0] == \
        "1561 Lee Rd Ste 102"


def test_two_rows_collapsing_to_one_address_are_left_alone(conn):
    # One store filed under a borough and under the city. The two hash
    # differently now, but Census resolves both to the same address, so
    # correcting the first would land it on top of the second. That is a
    # duplicate for a human to drop, not a row to overwrite.
    _store(conn, street="142 West 34th St", city="Manhattan", state="NY", postal="10001")
    _store(conn, street="142 W 34th St", city="New York", state="NY", postal="10001")
    post = _responder({
        "142 West 34th St": "142 W 34TH ST, NEW YORK, NY, 10001",
        "142 W 34th St": "142 W 34TH ST, NEW YORK, NY, 10001",
    })

    stats = geocode.run_geocode(conn, post=post)

    assert len(stats.collisions) == 1
    assert conn.execute("SELECT COUNT(*) FROM locations").fetchone()[0] == 2


def test_second_run_asks_the_service_nothing(conn):
    _store(conn)
    post = _responder({"1737 N Alafaya Trail": "1737 N ALAFAYA TRL, ORLANDO, FL, 32826"})
    geocode.run_geocode(conn, post=post)

    def boom(body: str) -> str:
        raise AssertionError("re-ran a lookup that the cache already answered")

    # The address changed, so this asks about the new one — still one call,
    # never a repeat of the old.
    geocode.run_geocode(conn, post=_responder({}))
    stats = geocode.run_geocode(conn, post=boom)
    assert stats.total == 1


def test_change_records_carry_before_and_after(conn):
    _store(conn)
    post = _responder({"1737 N Alafaya Trail": "1737 N ALAFAYA TRL, ORLANDO, FL, 32826"})

    stats = geocode.run_geocode(conn, dry_run=True, post=post)

    change = stats.substantive[0]
    assert change.old_street == "1737 N Alafaya Trail"
    assert change.new_street == "1737 N Alafaya Trl"
    assert not change.cosmetic


def test_a_case_only_change_is_reported_as_cosmetic(conn):
    _store(conn, street="6290 HOLLYWOOD BLVD", city="LOS ANGELES", state="CA",
           postal="90028")
    post = _responder({"6290 HOLLYWOOD BLVD": "6290 HOLLYWOOD BLVD, LOS ANGELES, CA, 90028"})

    stats = geocode.run_geocode(conn, dry_run=True, post=post)

    assert stats.cosmetic == 1
    assert stats.substantive == []
