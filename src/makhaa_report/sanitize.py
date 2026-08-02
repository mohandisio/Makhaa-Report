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

from . import config, geo
from .normalize import split_unit

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


def _make(row, kind: str, census, osm, drift: float | None = None) -> Finding:
    return Finding(
        uid=row["uid"], brand=row["brand"], street=row["street"],
        city=row["city"], state=row["state"], postal=row["postal"],
        lat=row["lat"], lon=row["lon"], kind=kind,
        census=census, osm=osm, drift=drift,
    )
