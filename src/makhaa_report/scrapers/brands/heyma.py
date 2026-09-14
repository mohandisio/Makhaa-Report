"""Heyma."""

import re

from ..base import Scraper
from ..extract import text

# Heyma's map links are directions URLs, so the coordinates ride in the
# destination parameter rather than a place id.
_DADDR_COORDS = re.compile(r"daddr=(-?\d+\.\d+),(-?\d+\.\d+)")


class Heyma(Scraper):
    """Heyma.

    Each store is a link to Google directions whose text is the full
    address and whose href carries the coordinates. The heading above it
    is the street name rather than a place name, so the city is used.

    No announced stores are published.
    """

    slug = "heyma"
    url = "https://www.heymacoffeeca.com/locations"

    def collect(self) -> None:
        soup = self.page(self.url)

        for link in soup.select("a.restaurant-links[href*=maps]"):
            raw_address = text(link)
            coords = _DADDR_COORDS.search(link["href"])
            phone_link = link.find_next("a", href=re.compile("^tel:"))

            self.add(
                raw_address,
                status="open",
                coords=(
                    (float(coords.group(1)), float(coords.group(2))) if coords else None
                ),
                phone=phone_link.get_text(strip=True) if phone_link else None,
                fragment=raw_address,
            )
