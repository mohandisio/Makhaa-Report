"""Shibam Coffee Co."""

import json

from bs4 import BeautifulSoup

from ..base import Scraper


class Shibam(Scraper):
    """Shibam Coffee Co.

    The WordPress REST endpoint returns the locations page as rendered
    HTML. Each store is a card holding hours, a Google Maps search link
    whose text is the address, and a phone number; the store's heading
    sits above the card rather than inside it.

    Headings are regional labels, not cities — "CLEVELAND, OH" is the
    North Olmsted store and "PHILLY, PA" is Philadelphia — so the address
    is the identity. A card announces itself with wording like "Soft
    opening coming soon" rather than a dedicated marker.
    """

    slug = "shibam"
    url = (
        "https://shibamcoffee.com/wp-json/wp/v2/pages"
        "?slug=our-locations&_fields=content"
    )

    def collect(self) -> None:
        payload = json.loads(self.fetch(self.url))
        soup = BeautifulSoup(payload[0]["content"]["rendered"], "lxml")

        for card in soup.select("div.primary-care-box"):
            link = next(
                (a for a in card.find_all("a", href=True) if "maps.google.com" in a["href"]),
                None,
            )
            if link is None:
                continue
            raw_address = " ".join(link.get_text(" ", strip=True).split())

            phone = next(
                (a["href"][4:] for a in card.find_all("a", href=True)
                 if a["href"].startswith("tel:")),
                None,
            )
            text = " ".join(card.get_text(" ", strip=True).split())

            self.add(
                raw_address,
                status="coming_soon" if "coming soon" in text.casefold() else "open",
                phone=phone,
                hours=text.split("•")[0].strip() or None,
                fragment=text,
            )
