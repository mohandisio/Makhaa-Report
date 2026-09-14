"""Port Coffee Co."""

import re

from ..base import Scraper
from ..extract import bundle_source, place_coords

# Minified object literals: {id:1,name:"...",address:"...",...}
_RECORD = re.compile(r'\{id:\d+,name:"[^"]*",address:"[^"]*".{0,800}?\}', re.S)
_FIELD = re.compile(r'(\w+):"([^"]*)"')


class Port(Scraper):
    """Port Coffee Co.

    Stores are object literals in the bundle carrying name, address,
    hours, phone, a status field and a Google Maps place link, so the
    coordinates come along with them.
    """

    slug = "port"
    url = "https://portcoffeeco.com"

    def collect(self) -> None:
        for record in _RECORD.findall(bundle_source(self.fetch, self.url)):
            fields = dict(_FIELD.findall(record))
            self.add(
                fields.get("address", ""),
                status=fields.get("status", "open"),
                coords=place_coords(fields.get("mapUrl", "")),
                phone=fields.get("phone") or None,
                hours=fields.get("hours") or None,
                fragment=record,
            )
