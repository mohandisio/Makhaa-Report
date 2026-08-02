"""Brands whose site is a single-page app with no server-rendered HTML.

The page itself is an empty shell — no links, no text — but the store
data ships inside the JavaScript bundle it loads. Reading the bundle
avoids needing a browser at the cost of parsing minified source, so
these scrapers are the most fragile in the set: a rebuild that changes
how the data is written will break them, and the row-count band is what
catches that.
"""

import logging
import re

from bs4 import BeautifulSoup

from ..fetch import Fetch
from ..models import RawLocation
from ..normalize import split_us_address

log = logging.getLogger("makhaa")

QISHR_URL = "https://qishrcoffeehouse.co"
PORT_URL = "https://portcoffeeco.com"

_BUNDLE = re.compile(r'src="(/assets/[^"]+\.js)"')
# Minified object literals: {id:1,name:"...",address:"...",...}
_RECORD = re.compile(r'\{id:\d+,name:"[^"]*",address:"[^"]*".{0,800}?\}', re.S)
_FIELD = re.compile(r'(\w+):"([^"]*)"')
# Google Maps place links inside those records carry the coordinates.
_PLACE_COORDS = re.compile(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)")
# A street literal followed within a few hundred characters by a
# "City, ST 12345" literal — how an address split across JSX children
# appears once minified.
_SPLIT_ADDRESS = re.compile(
    r'"(?P<street>\d{1,6}[^"]{3,44}?)"'
    r'.{0,240}?'  # the line-break element between them carries its own quotes
    r'"(?P<tail>[A-Za-z .\'-]{3,40},\s*[A-Z]{2}\s+\d{5})"',
    re.S,
)


def _bundle_source(fetch: Fetch, base_url: str) -> str:
    """Fetch the app bundle the shell page loads."""
    match = _BUNDLE.search(fetch(base_url))
    if match is None:
        raise ValueError(f"{base_url}: no app bundle found in the page shell")
    return fetch(base_url.rstrip("/") + match.group(1))


def scrape_port(fetch: Fetch) -> list[RawLocation]:
    """Port Coffee Co.

    Stores are object literals in the bundle carrying name, address,
    hours, phone, a status field and a Google Maps place link, so the
    coordinates come along with them.
    """
    rows: list[RawLocation] = []

    for record in _RECORD.findall(_bundle_source(fetch, PORT_URL)):
        fields = dict(_FIELD.findall(record))
        address = split_us_address(fields.get("address", ""))
        if address is None:
            log.warning("port: unparsed address %r", fields.get("address"))
            continue
        street, city, state, postal = address
        coords = _PLACE_COORDS.search(fields.get("mapUrl", ""))

        rows.append(
            RawLocation(
                brand="port",
                street=street,
                city=city,
                state=state,
                postal=postal,
                status=fields.get("status", "open"),
                lat=float(coords.group(1)) if coords else None,
                lon=float(coords.group(2)) if coords else None,
                phone=fields.get("phone") or None,
                hours=fields.get("hours") or None,
                source_url=PORT_URL,
                fragment=record,
            )
        )

    return rows


def scrape_qishr(fetch: Fetch) -> list[RawLocation]:
    """Qishr Coffee House.

    No store list — the single cafe's address is written straight into
    the footer markup, so it arrives as two adjacent string literals,
    street then "City, ST ZIP".
    """
    rows: list[RawLocation] = []
    seen: set[tuple[str, str]] = set()

    for match in _SPLIT_ADDRESS.finditer(_bundle_source(fetch, QISHR_URL)):
        address = split_us_address(f"{match['street']}, {match['tail']}")
        if address is None:
            continue
        street, city, state, postal = address
        if (street, city) in seen:
            continue
        seen.add((street, city))

        rows.append(
            RawLocation(
                brand="qishr",
                street=street,
                city=city,
                state=state,
                postal=postal,
                status="open",
                source_url=QISHR_URL,
                fragment=match.group(0),
            )
        )

    return rows
