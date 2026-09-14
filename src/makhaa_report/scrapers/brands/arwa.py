"""Arwa Yemeni Coffee."""

import re

from ..base import Scraper
from ..extract import text

# Google Maps *embed* URLs order their coordinates the other way round to
# place links: !2d is the longitude, !3d the latitude.
_EMBED_COORDS = re.compile(r"!2d(-?\d+\.\d+)!3d(-?\d+\.\d+)")


class Arwa(Scraper):
    """Arwa Yemeni Coffee.

    One section per store: an h2 name, a contact block whose paragraphs
    are address, email and phone in that order, and an embedded Google
    map the coordinates come from.

    The page lists no announced stores, so every row is recorded as open.
    """

    slug = "arwa"
    url = "https://arwacoffee.com/locations/"

    def collect(self) -> None:
        soup = self.page(self.url)

        for section in soup.select("section.location-section"):
            paragraphs = [text(p) for p in section.select(".info-address p")]
            if not paragraphs:
                continue

            phone = next((p for p in paragraphs[1:] if any(c.isdigit() for c in p)), None)
            frame = section.select_one(".location-map iframe")
            coords = _EMBED_COORDS.search(frame["src"]) if frame and frame.get("src") else None

            self.add(
                paragraphs[0],
                status="open",
                coords=(
                    (float(coords.group(2)), float(coords.group(1))) if coords else None
                ),
                phone=phone,
                fragment=text(section),
            )
