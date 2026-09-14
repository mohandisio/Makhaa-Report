"""Brands whose site is a single-page app with no server-rendered HTML.

The page itself is an empty shell — no links, no text — but the store
data ships inside the JavaScript bundle it loads. Reading the bundle
avoids needing a browser at the cost of parsing minified source, so
these scrapers are the most fragile in the set: a rebuild that changes
how the data is written will break them, and the break is silent until
somebody reads the rows.
"""

import logging
import re

from bs4 import BeautifulSoup

from ..fetch import Fetch
from ..models import RawLocation
from ..normalize import split_us_address

log = logging.getLogger("makhaa")

QISHR_URL = "https://qishrcoffeehouse.co"

_BUNDLE = re.compile(r'src="(/assets/[^"]+\.js)"')
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
