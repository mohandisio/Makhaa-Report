"""Brands whose entire locator is one server-rendered HTML page."""

import json
import logging
import re

from bs4 import BeautifulSoup

from ..fetch import Fetch
from ..models import RawLocation
from ..normalize import split_us_address

log = logging.getLogger("makhaa")

# Cheap pre-filter for text nodes worth handing to the address parser.
_LOOKS_LIKE_ADDRESS = re.compile(r"\b[A-Z]{2}\s+\d{5}\b")

DELAH_URL = "https://delahcoffee.com/locations/"

# Store links point at Google, either a shortened g.co link or a full
# place URL; only the latter carries coordinates.
_PLACE_COORDS = re.compile(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)")


def scrape_delah(fetch: Fetch) -> list[RawLocation]:
    """Delah Coffee.

    Built with Elementor, so the per-store blocks carry no usable classes
    and two of them are rendered inside embedded Google widgets. The icon
    list is the one consistent listing: an entry per store reading
    "City: address", alongside phone, email and social entries that carry
    no address and are skipped.

    The page announces no stores, so every row is recorded as open.
    """
    soup = BeautifulSoup(fetch(DELAH_URL), "lxml")
    for tag in soup.find_all(["script", "style"]):
        tag.decompose()

    rows: list[RawLocation] = []
    seen: set[tuple[str, str]] = set()

    for entry in soup.select("span.elementor-icon-list-text"):
        text = " ".join(entry.get_text(" ", strip=True).split())
        label, _, remainder = text.partition(":")
        address = split_us_address(remainder.strip())
        if address is None:
            continue  # phone, email or a social link
        street, city, state, postal = address
        if (street, city) in seen:
            continue
        seen.add((street, city))

        link = entry.find_parent("a") or entry.find_previous("a")
        href = link.get("href") if link else None
        coords = _PLACE_COORDS.search(href) if href else None

        rows.append(
            RawLocation(
                brand="delah",
                street=street,
                city=city,
                state=state,
                postal=postal,
                status="open",
                lat=float(coords.group(1)) if coords else None,
                lon=float(coords.group(2)) if coords else None,
                source_url=href or DELAH_URL,
                fragment=text,
            )
        )

    return rows


# The Yemeni brand is qatracoffee.com. qatracafe.com is an unrelated
# Afghan chai cafe — see the exclusions in the registry.
QATRA_URL = "https://qatracoffee.com/"


def scrape_qatra(fetch: Fetch) -> list[RawLocation]:
    """Qatra Coffee.

    There is no locations page — /locations returns 404 — so the stores
    are read off the home page, where each address appears several times
    across header, cards and footer. Addresses are collected wherever
    they appear and deduplicated.

    One store publishes coordinates in a schema.org block; the others
    have none. No announced stores are published.
    """
    soup = BeautifulSoup(fetch(QATRA_URL), "lxml")

    coords: dict[str, tuple[float, float]] = {}
    for block in soup.find_all("script", type="application/ld+json"):
        try:
            record = json.loads(block.string or "{}")
        except json.JSONDecodeError:
            continue
        address = record.get("address") or {}
        geo = record.get("geo") or {}
        if record.get("@type") == "CafeOrCoffeeShop" and geo.get("latitude"):
            coords[address.get("streetAddress", "").casefold()] = (
                geo["latitude"],
                geo["longitude"],
            )

    for tag in soup.find_all(["script", "style"]):
        tag.decompose()

    rows: list[RawLocation] = []
    seen: set[tuple[str, str]] = set()

    for node in soup.find_all(string=_LOOKS_LIKE_ADDRESS):
        text = " ".join(str(node).split())
        address = split_us_address(text)
        if address is None:
            continue
        street, city, state, postal = address
        if (street, city) in seen:
            continue
        seen.add((street, city))
        point = coords.get(street.casefold())

        rows.append(
            RawLocation(
                brand="qatra",
                street=street,
                city=city,
                state=state,
                postal=postal,
                status="open",
                lat=point[0] if point else None,
                lon=point[1] if point else None,
                source_url=QATRA_URL,
                fragment=text,
            )
        )

    return rows


HEYMA_URL = "https://www.heymacoffeeca.com/locations"

# Heyma's map links are directions URLs, so the coordinates ride in the
# destination parameter rather than a place id.
_DADDR_COORDS = re.compile(r"daddr=(-?\d+\.\d+),(-?\d+\.\d+)")


def scrape_heyma(fetch: Fetch) -> list[RawLocation]:
    """Heyma.

    Each store is a link to Google directions whose text is the full
    address and whose href carries the coordinates. The heading above it
    is the street name rather than a place name, so the city is used.

    No announced stores are published.
    """
    soup = BeautifulSoup(fetch(HEYMA_URL), "lxml")
    for tag in soup.find_all(["script", "style"]):
        tag.decompose()

    rows: list[RawLocation] = []
    for link in soup.select("a.restaurant-links[href*=maps]"):
        raw_address = " ".join(link.get_text(" ", strip=True).split())
        address = split_us_address(raw_address)
        if address is None:
            log.warning("heyma: unparsed address %r", raw_address)
            continue
        street, city, state, postal = address

        coords = _DADDR_COORDS.search(link["href"])
        phone_link = link.find_next("a", href=re.compile("^tel:"))

        rows.append(
            RawLocation(
                brand="heyma",
                street=street,
                city=city,
                state=state,
                postal=postal,
                status="open",
                lat=float(coords.group(1)) if coords else None,
                lon=float(coords.group(2)) if coords else None,
                phone=phone_link.get_text(strip=True) if phone_link else None,
                source_url=HEYMA_URL,
                fragment=raw_address,
            )
        )

    return rows


CAFFEENA_URL = "https://caffeena.com/locations"

_HEADINGS = ["h1", "h2", "h3"]


def _caffeena_status(node) -> str:
    """Which section an address sits under.

    Caffeena splits the page into "Now Open Locations" and "Coming Soon
    Locations", with a per-store heading under each; walking back to the
    nearest section heading is what tells the two apart.
    """
    heading = node
    while True:
        heading = heading.find_previous(_HEADINGS)
        if heading is None:
            return "unknown"
        text = heading.get_text(" ", strip=True).casefold()
        if "coming soon" in text:
            return "coming_soon"
        if "now open" in text:
            return "open"


def scrape_caffeena(fetch: Fetch) -> list[RawLocation]:
    """Caffeena Coffee House.

    Addresses sit in plain paragraphs under a per-store heading, split
    across a now-open and a coming-soon section. The site publishes
    neither coordinates nor phone numbers.
    """
    soup = BeautifulSoup(fetch(CAFFEENA_URL), "lxml")
    for tag in soup.find_all(["script", "style"]):
        tag.decompose()

    rows: list[RawLocation] = []
    seen: set[tuple[str, str]] = set()

    for node in soup.find_all(string=_LOOKS_LIKE_ADDRESS):
        text = " ".join(str(node).split())
        address = split_us_address(text)
        if address is None:
            continue
        street, city, state, postal = address
        if (street, city) in seen:
            continue
        seen.add((street, city))

        heading = node.parent.find_previous(_HEADINGS)
        rows.append(
            RawLocation(
                brand="caffeena",
                street=street,
                city=city,
                state=state,
                postal=postal,
                status=_caffeena_status(node.parent),
                source_url=CAFFEENA_URL,
                fragment=text,
            )
        )

    return rows


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


