"""House of Mokhah."""

from ..base import Scraper
from ..extract import drop_tags, innermost_address_texts

URL = "https://www.houseofmokhaycc.com/cafes"


class HouseOfMokhah(Scraper):
    """House of Mokhah.

    The cafes page announces a further location in prose with no address,
    so only the trading store is captured.
    """

    slug = "house_of_mokhah"
    url = URL
    quiet = True

    def collect(self) -> None:
        soup = self.page(self.url)
        drop_tags(soup, "script", "style", "title")
        for text in innermost_address_texts(soup):
            self.add(text)
