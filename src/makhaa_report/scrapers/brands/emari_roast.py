"""Emari Roast Cafe."""

from ..base import Scraper
from ..extract import drop_tags, innermost_address_texts


class EmariRoast(Scraper):
    """Emari Roast Cafe.

    A server-rendered Next.js `/locations` page: one "Now Open" card
    carrying a full street address, followed by "Coming Soon" teaser
    cards that name only a city and state (New York, Dallas TX,
    Chicago IL) with no street line. A teaser never contains a
    state-plus-ZIP pair, so it never looks like an address in the first
    place — no coming-soon wording to filter on, and nothing here to
    warn about.
    """

    slug = "emari_roast"
    url = "https://emariroastcafe.com/locations"
    quiet = True

    def collect(self) -> None:
        soup = self.page(self.url)
        drop_tags(soup, "script", "style")
        for text in innermost_address_texts(soup):
            self.add(text)
