"""Delah Coffee."""

from ..base import Scraper
from ..extract import drop_tags, place_coords, text


class Delah(Scraper):
    """Delah Coffee.

    Built with Elementor, so the per-store blocks carry no usable classes
    and two of them are rendered inside embedded Google widgets. The icon
    list is the one consistent listing: an entry per store reading
    "City: address", alongside phone, email and social entries that carry
    no address and are skipped.

    The page announces no stores, so every row is recorded as open.
    """

    slug = "delah"
    url = "https://delahcoffee.com/locations/"
    quiet = True

    def collect(self) -> None:
        soup = self.page(self.url)
        drop_tags(soup, "script", "style")

        for entry in soup.select("span.elementor-icon-list-text"):
            line = text(entry)
            _, _, remainder = line.partition(":")

            link = entry.find_parent("a") or entry.find_previous("a")
            href = link.get("href") if link else None

            self.add(
                remainder.strip(),
                status="open",
                coords=place_coords(href) if href else None,
                source_url=href,
                fragment=line,
            )
