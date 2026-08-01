"""Brands whose entire locator is one server-rendered HTML page."""

import logging

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
