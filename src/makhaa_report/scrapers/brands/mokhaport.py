"""Mokhaport."""

import json

from ..base import Scraper
from ..extract import postal_address, schema_records


class Mokhaport(Scraper):
    """Mokhaport.

    Not to be confused with Port Coffee Co. (portcoffeeco.com, ``port.py``) —
    Mokhaport (mokhaport.com) is an unrelated single-shop business; the
    similar name is a coincidence.

    A single store in Tucker, GA. The home page is server-rendered (the
    site is a Vite-built SPA, but the initial HTML response already
    carries the full JSON-LD, so no app bundle needs fetching) and there
    is no locations page to crawl. One schema.org CafeOrCoffeeShop block
    in the head carries the address, geo and phone; unlike
    qahwah_house's single-line `streetAddress`, the address here is
    split across `streetAddress`, `addressLocality`, `addressRegion` and
    `postalCode`, so those are joined before parsing. Two Product blocks
    for bagged coffee also use ld+json but carry no address and are
    skipped. The site publishes no hours and no coming-soon marker; it
    reads as an open, trading shop.
    """

    slug = "mokhaport"
    url = "https://mokhaport.com"

    def collect(self) -> None:
        soup = self.page(self.url)

        for record in schema_records(soup, "CafeOrCoffeeShop"):
            address = record.get("address") or {}
            geo = record.get("geo") or {}

            self.add(
                postal_address(address),
                status="open",
                coords=(geo.get("latitude"), geo.get("longitude")),
                phone=record.get("telephone") or None,
                source_url=record.get("url") or self.url,
                fragment=json.dumps(record, sort_keys=True),
            )
