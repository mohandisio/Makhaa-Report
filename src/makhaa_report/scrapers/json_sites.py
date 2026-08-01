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

# Qamaria's /cafes page embeds a Storepoint map widget; the widget's own
# API returns the full location list. The map id comes from the embed's
# data-map-id attribute and changes only if they rebuild the map.
QAMARIA_URL = "https://api.storepoint.co/v1/165c3af3b9c727/locations"

QAHWAH_HOUSE_URL = "https://qahwahhouse.com/locations"

_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def _hours(record: dict) -> str | None:
    """Weekday opening hours, joined verbatim and unparsed."""
    parts = [f"{day}: {record[day]}" for day in _WEEKDAYS if record.get(day)]
    return "; ".join(parts) or None


def scrape_qamaria(fetch: Fetch) -> list[RawLocation]:
    """Qamaria Yemeni Coffee.

    Two kinds of entry are dropped: rows tagged `catering`, which are
    service-area listings that repeat an existing cafe's address and would
    double-count, and non-US rows (Canada, Saudi Arabia, Qatar).

    The feed carries no open/coming-soon flag, so every row is recorded as
    open — Qamaria's announced pipeline is not visible here.
    """
    payload = json.loads(fetch(QAMARIA_URL))
    rows: list[RawLocation] = []

    for record in payload["results"]["locations"]:
        if "catering" in (record.get("tags") or ""):
            continue
        address = split_us_address(record.get("streetaddress") or "")
        if address is None:
            continue  # non-US store
        street, city, state, postal = address
        rows.append(
            RawLocation(
                brand="qamaria",
                name=(record.get("name") or "").strip(),
                street=street,
                city=city,
                state=state,
                postal=postal,
                status="open",
                lat=record.get("loc_lat"),
                lon=record.get("loc_long"),
                phone=(record.get("phone") or "").strip() or None,
                hours=_hours(record),
                source_url=QAMARIA_URL,
                fragment=json.dumps(record, sort_keys=True),
            )
        )

    return rows


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
                name=record.get("name", "").strip(),
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
                name=heading.get_text(" ", strip=True) if heading else city,
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
