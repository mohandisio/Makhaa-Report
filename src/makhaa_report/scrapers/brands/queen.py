"""Queen Yemeni Coffee."""

from ..base import Scraper
from ..extract import drop_tags, innermost_address_texts

URL = "https://queencoffeehouse.com"


class Queen(Scraper):
    """Queen Yemeni Coffee. Addresses use a middot between street and city."""

    slug = "queen"
    url = URL
    quiet = True

    def collect(self) -> None:
        soup = self.page(self.url)
        drop_tags(soup, "script", "style", "title")
        for text in innermost_address_texts(soup):
            self.add(text)
