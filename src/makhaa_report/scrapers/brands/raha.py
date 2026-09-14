"""Raha Coffee House."""

from ..base import Scraper
from ..extract import drop_tags, innermost_address_texts


class Raha(Scraper):
    """Raha Coffee House.

    A single-cafe site, not a chain: the home page has no locator at all,
    just its one Buffalo address in plain text inside an Elementor
    "Visit Our Cafe" widget, repeated again in the site-wide footer's
    "Contact Info" widget. Both hits parse to the same store and collapse
    to one row through the base class's dedupe.

    `/shops/` is a WooCommerce product catalog, not a store locator — it
    has no locations/stores/find/visit nav link and is never fetched here.
    The site publishes no coordinates (its Google Maps link is a short
    redirect, not a place link with embedded lat/lon) and no ld+json
    business listing.
    """

    slug = "raha"
    url = "https://rahacoffeehouse.com/"
    quiet = True

    def collect(self) -> None:
        soup = self.page(self.url)
        drop_tags(soup, "script", "style", "title")
        for text in innermost_address_texts(soup):
            self.add(text)
