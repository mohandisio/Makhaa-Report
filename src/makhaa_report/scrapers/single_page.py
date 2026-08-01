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

# /pages/locations redirects here. Store detail pages live at
# mokanco.com/<slug>/, but every address is already on this page, so
# scraping the detail pages too would double-count.
MOKA_URL = "https://mokanco.com/locations/"


def scrape_moka_and_co(fetch: Fetch) -> list[RawLocation]:
    """Moka & Co.

    One WordPress query block per store: title links to the store page,
    an excerpt holds the address, and a "Coming Soon" term marks the
    pipeline. The corporate contact block in the mobile menu carries HQ
    addresses that are not stores, so only post blocks are read.

    The listing repeats a store when it belongs to more than one grouping;
    the first entry for an address wins.
    """
    soup = BeautifulSoup(fetch(MOKA_URL), "lxml")
    rows: list[RawLocation] = []
    seen: set[str] = set()

    for post in soup.select("li.wp-block-post"):
        excerpt = post.select_one("p.wp-block-post-excerpt__excerpt")
        if excerpt is None:
            continue
        raw_address = " ".join(excerpt.get_text(strip=True).split())
        address = split_us_address(raw_address)
        if address is None:
            log.warning("moka_and_co: unparsed address %r", raw_address)
            continue
        street, city, state, postal = address
        if raw_address in seen:
            continue
        seen.add(raw_address)

        title = post.select_one("h6.wp-block-post-title")
        link = title.find("a") if title else None
        terms = [t.get_text(strip=True).casefold() for t in post.select(".wp-block-post-terms a")]

        rows.append(
            RawLocation(
                brand="moka_and_co",
                name=title.get_text(strip=True) if title else city,
                street=street,
                city=city,
                state=state,
                postal=postal,
                status="coming_soon" if "coming soon" in terms else "open",
                source_url=link["href"] if link and link.get("href") else MOKA_URL,
                fragment=" ".join(post.get_text(" ", strip=True).split()),
            )
        )

    return rows


ARWA_URL = "https://arwacoffee.com/locations/"

# Google Maps *embed* URLs order their coordinates the other way round to
# place links: !2d is the longitude, !3d the latitude.
_EMBED_COORDS = re.compile(r"!2d(-?\d+\.\d+)!3d(-?\d+\.\d+)")


def scrape_arwa(fetch: Fetch) -> list[RawLocation]:
    """Arwa Yemeni Coffee.

    One section per store: an h2 name, a contact block whose paragraphs
    are address, email and phone in that order, and an embedded Google
    map the coordinates come from.

    The page lists no announced stores, so every row is recorded as open.
    """
    soup = BeautifulSoup(fetch(ARWA_URL), "lxml")
    rows: list[RawLocation] = []

    for section in soup.select("section.location-section"):
        paragraphs = [
            " ".join(p.get_text(" ", strip=True).split())
            for p in section.select(".info-address p")
        ]
        if not paragraphs:
            continue
        address = split_us_address(paragraphs[0])
        if address is None:
            log.warning("arwa: unparsed address %r", paragraphs[0])
            continue
        street, city, state, postal = address

        phone = next((p for p in paragraphs[1:] if any(c.isdigit() for c in p)), None)
        heading = section.find("h2")
        frame = section.select_one(".location-map iframe")
        coords = _EMBED_COORDS.search(frame["src"]) if frame and frame.get("src") else None

        rows.append(
            RawLocation(
                brand="arwa",
                name=heading.get_text(" ", strip=True) if heading else city,
                street=street,
                city=city,
                state=state,
                postal=postal,
                status="open",
                lat=float(coords.group(2)) if coords else None,
                lon=float(coords.group(1)) if coords else None,
                phone=phone,
                source_url=ARWA_URL,
                fragment=" ".join(section.get_text(" ", strip=True).split()),
            )
        )

    return rows


MATARI_URL = "https://mataricoffee.com/locations"


def scrape_matari(fetch: Fetch) -> list[RawLocation]:
    """Matari Coffee.

    One card per store: a title link carrying the store name and phone,
    an <address>, and "coming soon" wording for announced stores.

    Two kinds of card produce no row. The Mississauga store is Canadian
    and falls out of the US address parse on its own. Three announced
    markets are published as a bare "Dallas, TX" with no street; they are
    logged and skipped, so Matari's announced presence in Texas and
    Georgia is not represented here.
    """
    soup = BeautifulSoup(fetch(MATARI_URL), "lxml")
    rows: list[RawLocation] = []

    for card in soup.select("div.service__item-3"):
        block = card.find("address")
        if block is None:
            continue
        raw_address = " ".join(block.get_text(" ", strip=True).split())
        address = split_us_address(raw_address)
        if address is None:
            log.warning("matari: skipping unparsed address %r", raw_address)
            continue
        street, city, state, postal = address

        link = card.select_one("a.woocomerce__feature-producttitle")
        heading = card.select_one("span.primary-color")
        phone = None
        if link is not None:
            phone = next(
                (t for t in link.get_text(" ", strip=True).split() if t.startswith("+")),
                None,
            )
        text = " ".join(card.get_text(" ", strip=True).split())

        rows.append(
            RawLocation(
                brand="matari",
                name=heading.get_text(strip=True) if heading else city,
                street=street,
                city=city,
                state=state,
                postal=postal,
                status="coming_soon" if "coming soon" in text.casefold() else "open",
                phone=phone,
                source_url=link["href"] if link and link.get("href") else MATARI_URL,
                fragment=text,
            )
        )

    return rows


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
                name=label.strip() or city,
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
                name=city,
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
