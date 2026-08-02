"""Brands whose locator is spread across one page per state or store."""

import logging
import re

from bs4 import BeautifulSoup

from ..fetch import Fetch
from ..models import RawLocation
from ..normalize import US_STATE_NAMES, split_us_address

log = logging.getLogger("makhaa")

_LOOKS_LIKE_ADDRESS = re.compile(r"\b[A-Z]{2}\s+\d{5}\b")

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


ORIGINAL_MOCHA_URL = "https://originalmocha.com"


def _original_mocha_store_pages(fetch: Fetch) -> list[str]:
    """Find store pages by their slug.

    The sitemap omits them and the home page carries no address, but each
    store has its own page slugged city-then-state ("/murphy-texas/",
    "/tinley-park-illinois/"). Matching the trailing state name finds new
    stores without fetching every page on the site.
    """
    soup = BeautifulSoup(fetch(ORIGINAL_MOCHA_URL), "lxml")
    pages = set()
    for link in soup.find_all("a", href=True):
        href = link["href"]
        if not href.startswith(ORIGINAL_MOCHA_URL):
            continue
        slug = href[len(ORIGINAL_MOCHA_URL) :].strip("/")
        if not slug or "/" in slug:
            continue
        words = slug.replace("-", " ")
        if any(words.endswith(state) for state in US_STATE_NAMES):
            pages.add(href)
    return sorted(pages)


def scrape_original_mocha(fetch: Fetch) -> list[RawLocation]:
    """Original Mocha.

    One page per store, discovered from the home page by slug. Each page
    carries a single address; the site publishes no coordinates.
    """
    rows: list[RawLocation] = []

    for url in _original_mocha_store_pages(fetch):
        soup = BeautifulSoup(fetch(url), "lxml")
        for tag in soup.find_all(["script", "style"]):
            tag.decompose()
        for node in soup.find_all(string=_LOOKS_LIKE_ADDRESS):
            address = split_us_address(" ".join(str(node).split()))
            if address is None:
                continue
            street, city, state, postal = address
            rows.append(
                RawLocation(
                    brand="original_mocha",
                    street=street,
                    city=city,
                    state=state,
                    postal=postal,
                    status="open",
                    source_url=url,
                    fragment=" ".join(str(node).split()),
                )
            )
            break

    return rows
