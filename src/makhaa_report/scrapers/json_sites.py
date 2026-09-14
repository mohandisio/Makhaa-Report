"""Brands whose locator data arrives as JSON, whether from an API or
embedded in the page."""

import json
import logging
import re

from bs4 import BeautifulSoup

from ..fetch import Fetch
from ..models import RawLocation
from ..normalize import split_us_address

log = logging.getLogger("makhaa")

SHIBAM_URL = (
    "https://shibamcoffee.com/wp-json/wp/v2/pages"
    "?slug=our-locations&_fields=content"
)

_HEADING = re.compile("^h[1-6]$")


def scrape_shibam(fetch: Fetch) -> list[RawLocation]:
    """Shibam Coffee Co.

    The WordPress REST endpoint returns the locations page as rendered
    HTML. Each store is a card holding hours, a Google Maps search link
    whose text is the address, and a phone number; the store's heading
    sits above the card rather than inside it.

    Headings are regional labels, not cities — "CLEVELAND, OH" is the
    North Olmsted store and "PHILLY, PA" is Philadelphia — so the address
    is the identity. A card announces itself with wording like "Soft
    opening coming soon" rather than a dedicated marker.
    """
    payload = json.loads(fetch(SHIBAM_URL))
    soup = BeautifulSoup(payload[0]["content"]["rendered"], "lxml")
    rows: list[RawLocation] = []

    for card in soup.select("div.primary-care-box"):
        link = next(
            (a for a in card.find_all("a", href=True) if "maps.google.com" in a["href"]),
            None,
        )
        if link is None:
            continue
        raw_address = " ".join(link.get_text(" ", strip=True).split())
        address = split_us_address(raw_address)
        if address is None:
            log.warning("shibam: unparsed address %r", raw_address)
            continue
        street, city, state, postal = address

        heading = card.find_previous(_HEADING)
        phone = next(
            (a["href"][4:] for a in card.find_all("a", href=True)
             if a["href"].startswith("tel:")),
            None,
        )
        text = " ".join(card.get_text(" ", strip=True).split())

        rows.append(
            RawLocation(
                brand="shibam",
                street=street,
                city=city,
                state=state,
                postal=postal,
                status="coming_soon" if "coming soon" in text.casefold() else "open",
                phone=phone,
                hours=text.split("•")[0].strip() or None,
                source_url=SHIBAM_URL,
                fragment=text,
            )
        )

    return rows
