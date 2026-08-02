"""Address resolution end to end, against a stubbed geocoder.

The uid is a hash of the address, so correcting an address moves the row.
These tests pin that the store stays one row with its history attached.
"""

import json

import pytest

from makhaa_report import db, geo, geocode, pipeline
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


def _osm(results: dict[str, tuple[float, float]] | None = None):
    """Stand in for Nominatim: {street queried: (lat, lon)}, else no result."""
    results = results or {}

    def get(url: str, params: dict[str, str]) -> str:
        point = results.get(params["street"])
        if point is None:
            return "[]"
        return json.dumps([{"lat": str(point[0]), "lon": str(point[1])}])

    return get


def _run(conn, **kwargs):
    """run_geocode with the clock stubbed, so the rate limit costs no time."""
    kwargs.setdefault("get", _osm())
    return geocode.run_geocode(conn, sleep=lambda _s: None, **kwargs)


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

def test_a_suffix_correction_keeps_the_uid(conn):
    # "Alafaya Trail" and "Alafaya Trl" hash the same, so adopting the
    # canonical spelling rewrites the row without moving it. This is what
    # stops the next scrape re-inserting the uncorrected address.
    old_uid = _store(conn)
    post = _responder({"1737 N Alafaya Trail": "1737 N ALAFAYA TRL, ORLANDO, FL, 32826"})

    _run(conn, post=post)

    rows = conn.execute("SELECT uid, street FROM locations").fetchall()
    assert len(rows) == 1
    assert (rows[0]["uid"], rows[0]["street"]) == (old_uid, "1737 N Alafaya Trl")


def test_adopting_moves_the_row_and_its_snapshots(conn):
    # A word split is beyond any abbreviation rule, so this correction
    # really does re-key — and the row must travel whole.
    old_uid = _store(conn, street="606 Broadhollow Rd", city="Melville",
                     state="NY", postal="11747")
    post = _responder({"606 Broadhollow Rd": "606 BROAD HOLLOW RD, MELVILLE, NY, 11747"})

    _run(conn, post=post)

    new_uid = make_uid("haraz", "606 Broad Hollow Rd", "Melville", "NY")
    assert new_uid != old_uid
    rows = conn.execute("SELECT uid, street FROM locations").fetchall()
    assert len(rows) == 1, "the store must not be duplicated by its correction"
    assert (rows[0]["uid"], rows[0]["street"]) == (new_uid, "606 Broad Hollow Rd")
    # History follows the row rather than being orphaned.
    assert conn.execute("SELECT uid FROM snapshots").fetchone()["uid"] == new_uid


def test_dry_run_writes_nothing(conn):
    old_uid = _store(conn)
    post = _responder({"1737 N Alafaya Trail": "1737 N ALAFAYA TRL, ORLANDO, FL, 32826"})

    stats = _run(conn, dry_run=True, post=post)

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

    _run(conn, post=post)

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

    stats = _run(conn, post=post)

    assert len(stats.collisions) == 1
    assert conn.execute("SELECT COUNT(*) FROM locations").fetchone()[0] == 2


def test_second_run_asks_the_service_nothing(conn):
    _store(conn)
    post = _responder({"1737 N Alafaya Trail": "1737 N ALAFAYA TRL, ORLANDO, FL, 32826"})
    _run(conn, post=post)

    def boom(body: str) -> str:
        raise AssertionError("re-ran a lookup that the cache already answered")

    # The address changed, so this asks about the new one — still one call,
    # never a repeat of the old.
    _run(conn, post=_responder({}))
    stats = _run(conn, post=boom)
    assert stats.total == 1


def test_change_records_carry_before_and_after(conn):
    _store(conn)
    post = _responder({"1737 N Alafaya Trail": "1737 N ALAFAYA TRL, ORLANDO, FL, 32826"})

    stats = _run(conn, dry_run=True, post=post)

    change = stats.substantive[0]
    assert change.old_street == "1737 N Alafaya Trail"
    assert change.new_street == "1737 N Alafaya Trl"
    assert not change.cosmetic


@pytest.mark.parametrize("scraped, canonical", [
    ("1737 N Alafaya Trail", "1737 N ALAFAYA TRL"),
    ("43780 Parkhurst Plaza", "43780 PARKHURST PLZ"),
    ("222 E Farm To Market 544", "222 E FM 544"),
    ("356 Troy-Schenectady Rd", "356 TROY SCHENECTADY RD"),
])
def test_a_rescrape_does_not_resurrect_the_uncorrected_address(
    conn, tmp_path, monkeypatch, scraped, canonical
):
    """The bug this guards: geocode corrects an address, the weekly scrape
    publishes the original spelling again, and the store becomes two rows.
    """
    manual = tmp_path / "manual"
    manual.mkdir()
    (manual / "mohka_house.csv").write_text(
        "name,street,city,state,postal,status,status_note,lat,lon,phone,hours,source_url\n"
        f"Mohka House,{scraped},Latham,NY,12110,open,,,,,,\n"
    )
    monkeypatch.setattr("makhaa_report.config.MANUAL_DIR", manual)
    monkeypatch.setattr("makhaa_report.config.OVERRIDES_PATH", tmp_path / "overrides.csv")
    monkeypatch.setattr("makhaa_report.config.EXPORT_DIR", tmp_path / "exports")

    def no_fetch(url: str) -> str:
        raise AssertionError(f"network fetch attempted: {url}")

    pipeline.run_scrape(conn, brands=["mohka_house"], fetch=no_fetch)
    _run(conn, post=_responder({scraped: f"{canonical}, LATHAM, NY, 12110"}))
    pipeline.run_scrape(conn, brands=["mohka_house"], fetch=no_fetch)

    rows = conn.execute("SELECT street FROM locations").fetchall()
    assert len(rows) == 1, f"re-scraping split the store into {len(rows)} rows"


def test_an_override_can_correct_the_address_itself(conn, tmp_path, monkeypatch):
    """upsert_location refuses to move street/city because they feed the
    uid. A hand correction is exactly the case that must be allowed to.
    """
    manual_dir = tmp_path / "manual"
    manual_dir.mkdir()
    (manual_dir / "mohka_house.csv").write_text(
        "name,street,city,state,postal,status,status_note,lat,lon,phone,hours,source_url\n"
        "Mohka House,285 South Broadway,Long Isand,NY,,open,,,,,,\n"
    )
    uid = make_uid("mohka_house", "285 South Broadway", "Long Isand", "NY")
    overrides = tmp_path / "overrides.csv"
    overrides.write_text(
        "action,uid,brand,name,street,city,state,postal,lat,lon,status,"
        "status_note,phone,hours,note\n"
        f"patch,{uid},,,285 S Broadway,Hicksville,,11801,40.76223,-73.51674,,,,,typo\n"
    )
    monkeypatch.setattr("makhaa_report.config.MANUAL_DIR", manual_dir)
    monkeypatch.setattr("makhaa_report.config.OVERRIDES_PATH", overrides)
    monkeypatch.setattr("makhaa_report.config.EXPORT_DIR", tmp_path / "exports")

    def no_fetch(url: str) -> str:
        raise AssertionError(f"network fetch attempted: {url}")

    pipeline.run_scrape(conn, brands=["mohka_house"], fetch=no_fetch)

    rows = conn.execute("SELECT uid, street, city, postal, lat FROM locations").fetchall()
    assert len(rows) == 1
    assert (rows[0]["street"], rows[0]["city"]) == ("285 S Broadway", "Hicksville")
    assert rows[0]["postal"] == "11801"
    # The uid follows the corrected address, and its history comes along.
    assert rows[0]["uid"] == make_uid("mohka_house", "285 S Broadway", "Hicksville", "NY")
    assert conn.execute("SELECT uid FROM snapshots").fetchone()["uid"] == rows[0]["uid"]


def test_connect_rekeys_rows_left_by_an_older_normalizer(tmp_path, monkeypatch):
    """A uid written before an abbreviation was added must converge.

    Otherwise the next scrape computes the new uid, finds nothing under
    it, and inserts the store a second time.
    """
    monkeypatch.setattr("makhaa_report.config.GEO_DIR", tmp_path / "geo")
    path = tmp_path / "stale.sqlite"
    conn = db.connect(path)
    uid = _store(conn, street="43780 Parkhurst Plaza", city="Ashburn",
                 state="VA", postal="20147")
    # Pretend the row was keyed before "plaza" was abbreviated.
    conn.execute("UPDATE locations SET uid='legacyuid0000000' WHERE uid=?", (uid,))
    conn.execute("UPDATE snapshots SET uid='legacyuid0000000' WHERE uid=?", (uid,))
    conn.commit()
    conn.close()

    conn = db.connect(path)

    rows = conn.execute("SELECT uid FROM locations").fetchall()
    assert len(rows) == 1
    assert rows[0]["uid"] == uid
    assert conn.execute("SELECT uid FROM snapshots").fetchone()["uid"] == uid


# --- verification -------------------------------------------------------

def test_a_city_only_correction_is_adopted():
    # Census returns Non_Exact but hands back our street letter for
    # letter: it is only correcting the borough. Safe.
    match = geo.Match(True, False, "142 W 34TH ST", "NEW YORK", "NY", "10001")
    r = geo.resolve("k", match, "142 West 34th st", "Manhattan", "10001")
    assert r.verdict == "adopted"
    assert (r.street, r.city) == ("142 W 34th St", "New York")


def test_a_street_change_is_still_never_adopted():
    # Same Non_Exact verdict, but the street moved: 14th St is not 14th Pl.
    match = geo.Match(True, False, "4341 14TH PL", "PLANO", "TX", "75074")
    r = geo.resolve("k", match, "4341 14th St", "Plano", "75074")
    assert r.verdict == "inexact"
    assert r.street == "4341 14th St"


def test_openstreetmap_confirms_an_address_census_could_not(conn):
    _store(conn, street="1076 Rte 59", city="Aurora", state="IL", postal="60504")
    conn.execute("UPDATE locations SET lat=41.7, lon=-88.2, geocode_source='locator'")
    conn.commit()

    stats = _run(conn, post=_responder({}), get=_osm({"1076 Rte 59": (41.747, -88.206)}))

    assert stats.verified == {"openstreetmap": 1}
    assert stats.unverified == []
    # It already had coordinates; OSM was asked only to confirm the address.
    row = conn.execute("SELECT lat, geocode_source, geocode_flagged FROM locations").fetchone()
    assert (row["lat"], row["geocode_source"]) == (41.7, "locator")
    assert row["geocode_flagged"] == 0


def test_an_address_neither_source_knows_is_reported(conn):
    _store(conn, street="21800 Towncenter Plz", city="Sterling", state="VA", postal="20164")
    conn.execute("UPDATE locations SET lat=39.0, lon=-77.4, geocode_source='locator'")
    conn.commit()

    stats = _run(conn, post=_responder({}), get=_osm())

    assert stats.unverified == ["21800 Towncenter Plz, Sterling, VA"]
    assert len(stats.flagged) == 1
    # The in-bounds check clears the flag before the OSM pass sets it, so
    # what the run reports and what the database holds must agree.
    assert conn.execute(
        "SELECT COUNT(*) FROM locations WHERE geocode_flagged=1"
    ).fetchone()[0] == len(stats.flagged)


def test_a_verified_row_is_not_asked_about_twice(conn):
    _store(conn)
    post = _responder({"1737 N Alafaya Trail": "1737 N ALAFAYA TRL, ORLANDO, FL, 32826"})
    asked: list[str] = []

    def counting(url, params):
        asked.append(params["street"])
        return "[]"

    _run(conn, post=post, get=counting)
    assert asked == [], "census settled this address; OSM should not be troubled"


# --- coordinates --------------------------------------------------------

def test_census_coordinates_land_on_the_corrected_row(conn):
    # The correction re-keys the row, so a coordinate looked up under the
    # old uid has to follow it across.
    _store(conn)
    post = _responder({"1737 N Alafaya Trail": "1737 N ALAFAYA TRL, ORLANDO, FL, 32826"})

    _run(conn, post=post)

    row = conn.execute("SELECT lat, lon, geocode_source FROM locations").fetchone()
    assert (round(row["lat"], 1), round(row["lon"], 1)) == (28.6, -81.2)
    assert row["geocode_source"] == "census"


def test_nominatim_places_what_census_could_not(conn):
    _store(conn, street="21788 Katy Freeway", city="Katy", state="TX", postal="77449")

    stats = _run(conn, post=_responder({}),
                 get=_osm({"21788 Katy Freeway": (29.78, -95.76)}))

    row = conn.execute("SELECT lat, lon, geocode_source FROM locations").fetchone()
    assert (round(row["lat"], 2), round(row["lon"], 2)) == (29.78, -95.76)
    assert row["geocode_source"] == "nominatim"
    assert stats.filled == {"nominatim": 1}


def test_a_row_no_source_can_place_stays_empty_and_flagged(conn):
    _store(conn, street="99999 Fakery Blvd", city="Nowhere", state="TX", postal="77449")

    stats = _run(conn, post=_responder({}), get=_osm())

    row = conn.execute("SELECT lat, lon, geocode_flagged FROM locations").fetchone()
    assert (row["lat"], row["lon"]) == (None, None), "no coordinate is better than a wrong one"
    assert row["geocode_flagged"] == 1
    assert stats.still_dark == 1


def test_a_row_that_already_has_coordinates_is_not_looked_up(conn):
    _store(conn)
    conn.execute("UPDATE locations SET lat=28.6, lon=-81.2, geocode_source='locator'")
    conn.commit()

    stats = _run(conn, post=_responder({}), get=_osm())

    row = conn.execute("SELECT geocode_source FROM locations").fetchone()
    assert row["geocode_source"] == "locator"
    assert stats.filled == {}


def test_a_coordinate_outside_the_us_is_flagged_but_kept(conn):
    # A locator published a New Jersey store at 33.89,35.50 — Lebanon.
    _store(conn, street="493 Bloomfield Ave", city="Montclair", state="NJ", postal="07042")
    conn.execute("UPDATE locations SET lat=33.8915, lon=35.5024, geocode_source='locator'")
    conn.commit()

    stats = _run(conn, post=_responder({}), get=_osm())

    row = conn.execute("SELECT lat, geocode_flagged FROM locations").fetchone()
    assert row["geocode_flagged"] == 1
    assert row["lat"] == 33.8915, "kept for review rather than deleted"
    assert len(stats.flagged) == 1


def test_a_flag_clears_once_the_row_is_fixed(conn):
    # A hand-corrected coordinate must not leave the row flagged forever.
    _store(conn, street="493 Bloomfield Ave", city="Montclair", state="NJ", postal="07042")
    conn.execute("UPDATE locations SET lat=33.8915, lon=35.5024, geocode_source='locator'")
    conn.commit()
    assert _run(conn, post=_responder({})).flagged

    # What an override does: sets the coordinates and marks the row as
    # hand-checked, which is what stops it being reported as unverified.
    conn.execute("UPDATE locations SET lat=40.81466, lon=-74.21811, "
                 "geocode_source='manual', is_manual=1")
    conn.commit()
    stats = _run(conn, post=_responder({}))

    assert stats.flagged == []
    assert stats.verified == {"hand": 1}
    assert conn.execute("SELECT geocode_flagged FROM locations").fetchone()[0] == 0


@pytest.mark.parametrize("lat, lon, expected", [
    (42.33, -83.49, True),    # Detroit
    (21.31, -157.86, True),   # Honolulu
    (61.22, -149.90, True),   # Anchorage
    (33.89, 35.50, False),    # Beirut
    (51.51, -0.13, False),    # London
])
def test_us_bounds(lat, lon, expected):
    assert geo.in_us(lat, lon) is expected


def test_nominatim_is_asked_once_then_answered_from_cache(conn):
    _store(conn, street="21788 Katy Freeway", city="Katy", state="TX", postal="77449")
    calls: list[str] = []

    def counting_get(url, params):
        calls.append(params["street"])
        return _osm({"21788 Katy Freeway": (29.78, -95.76)})(url, params)

    _run(conn, post=_responder({}), get=counting_get)
    conn.execute("UPDATE locations SET lat=NULL, lon=NULL")  # force a re-fill
    conn.commit()
    _run(conn, post=_responder({}), get=counting_get)

    assert calls == ["21788 Katy Freeway"], "OSM must not be asked twice for one address"


def test_a_failing_nominatim_request_costs_only_that_row(conn):
    _store(conn, street="21788 Katy Freeway", city="Katy", state="TX", postal="77449")

    def broken(url, params):
        raise OSError("connection reset")

    stats = _run(conn, post=_responder({}), get=broken)

    assert stats.still_dark == 1
    assert conn.execute("SELECT lat FROM locations").fetchone()[0] is None


def test_a_case_only_change_is_reported_as_cosmetic(conn):
    _store(conn, street="6290 HOLLYWOOD BLVD", city="LOS ANGELES", state="CA",
           postal="90028")
    post = _responder({"6290 HOLLYWOOD BLVD": "6290 HOLLYWOOD BLVD, LOS ANGELES, CA, 90028"})

    stats = _run(conn, dry_run=True, post=post)

    assert stats.cosmetic == 1
    assert stats.substantive == []
