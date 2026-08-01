"""Brands whose locator is spread across one page per state or store."""

import logging
import re

from bs4 import BeautifulSoup

from ..fetch import Fetch
from ..models import RawLocation
from ..normalize import split_us_address

log = logging.getLogger("makhaa")

HARAZ_SITEMAP = "https://harazcoffeehouse.com/sitemap.xml"
# The all-states summary page is stale; the per-state pages are current.
HARAZ_SUMMARY_SLUG = "locations-and-hours"

# Google Maps place links carry the store's coordinates twice: the "@"
# pair is the map viewport, the !3d/!4d pair is the place itself.
_MAPS_COORDS = re.compile(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)")


def _haraz_state_pages(fetch: Fetch) -> list[str]:
    """Discover the per-state locator pages from the sitemap.

    Read rather than hardcoded: Haraz adds states, and a fixed list would
    keep scraping happily while silently missing every store in a new one.
    """
    index = BeautifulSoup(fetch(HARAZ_SITEMAP), "xml")
    pages_sitemap = next(
        (loc.text for loc in index.find_all("loc") if "sitemap_pages" in loc.text), None
    )
    if pages_sitemap is None:
        raise ValueError("haraz: sitemap index has no pages sitemap")

    pages = BeautifulSoup(fetch(pages_sitemap), "xml")
    return sorted(
        loc.text
        for loc in pages.find_all("loc")
        if loc.text.rstrip("/").endswith("-locations")
        and HARAZ_SUMMARY_SLUG not in loc.text
    )


def scrape_haraz(fetch: Fetch) -> list[RawLocation]:
    """Haraz Coffee House.

    One page per state, each holding a card per store: heading, address,
    and a Google Maps link the coordinates come from. Card headings are
    not reliable — a Pearland store is headed "Plano" — so the address is
    the identity.

    The per-state pages carry no coming-soon markers; Haraz's announced
    pipeline is published elsewhere and is not visible to this scraper.
    """
    rows: list[RawLocation] = []

    for url in _haraz_state_pages(fetch):
        soup = BeautifulSoup(fetch(url), "lxml")
        for card in soup.select("li.multicolumn-list__item .multicolumn-card__info"):
            paragraph = card.select_one(".rte p")
            if paragraph is None:
                continue
            raw_address = " ".join(paragraph.get_text(" ", strip=True).split())
            address = split_us_address(raw_address)
            if address is None:
                log.warning("haraz: unparsed address %r on %s", raw_address, url)
                continue
            street, city, state, postal = address

            heading = card.find("h3")
            link = card.find("a", href=True)
            coords = _MAPS_COORDS.search(link["href"]) if link else None
            text = card.get_text(" ", strip=True).casefold()

            rows.append(
                RawLocation(
                    brand="haraz",
                    name=heading.get_text(strip=True) if heading else city,
                    street=street,
                    city=city,
                    state=state,
                    postal=postal,
                    status="coming_soon" if "coming soon" in text else "open",
                    lat=float(coords.group(1)) if coords else None,
                    lon=float(coords.group(2)) if coords else None,
                    source_url=url,
                    fragment=" ".join(card.get_text(" ", strip=True).split()),
                )
            )

    return rows
