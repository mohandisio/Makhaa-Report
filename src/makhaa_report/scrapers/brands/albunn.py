"""Albunn Coffee House."""

from .. import extract
from ..base import Scraper


class Albunn(Scraper):
    """Albunn Coffee House.

    A single-page SpotHopper marketing site with no locations page — every
    internal link points back to `/`. The one store lives as a root-level
    schema.org `Restaurant` block (not nested under an Organization or a
    location array), carrying the address as a `PostalAddress`, plus geo
    coordinates and a phone number. There is no
    `openingHoursSpecification`, so hours are never published here.

    Single location, so nothing to dedupe and no coming-soon or non-US
    rows to drop.
    """

    slug = "albunn"
    url = "https://albunncoffee.com/"

    def collect(self) -> None:
        soup = self.page(self.url)

        for record in extract.schema_records(soup, "Restaurant"):
            address = record.get("address") or {}
            raw_address = extract.postal_address(address)
            geo = record.get("geo") or {}

            self.add(
                raw_address,
                status="open",
                coords=(geo.get("latitude"), geo.get("longitude")),
                phone=record.get("telephone") or None,
                fragment=raw_address,
            )
