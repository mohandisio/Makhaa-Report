"""Brands whose entire locator is one server-rendered HTML page."""

import logging
import re

from bs4 import BeautifulSoup

from ..fetch import Fetch
from ..models import RawLocation
from ..normalize import split_us_address

log = logging.getLogger("makhaa")

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
