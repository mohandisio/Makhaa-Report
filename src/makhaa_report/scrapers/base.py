"""Thin base class for brand scrapers.

Each brand owns its own crawl: how many pages it fetches, in what order,
and how it reads a card or a script block into an address. The base class
only carries what every brand needs regardless of that shape — fetching a
page into a parsed document, and turning one candidate address into a
`RawLocation` with the dedupe and warning behaviour that all of them
share. A brand subclass sets `slug` and `url`, implements `collect()` to
walk its own pages and call `add()` for each candidate, and leaves parsing
oddities to itself.
"""

import logging

from bs4 import BeautifulSoup

from ..fetch import Fetch
from ..models import RawLocation
from ..normalize import split_us_address

log = logging.getLogger("makhaa")


class Scraper:
    slug: str = ""
    url: str = ""
    quiet: bool = False

    def __init__(self, fetch: Fetch) -> None:
        self.fetch = fetch
        self.rows: list[RawLocation] = []
        self.seen: set[tuple[str, str, str]] = set()

    @classmethod
    def scrape(cls, fetch: Fetch) -> list[RawLocation]:
        return cls(fetch).run()

    def run(self) -> list[RawLocation]:
        self.collect()
        return self.rows

    def collect(self) -> None:
        raise NotImplementedError

    def page(self, url: str, parser: str = "lxml") -> BeautifulSoup:
        return BeautifulSoup(self.fetch(url), parser)

    def add(
        self,
        raw_address: str,
        *,
        status: str = "open",
        coords: tuple[float | None, float | None] | None = None,
        phone: str | None = None,
        hours: str | None = None,
        source_url: str | None = None,
        fragment: str | None = None,
    ) -> bool:
        address = split_us_address(raw_address)
        if address is None:
            if not self.quiet:
                log.warning(
                    "%s: unparsed address %r on %s",
                    self.slug,
                    raw_address,
                    source_url or self.url,
                )
            return False
        street, city, state, postal = address

        key = (street.casefold(), city.casefold(), state)
        if key in self.seen:
            return False
        self.seen.add(key)

        self.rows.append(
            RawLocation(
                brand=self.slug,
                street=street,
                city=city,
                state=state,
                postal=postal,
                status=status,
                lat=coords[0] if coords else None,
                lon=coords[1] if coords else None,
                phone=phone,
                hours=hours,
                source_url=source_url or self.url,
                fragment=raw_address if fragment is None else fragment,
            )
        )
        return True
