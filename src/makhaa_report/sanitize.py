"""Find the rows a geocoder could not settle, so a human can settle them.

Two things go wrong that no automatic pass can fix. An address no
gazetteer recognises may be a typo, a truncation, or a street too new to
be in the files — only a person with a browser can tell which. And a
coordinate a locator published may be plain wrong in a way no bounds
check catches, because it is still inside the country.

Nothing here writes. It reads the caches `geocode` already filled, so
building the queue costs no requests.
"""

import sqlite3
from dataclasses import dataclass

from . import config, db, geo, manual
from .normalize import make_uid, split_unit

#: Why a row is in the queue.
KINDS = ("unconfirmed", "coordinate")


@dataclass
class Finding:
    """One row that needs a person, and everything known about it."""

    uid: str
    brand: str
    street: str
    city: str
    state: str
    postal: str | None
    lat: float | None
    lon: float | None
    kind: str
    census: geo.Match | None = None
    osm: geo.Match | None = None
    #: How far the stored coordinate sits from the Census match, in km.
    drift: float | None = None

    @property
    def address(self) -> str:
        zip_ = f" {self.postal}" if self.postal else ""
        return f"{self.street}, {self.city}, {self.state}{zip_}"

    @property
    def why(self) -> str:
        if self.kind == "coordinate":
            return f"coordinate is {self.drift:.0f} km from the matched address"
        if self.census is not None and self.census.matched:
            return "census resolved it to a different address"
        return "no gazetteer recognises the address"


def _query(row) -> geo.Query:
    return geo.Query(row["uid"], split_unit(row["street"])[0],
                     row["city"], row["state"], row["postal"])


def find_problems(conn: sqlite3.Connection) -> list[Finding]:
    """Every row a source contradicts or none can confirm.

    Rows already corrected by hand are left out: somebody looked, and
    that outranks a gazetteer that has never heard of the street.
    """
    census = geo.MatchCache(config.GEO_DIR / "census.json")
    osm = geo.MatchCache(config.GEO_DIR / "nominatim.json")

    findings: list[Finding] = []
    for row in conn.execute(
        "SELECT uid, brand, street, city, state, postal, lat, lon, is_manual "
        "FROM locations ORDER BY brand, state, city, street"
    ):
        if row["is_manual"]:
            continue
        query = _query(row)
        c = census.get(query)
        o = osm.get(query)
        resolution = geo.resolve(row["uid"], c, row["street"], row["city"], row["postal"])

        if resolution.verdict in ("inexact", "unmatched") and not (o and o.matched):
            findings.append(_make(row, "unconfirmed", c, o))
            continue

        if (row["lat"] is not None and c is not None and c.matched and c.exact
                and c.lat is not None):
            drift = geo.distance_km(row["lat"], row["lon"], c.lat, c.lon)
            if drift > geo.COORDINATE_TOLERANCE_KM:
                findings.append(_make(row, "coordinate", c, o, drift))

    return findings


def adopt_coordinates(conn: sqlite3.Connection, findings: list[Finding],
                      *, dry_run: bool = False) -> list[Finding]:
    """Replace a wrong locator coordinate with the one Census matched.

    Only for findings where Census matched the address exactly, so the
    coordinate is evidence about this address rather than a guess about
    a similar one. Written to the database and recorded as an override,
    because a locator that publishes its head office for a branch will
    publish it again next week.
    """
    adopted: list[Finding] = []
    for f in findings:
        if f.kind != "coordinate" or f.census is None or f.census.lat is None:
            continue
        adopted.append(f)
        if dry_run:
            continue
        db.set_coordinates(conn, f.uid, f.census.lat, f.census.lon, "census")
        db.set_flagged(conn, f.uid, False)
        manual.append_override(
            f.uid,
            {"lat": f"{f.census.lat:.6f}", "lon": f"{f.census.lon:.6f}"},
            note=f"locator put this {f.drift:.0f} km away at "
                 f"{f.lat:.4f},{f.lon:.4f}; census matched the address exactly",
        )
    if adopted and not dry_run:
        conn.commit()
    return adopted


def correct_address(conn: sqlite3.Connection, uid: str, fields: dict[str, str],
                    note: str) -> str:
    """Write a researched correction, and return the uid the row now has.

    The address feeds the uid, so a corrected row moves; the history
    moves with it. Recorded as an override too, or the next scrape would
    republish whatever the locator says and undo the work.
    """
    row = conn.execute(
        "SELECT brand, street, city, state, postal FROM locations WHERE uid=?",
        (uid,),
    ).fetchone()
    if row is None:
        raise KeyError(f"no location with uid {uid}")

    street = fields.get("street", row["street"])
    city = fields.get("city", row["city"])
    postal = fields.get("postal", row["postal"])
    new_uid = make_uid(row["brand"], street, city, row["state"])

    taken = {r[0] for r in conn.execute("SELECT uid FROM locations")}
    with conn:
        if new_uid != uid and new_uid in taken:
            db.merge_into(conn, uid, new_uid)
        else:
            db.rekey_location(conn, uid, new_uid, street, city, postal)
        if "lat" in fields and "lon" in fields:
            db.set_coordinates(conn, new_uid, float(fields["lat"]),
                               float(fields["lon"]), "manual")
        db.set_flagged(conn, new_uid, False)
        conn.execute("UPDATE locations SET is_manual=1 WHERE uid=?", (new_uid,))
    manual.append_override(uid, fields, note=note)
    return new_uid


def _make(row, kind: str, census, osm, drift: float | None = None) -> Finding:
    return Finding(
        uid=row["uid"], brand=row["brand"], street=row["street"],
        city=row["city"], state=row["state"], postal=row["postal"],
        lat=row["lat"], lon=row["lon"], kind=kind,
        census=census, osm=osm, drift=drift,
    )
