"""Mocha Point Coffee."""

from ..base import Scraper
from ..extract import drop_tags, innermost_address_texts


class MochaPoint(Scraper):
    """Mocha Point Coffee.

    Elementor page with no stable classes — each heading's class is a
    fresh hash regenerated per edit — so there is no selector worth
    writing; the address is read as plain text off the /locations/ page
    instead. A second unit, "Kansas", is listed only as a nav dropdown
    item linking out to an Instagram profile; the site publishes no
    street address for it anywhere, so it never produces a row here.

    No coming-soon marker, phone, hours, or map embed is published on
    the pages this scraper reads.
    """

    slug = "mocha_point"
    url = "https://mochapointcoffee.com/locations/"
    quiet = True

    def collect(self) -> None:
        soup = self.page(self.url)
        drop_tags(soup, "script", "style", "title")
        for text in innermost_address_texts(soup):
            self.add(text)
