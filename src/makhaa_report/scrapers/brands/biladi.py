"""Biladi Coffee House."""

from ..base import Scraper
from ..extract import drop_tags, innermost_address_texts

URL = "https://biladicoffeehouse.com"


class Biladi(Scraper):
    """Biladi Coffee House. Addresses carry a pipe-separated label prefix."""

    slug = "biladi"
    url = URL
    quiet = True

    def collect(self) -> None:
        soup = self.page(self.url)
        drop_tags(soup, "script", "style", "title")
        for text in innermost_address_texts(soup):
            self.add(text)
