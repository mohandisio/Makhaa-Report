"""Brands whose entire locator is one server-rendered HTML page."""

import logging
import re

from bs4 import BeautifulSoup

from ..fetch import Fetch
from ..models import RawLocation
from ..normalize import split_us_address

log = logging.getLogger("makhaa")

# Cheap pre-filter for text nodes worth handing to the address parser.
_LOOKS_LIKE_ADDRESS = re.compile(r"\b[A-Z]{2}\s+\d{5}\b")

# MOKAFÉ (mymokafe.com) is a different company from Moka & Co
# (mokanco.com). Both stay in the registry; never merge them.
MOKAFE_URL = "https://mymokafe.com/pages/locations"


def scrape_mokafe(fetch: Fetch) -> list[RawLocation]:
    """MOKAFÉ.

    Each store is a single bold line combining name and address, split
    either side of a colon, or of the bullet when no colon is present.

    This scraper reports what the site claims. Which of these storefronts
    trade as MOKAFÉ has been disputed by earlier research, and no scrape
    settles that — verify by hand before publishing the count.
    """
    soup = BeautifulSoup(fetch(MOKAFE_URL), "lxml")
    for tag in soup.find_all(["script", "style"]):
        tag.decompose()

    rows: list[RawLocation] = []
    seen: set[tuple[str, str]] = set()

    for node in soup.find_all(string=_LOOKS_LIKE_ADDRESS):
        text = " ".join(str(node).split())
        separator = ":" if ":" in text else "•"
        name, _, remainder = text.partition(separator)
        address = split_us_address(remainder.strip())
        if address is None:
            log.warning("mokafe: unparsed address %r", text)
            continue
        street, city, state, postal = address
        if (street, city) in seen:
            continue
        seen.add((street, city))

        rows.append(
            RawLocation(
                brand="mokafe",
                street=street,
                city=city,
                state=state,
                postal=postal,
                status="open",
                source_url=MOKAFE_URL,
                fragment=text,
            )
        )

    return rows


