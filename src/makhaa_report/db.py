"""SQLite access — the only module that writes SQL."""

import dataclasses
import json
import logging
import sqlite3
from pathlib import Path

from . import config
from .models import Brand, Exclusion, GEOCODE_SOURCES, Location, RunStats, STATUSES

log = logging.getLogger("makhaa")

_STATUS_LIST = ",".join(f"'{s}'" for s in STATUSES)
_GEOSRC_LIST = ",".join(f"'{s}'" for s in GEOCODE_SOURCES)

_DDL = f"""
CREATE TABLE IF NOT EXISTS brands (
    slug TEXT PRIMARY KEY, display_name TEXT NOT NULL, locator_url TEXT NOT NULL,
    method TEXT NOT NULL CHECK (method IN ('scrape','manual')),
    band_low INTEGER NOT NULL, band_high INTEGER NOT NULL,
    franchises INTEGER NOT NULL DEFAULT 0, hq TEXT,
    alt_domains TEXT,
    notes TEXT
);
CREATE TABLE IF NOT EXISTS exclusions (
    domain TEXT PRIMARY KEY, reason TEXT NOT NULL,
    related_brand TEXT REFERENCES brands(slug)
);
CREATE TABLE IF NOT EXISTS locations (
    uid TEXT PRIMARY KEY,
    brand TEXT NOT NULL REFERENCES brands(slug),
    street TEXT NOT NULL, city TEXT NOT NULL,
    state TEXT NOT NULL, postal TEXT,
    lat REAL, lon REAL,
    geocode_source TEXT CHECK (geocode_source IN ({_GEOSRC_LIST})),
    geocode_flagged INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'unknown' CHECK (status IN ({_STATUS_LIST})),
    status_note TEXT, phone TEXT, hours TEXT,
    source_url TEXT, is_manual INTEGER NOT NULL DEFAULT 0,
    first_seen TEXT NOT NULL, last_seen TEXT NOT NULL,
    UNIQUE (brand, street, city, state)
);
CREATE INDEX IF NOT EXISTS idx_locations_brand ON locations(brand);
CREATE INDEX IF NOT EXISTS idx_locations_state ON locations(state);
CREATE INDEX IF NOT EXISTS idx_locations_status ON locations(status);
CREATE TABLE IF NOT EXISTS runs (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL, finished_at TEXT,
    brands_succeeded TEXT, brands_failed TEXT,
    total_rows INTEGER
);
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES runs(run_id),
    uid TEXT NOT NULL,
    observed_at TEXT NOT NULL, status TEXT NOT NULL,
    fragment TEXT,
    UNIQUE (run_id, uid)
);
CREATE INDEX IF NOT EXISTS idx_snapshots_uid ON snapshots(uid);
"""

# Every Location field is a column except transient `fragment`.
_LOCATION_COLS = tuple(
    f.name for f in dataclasses.fields(Location) if f.name != "fragment"
)

# Fields a fresh scrape may overwrite on an existing row. first_seen is
# never touched; coordinates only when the incoming row carries its own.
_MUTABLE = ("postal", "status", "status_note", "phone", "hours",
            "source_url", "is_manual", "last_seen")

_UPSERT = (
    f"INSERT INTO locations ({','.join(_LOCATION_COLS)}) "
    f"VALUES ({','.join('?' * len(_LOCATION_COLS))}) "
    "ON CONFLICT(uid) DO UPDATE SET "
    + ", ".join(f"{c}=excluded.{c}" for c in _MUTABLE)
    + """,
    lat = CASE WHEN excluded.lat IS NOT NULL THEN excluded.lat ELSE lat END,
    lon = CASE WHEN excluded.lon IS NOT NULL THEN excluded.lon ELSE lon END,
    geocode_source = CASE WHEN excluded.lat IS NOT NULL
                          THEN excluded.geocode_source ELSE geocode_source END"""
)

# Columns an older database may still carry. CREATE TABLE IF NOT EXISTS
# leaves an existing table alone, so dropping a column from _DDL is not
# enough on its own.
_RETIRED_LOCATION_COLS = ("county", "tract", "cbsa", "name")

# Canonical row order for exports — keeps weekly git diffs readable.
_DUMP_ORDER = {
    "locations": "brand, state, city, street",
    "brands": "slug",
    "runs": "run_id",
    "exclusions": "domain",
    "snapshots": "id",
}


def connect(path: Path = config.DB_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(_DDL)
    _drop_retired_columns(conn)
    _widen_geocode_sources(conn)
    _rekey_stale_uids(conn)
    return conn


def _rekey_stale_uids(conn: sqlite3.Connection) -> None:
    """Move rows whose uid predates the current normalizer.

    The uid is a hash of the address, so widening an abbreviation re-keys
    every row that uses it. Left alone, the next scrape would compute the
    new uid, find no row under it, and insert the store a second time.
    Recomputing here means a normalizer change converges instead of
    quietly splitting the census in two.
    """
    from .normalize import make_uid

    rows = conn.execute(
        "SELECT uid, brand, street, city, state FROM locations"
    ).fetchall()
    taken = {r["uid"] for r in rows}
    moved = 0
    for row in rows:
        current = make_uid(row["brand"], row["street"], row["city"], row["state"])
        if current == row["uid"]:
            continue
        if current in taken:
            log.warning(
                "%s: '%s, %s' now shares an identity with another row — "
                "left in place; one of them is a duplicate to drop by hand.",
                row["brand"], row["street"], row["city"],
            )
            continue
        rekey_location(conn, row["uid"], current, row["street"], row["city"],
                       _postal_of(conn, row["uid"]))
        taken.discard(row["uid"])
        taken.add(current)
        moved += 1
    if moved:
        log.info("re-keyed %d rows onto the current normalizer", moved)
        conn.commit()


def _postal_of(conn: sqlite3.Connection, uid: str) -> str | None:
    return conn.execute("SELECT postal FROM locations WHERE uid=?", (uid,)).fetchone()[0]


def _drop_retired_columns(conn: sqlite3.Connection) -> None:
    present = {r["name"] for r in conn.execute("PRAGMA table_info(locations)")}
    for column in _RETIRED_LOCATION_COLS:
        if column in present:
            conn.execute(f"ALTER TABLE locations DROP COLUMN {column}")
    conn.commit()


_LOCATION_INDEXES = ("idx_locations_brand", "idx_locations_state", "idx_locations_status")


def _widen_geocode_sources(conn: sqlite3.Connection) -> None:
    """Rebuild locations when its geocode_source CHECK is out of date.

    SQLite cannot alter a CHECK constraint, so adding a geocoder means
    copying the table. Indexes travel with the renamed original, so they
    are dropped first and let the DDL recreate them.
    """
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='locations'"
    ).fetchone()
    if row is None or _GEOSRC_LIST in row[0]:
        return
    columns = ",".join(_LOCATION_COLS)
    with conn:
        conn.execute("ALTER TABLE locations RENAME TO locations_old")
        for index in _LOCATION_INDEXES:
            conn.execute(f"DROP INDEX IF EXISTS {index}")
        conn.executescript(_DDL)
        conn.execute(
            f"INSERT INTO locations ({columns}) SELECT {columns} FROM locations_old"
        )
        conn.execute("DROP TABLE locations_old")


def sync_registry(conn: sqlite3.Connection, brands: tuple[Brand, ...],
                  exclusions: tuple[Exclusion, ...]) -> None:
    for b in brands:
        conn.execute(
            """INSERT INTO brands (slug, display_name, locator_url, method, band_low,
                                   band_high, franchises, hq, alt_domains, notes)
               VALUES (?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(slug) DO UPDATE SET
                 display_name=excluded.display_name, locator_url=excluded.locator_url,
                 method=excluded.method, band_low=excluded.band_low,
                 band_high=excluded.band_high, franchises=excluded.franchises,
                 hq=excluded.hq, alt_domains=excluded.alt_domains, notes=excluded.notes""",
            (b.slug, b.display_name, b.locator_url, b.method, b.band[0], b.band[1],
             b.franchises, b.hq, json.dumps(list(b.alt_domains)), b.notes),
        )
    for e in exclusions:
        conn.execute(
            """INSERT INTO exclusions (domain, reason, related_brand) VALUES (?,?,?)
               ON CONFLICT(domain) DO UPDATE SET
                 reason=excluded.reason, related_brand=excluded.related_brand""",
            (e.domain, e.reason, e.related_brand),
        )
    conn.commit()


def start_run(conn: sqlite3.Connection, started_at: str) -> int:
    cur = conn.execute("INSERT INTO runs (started_at) VALUES (?)", (started_at,))
    conn.commit()
    return cur.lastrowid


def finish_run(conn: sqlite3.Connection, stats: RunStats, finished_at: str) -> None:
    conn.execute(
        """UPDATE runs SET finished_at=?, brands_succeeded=?, brands_failed=?, total_rows=?
           WHERE run_id=?""",
        (finished_at, json.dumps(stats.brands_succeeded), json.dumps(stats.brands_failed),
         stats.total_rows, stats.run_id),
    )
    conn.commit()


def insert_snapshot(conn: sqlite3.Connection, run_id: int, uid: str,
                    observed_at: str, status: str, fragment: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO snapshots (run_id, uid, observed_at, status, fragment) "
        "VALUES (?,?,?,?,?)",
        (run_id, uid, observed_at, status, fragment),
    )


def upsert_location(conn: sqlite3.Connection, loc: Location) -> None:
    conn.execute(_UPSERT, tuple(getattr(loc, c) for c in _LOCATION_COLS))


def rekey_location(conn: sqlite3.Connection, old_uid: str, new_uid: str,
                   street: str, city: str, postal: str | None) -> None:
    """Store a corrected address, moving the row to the uid it now hashes to.

    Updating in place rather than inserting the corrected row is what
    keeps one store one row: an insert would leave the uncorrected
    original behind with nothing pointing at it. Snapshots follow the
    row so its history stays attached.
    """
    conn.execute(
        "UPDATE locations SET uid=?, street=?, city=?, postal=? WHERE uid=?",
        (new_uid, street, city, postal, old_uid),
    )
    if new_uid != old_uid:
        conn.execute("UPDATE snapshots SET uid=? WHERE uid=?", (new_uid, old_uid))


def set_coordinates(conn: sqlite3.Connection, uid: str, lat: float, lon: float,
                    source: str) -> None:
    conn.execute(
        "UPDATE locations SET lat=?, lon=?, geocode_source=? WHERE uid=?",
        (lat, lon, source, uid),
    )


def set_flagged(conn: sqlite3.Connection, uid: str, flagged: bool) -> None:
    conn.execute("UPDATE locations SET geocode_flagged=? WHERE uid=?",
                 (int(flagged), uid))


def dump_table(conn: sqlite3.Connection, name: str) -> tuple[list[str], list[tuple]]:
    """Full table contents in canonical order, for CSV export."""
    cur = conn.execute(f"SELECT * FROM {name} ORDER BY {_DUMP_ORDER[name]}")
    columns = [d[0] for d in cur.description]
    return columns, cur.fetchall()


def location_counts(conn: sqlite3.Connection) -> dict[str, int]:
    """Rows per brand from the last run, used to order the next one."""
    rows = conn.execute(
        "SELECT brand, COUNT(*) n FROM locations GROUP BY brand"
    ).fetchall()
    return {r["brand"]: r["n"] for r in rows}
