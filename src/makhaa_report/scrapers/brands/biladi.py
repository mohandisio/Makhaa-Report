"""Biladi Coffee House."""

from ..base import Scraper
from ..extract import drop_tags, innermost_address_texts

class Biladi(Scraper):
    """Biladi Coffee House. Addresses carry a pipe-separated label prefix."""

    slug = "biladi"
    url = "https://biladicoffeehouse.com"
    quiet = True

    def collect(self) -> None:
        soup = self.page(self.url)
        drop_tags(soup, "script", "style", "title")
        for text in innermost_address_texts(soup):
            self.add(text)
