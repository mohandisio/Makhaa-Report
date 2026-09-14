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

QAHWAH_HOUSE_URL = "https://qahwahhouse.com/locations"


def _opening_hours(record: dict) -> str | None:
    """Opening hours joined verbatim from the schema.org specification."""
    spec = record.get("openingHoursSpecification") or []
    parts = [
        f"{entry.get('dayOfWeek', '').rsplit('/', 1)[-1]}: "
        f"{entry.get('opens')}-{entry.get('closes')}"
        for entry in spec
        if entry.get("opens")
    ]
    return "; ".join(parts) or None


def scrape_qahwah_house(fetch: Fetch) -> list[RawLocation]:
    """Qahwah House.

    The locations page embeds one schema.org CafeOrCoffeeShop block per
    store, carrying the address, phone, hours and coordinates — so no
    per-store page needs fetching. The sitemap lists no store pages, and
    several stores share a URL, which makes the address the identity.

    Nothing in the markup distinguishes an announced store from a trading
    one, so every row is recorded as open.
    """
    soup = BeautifulSoup(fetch(QAHWAH_HOUSE_URL), "lxml")
    rows: list[RawLocation] = []

    for block in soup.find_all("script", type="application/ld+json"):
        try:
            record = json.loads(block.string or "{}")
        except json.JSONDecodeError:
            log.warning("qahwah_house: unreadable ld+json block")
            continue
        if record.get("@type") != "CafeOrCoffeeShop":
            continue

        raw_address = (record.get("address") or {}).get("streetAddress", "")
        address = split_us_address(raw_address)
        if address is None:
            log.warning("qahwah_house: unparsed address %r", raw_address)
            continue
        street, city, state, postal = address
        geo = record.get("geo") or {}

        rows.append(
            RawLocation(
                brand="qahwah_house",
                street=street,
                city=city,
                state=state,
                postal=postal,
                status="open",
                lat=geo.get("latitude"),
                lon=geo.get("longitude"),
                phone=record.get("telephone") or None,
                hours=_opening_hours(record),
                source_url=record.get("url") or QAHWAH_HOUSE_URL,
                fragment=json.dumps(record, sort_keys=True),
            )
        )

    return rows


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
