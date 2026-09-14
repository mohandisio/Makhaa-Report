"""Yemerica Coffee."""

from ..base import Scraper
from ..extract import drop_tags, innermost_address_texts


class Yemerica(Scraper):
    """Yemerica Coffee.

    `/locations` lists one open flagship (West Hartford, CT) plus several
    "coming soon" cards for future New England markets — each announced
    only with a bare state name ("Connecticut", "Massachusetts", "Rhode
    Island"), never a street. A text scan naturally skips those: they
    never contain a two-letter state code plus ZIP, so they never look
    like an address in the first place. The flagship's full street,
    city, state and ZIP appear together only in the footer contact
    block; the location card itself omits the state and ZIP, so scanning
    the whole page (rather than just the card grid) is what turns up a
    row at all.
    """

    slug = "yemerica"
    url = "https://yemericacoffee.com/locations"
    quiet = True

    def collect(self) -> None:
        soup = self.page(self.url)
        drop_tags(soup, "script", "style", "title")
        for candidate in innermost_address_texts(soup):
            self.add(candidate)
