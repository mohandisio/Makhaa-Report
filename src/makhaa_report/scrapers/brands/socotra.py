"""Socotra Coffee House."""

from ..base import Scraper
from ..extract import LOOKS_LIKE_ADDRESS, drop_tags, one_line

URL = "https://socotracoffeehouse.framer.website"


class Socotra(Scraper):
    """Socotra Coffee House.

    Framer, but server-rendered: the single cafe's address sits whole
    inside a map link.
    """

    slug = "socotra"
    url = URL
    quiet = True

    def collect(self) -> None:
        soup = self.page(self.url)
        drop_tags(soup, "script", "style")
        for node in soup.find_all(string=LOOKS_LIKE_ADDRESS):
            self.add(one_line(str(node)))
