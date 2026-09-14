"""MOKAFÉ."""

from ..base import Scraper
from ..extract import LOOKS_LIKE_ADDRESS, drop_tags, one_line


class Mokafe(Scraper):
    """MOKAFÉ.

    Each store is a single bold line combining name and address, split
    either side of a colon, or of the bullet when no colon is present.

    This scraper reports what the site claims. Which of these storefronts
    trade as MOKAFÉ has been disputed by earlier research, and no scrape
    settles that — verify by hand before publishing the count.
    """

    # MOKAFÉ (mymokafe.com) is a different company from Moka & Co
    # (mokanco.com). Both stay in the registry; never merge them.
    slug = "mokafe"
    url = "https://mymokafe.com/pages/locations"

    def collect(self) -> None:
        soup = self.page(self.url)
        drop_tags(soup, "script", "style")

        for node in soup.find_all(string=LOOKS_LIKE_ADDRESS):
            line = one_line(str(node))
            separator = ":" if ":" in line else "•"
            _, _, remainder = line.partition(separator)

            self.add(remainder.strip(), fragment=line)
