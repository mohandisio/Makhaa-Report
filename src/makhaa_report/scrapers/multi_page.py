"""Brands whose locator is spread across one page per state or store."""

import logging
import re

from bs4 import BeautifulSoup

from ..fetch import Fetch
from ..models import RawLocation
from ..normalize import US_STATE_NAMES, split_us_address

log = logging.getLogger("makhaa")

_LOOKS_LIKE_ADDRESS = re.compile(r"\b[A-Z]{2}\s+\d{5}\b")

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
