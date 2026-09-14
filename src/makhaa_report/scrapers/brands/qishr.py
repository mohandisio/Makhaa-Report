"""Qishr Coffee House."""

from ..base import Scraper
from ..extract import drop_tags, innermost_address_texts


class Qishr(Scraper):
    """Qishr Coffee House.

    No store list — the single cafe's address sits in a plain
    server-rendered `.loc-block` on the home page, alongside a sibling
    block for hours that has no ZIP-shaped text and so is skipped
    without a warning. The site used to be a Vite SPA whose address was
    inlined in the JS bundle; it has since been rebuilt as static HTML.

    The unit is written as a bare "#140" set off from the street by a
    comma ("90 Skyport Dr, #140"), which the shared address splitter
    reads as a city-side unit only when a marker word precedes it, not
    a comma. Turning that comma into a space keeps the unit on the
    street where it belongs.
    """

    slug = "qishr"
    url = "https://qishrcoffeehouse.co"
    quiet = True

    def collect(self) -> None:
        soup = self.page(self.url)
        drop_tags(soup, "script", "style", "title")
        for text in innermost_address_texts(soup):
            self.add(text.replace(", #", " #"))
