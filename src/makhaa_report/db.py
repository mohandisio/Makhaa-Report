"""SQLite access — the only module that writes SQL."""

import dataclasses
import json
import sqlite3
from pathlib import Path

from . import config
from .models import Brand, Exclusion, GEOCODE_SOURCES, Location, RunStats, STATUSES

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
    name TEXT NOT NULL, street TEXT NOT NULL, city TEXT NOT NULL,
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
_MUTABLE = ("name", "postal", "status", "status_note", "phone", "hours",
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
_RETIRED_LOCATION_COLS = ("county", "tract", "cbsa")

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
    return conn


def _drop_retired_columns(conn: sqlite3.Connection) -> None:
    present = {r["name"] for r in conn.execute("PRAGMA table_info(locations)")}
    for column in _RETIRED_LOCATION_COLS:
        if column in present:
            conn.execute(f"ALTER TABLE locations DROP COLUMN {column}")
    conn.commit()


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


def dump_table(conn: sqlite3.Connection, name: str) -> tuple[list[str], list[tuple]]:
    """Full table contents in canonical order, for CSV export."""
    cur = conn.execute(f"SELECT * FROM {name} ORDER BY {_DUMP_ORDER[name]}")
    columns = [d[0] for d in cur.description]
    return columns, cur.fetchall()
