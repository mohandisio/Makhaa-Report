"""The review queue and the two ways a row leaves it."""

import csv

import pytest

from makhaa_report import db, geo, manual, sanitize
from makhaa_report.models import RawLocation, utcnow_iso
from makhaa_report.normalize import make_uid, split_unit, to_location


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr("makhaa_report.config.GEO_DIR", tmp_path / "geo")
    monkeypatch.setattr("makhaa_report.config.OVERRIDES_PATH", tmp_path / "overrides.csv")
    return tmp_path


@pytest.fixture
def conn(workspace):
    return db.connect(workspace / "test.sqlite")


def _store(conn, brand="haraz", street="1 Main St", city="Dearborn", state="MI",
           postal="48126", lat=None, lon=None, source=None):
    conn.execute(
        "INSERT OR IGNORE INTO brands (slug, display_name, locator_url, method)"
        " VALUES (?,?,?,'scrape')",
        (brand, brand.title(), "https://example.test"),
    )
    now = utcnow_iso()
    loc = to_location(RawLocation(brand=brand, street=street, city=city,
                                  state=state, postal=postal), now)
    loc.lat, loc.lon, loc.geocode_source = lat, lon, source
    db.upsert_location(conn, loc)
    conn.execute("INSERT INTO runs (started_at) VALUES (?)", (now,))
    db.insert_snapshot(conn, 1, loc.uid, now, "open", "")
    conn.commit()
    return loc.uid


def _cache(name, entries):
    """Write one geocoder cache: {(street, city, state, postal): Match}."""
    store = geo.MatchCache(__import__("makhaa_report.config", fromlist=["x"]).GEO_DIR / name)
    for (street, city, state, postal), match in entries.items():
        store.put(geo.Query("k", split_unit(street)[0], city, state, postal), match)
    store.save()


# --- the queue ----------------------------------------------------------

def test_an_address_no_source_knows_is_queued(conn):
    _store(conn, street="21800 Towncenter Plz", city="Sterling", state="VA",
           postal="20164")
    _cache("census.json", {("21800 Towncenter Plz", "Sterling", "VA", "20164"): geo.MISS})
    _cache("nominatim.json", {("21800 Towncenter Plz", "Sterling", "VA", "20164"): geo.MISS})

    found = sanitize.find_problems(conn)

    assert [f.kind for f in found] == ["unconfirmed"]
    assert found[0].why == "no gazetteer recognises the address"


def test_an_address_openstreetmap_knows_is_not_queued(conn):
    _store(conn, street="1076 Rte 59", city="Aurora", state="IL", postal="60504")
    _cache("census.json", {("1076 Rte 59", "Aurora", "IL", "60504"): geo.MISS})
    _cache("nominatim.json", {
        ("1076 Rte 59", "Aurora", "IL", "60504"): geo.Match(True, False, lat=41.7, lon=-88.2),
    })

    assert sanitize.find_problems(conn) == []


def test_a_coordinate_far_from_an_exact_match_is_queued(conn):
    _store(conn, street="8602 4th Ave", city="Brooklyn", state="NY", postal="11209",
           lat=42.3073, lon=-83.2452, source="locator")  # Dearborn, Michigan
    _cache("census.json", {
        ("8602 4th Ave", "Brooklyn", "NY", "11209"):
            geo.Match(True, True, "8602 4TH AVE", "BROOKLYN", "NY", "11209",
                      lat=40.6227, lon=-74.0285),
    })

    found = sanitize.find_problems(conn)

    assert [f.kind for f in found] == ["coordinate"]
    assert round(found[0].drift) == 790


def test_a_coordinate_within_tolerance_is_not_queued(conn):
    _store(conn, lat=42.3395, lon=-83.1767, source="locator")
    _cache("census.json", {
        ("1 Main St", "Dearborn", "MI", "48126"):
            geo.Match(True, True, "1 MAIN ST", "DEARBORN", "MI", "48126",
                      lat=42.3400, lon=-83.1770),
    })

    assert sanitize.find_problems(conn) == []


def test_a_row_already_corrected_by_hand_is_left_out(conn):
    uid = _store(conn, street="21800 Towncenter Plz", city="Sterling", state="VA",
                 postal="20164")
    conn.execute("UPDATE locations SET is_manual=1 WHERE uid=?", (uid,))
    conn.commit()
    _cache("census.json", {("21800 Towncenter Plz", "Sterling", "VA", "20164"): geo.MISS})

    assert sanitize.find_problems(conn) == []


# --- adopting a coordinate ----------------------------------------------

def test_adopting_writes_the_coordinate_and_records_it(conn, workspace):
    uid = _store(conn, street="8602 4th Ave", city="Brooklyn", state="NY",
                 postal="11209", lat=42.3073, lon=-83.2452, source="locator")
    _cache("census.json", {
        ("8602 4th Ave", "Brooklyn", "NY", "11209"):
            geo.Match(True, True, "8602 4TH AVE", "BROOKLYN", "NY", "11209",
                      lat=40.6227, lon=-74.0285),
    })

    adopted = sanitize.adopt_coordinates(conn, sanitize.find_problems(conn))

    assert len(adopted) == 1
    row = conn.execute("SELECT lat, lon, geocode_source, geocode_flagged "
                       "FROM locations").fetchone()
    assert (round(row["lat"], 3), round(row["lon"], 3)) == (40.623, -74.028)
    assert row["geocode_source"] == "census"
    assert row["geocode_flagged"] == 0
    # Recorded, or the next scrape republishes the locator's version.
    overrides = list(csv.DictReader((workspace / "overrides.csv").open()))
    assert [o["uid"] for o in overrides] == [uid]
    assert "790 km away" in overrides[0]["note"]
    # And it leaves the queue.
    assert sanitize.find_problems(conn) == []


def test_a_dry_run_adopts_nothing(conn, workspace):
    _store(conn, street="8602 4th Ave", city="Brooklyn", state="NY", postal="11209",
           lat=42.3073, lon=-83.2452, source="locator")
    _cache("census.json", {
        ("8602 4th Ave", "Brooklyn", "NY", "11209"):
            geo.Match(True, True, "8602 4TH AVE", "BROOKLYN", "NY", "11209",
                      lat=40.6227, lon=-74.0285),
    })

    adopted = sanitize.adopt_coordinates(conn, sanitize.find_problems(conn), dry_run=True)

    assert len(adopted) == 1
    assert conn.execute("SELECT lat FROM locations").fetchone()[0] == 42.3073
    assert not (workspace / "overrides.csv").exists()


# --- correcting an address ----------------------------------------------

def test_correcting_an_address_moves_the_row_and_its_history(conn, workspace):
    uid = _store(conn, brand="matari", street="285 South Broadway, Hicksville",
                 city="Long Isand", state="NY", postal=None)

    new_uid = sanitize.correct_address(
        conn, uid,
        {"street": "285 S Broadway", "city": "Hicksville", "postal": "11801",
         "lat": "40.76223", "lon": "-73.51674"},
        note="locator publishes the borough as the city",
    )

    assert new_uid == make_uid("matari", "285 S Broadway", "Hicksville", "NY")
    rows = conn.execute("SELECT uid, street, city, postal, lat, is_manual, "
                        "geocode_flagged FROM locations").fetchall()
    assert len(rows) == 1
    assert (rows[0]["street"], rows[0]["city"]) == ("285 S Broadway", "Hicksville")
    assert rows[0]["postal"] == "11801"
    assert rows[0]["is_manual"] == 1
    assert rows[0]["geocode_flagged"] == 0
    assert conn.execute("SELECT uid FROM snapshots").fetchone()["uid"] == new_uid
    # Keyed on the uid the scraper will produce again, not the corrected one.
    overrides = list(csv.DictReader((workspace / "overrides.csv").open()))
    assert overrides[0]["uid"] == uid


def test_correcting_onto_an_address_another_row_holds_folds_them(conn):
    keeper = _store(conn, brand="mokafe", street="606 Broad Hollow Rd",
                    city="Melville", state="NY", postal="11747")
    stale = _store(conn, brand="mokafe", street="606 Broadhollow Rd",
                   city="Melville", state="NY", postal="11747")

    result = sanitize.correct_address(
        conn, stale, {"street": "606 Broad Hollow Rd"}, note="one road, two spellings",
    )

    assert result == keeper
    assert conn.execute("SELECT COUNT(*) FROM locations").fetchone()[0] == 1
    assert conn.execute(
        "SELECT COUNT(*) FROM snapshots s WHERE NOT EXISTS "
        "(SELECT 1 FROM locations l WHERE l.uid = s.uid)"
    ).fetchone()[0] == 0


def test_correcting_an_unknown_uid_is_an_error(conn):
    with pytest.raises(KeyError):
        sanitize.correct_address(conn, "nosuchuid", {"city": "Nowhere"}, note="x")
