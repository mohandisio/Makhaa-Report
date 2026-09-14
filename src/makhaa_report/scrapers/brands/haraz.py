"""Haraz Coffee House."""

from ..base import Scraper
from ..extract import place_coords

# The all-states summary page is stale; the per-state pages are current.
_SUMMARY_SLUG = "locations-and-hours"


class Haraz(Scraper):
    """Haraz Coffee House.

    One page per state, each holding a card per store: heading, address,
    and a Google Maps link the coordinates come from. Card headings are
    not reliable — a Pearland store is headed "Plano" — so the address is
    the identity.

    The per-state pages carry no coming-soon markers; Haraz's announced
    pipeline is published elsewhere and is not visible to this scraper.
    """

    slug = "haraz"
    url = "https://harazcoffeehouse.com/sitemap.xml"

    def _state_pages(self) -> list[str]:
        """Discover the per-state locator pages from the sitemap.

        Read rather than hardcoded: Haraz adds states, and a fixed list
        would keep scraping happily while silently missing every store in
        a new one.
        """
        index = self.page(self.url, parser="xml")
        pages_sitemap = next(
            (loc.text for loc in index.find_all("loc") if "sitemap_pages" in loc.text),
            None,
        )
        if pages_sitemap is None:
            raise ValueError("haraz: sitemap index has no pages sitemap")

        pages = self.page(pages_sitemap, parser="xml")
        return sorted(
            loc.text
            for loc in pages.find_all("loc")
            if loc.text.rstrip("/").endswith("-locations")
            and _SUMMARY_SLUG not in loc.text
        )

    def collect(self) -> None:
        for url in self._state_pages():
            soup = self.page(url)
            for card in soup.select("li.multicolumn-list__item .multicolumn-card__info"):
                paragraph = card.select_one(".rte p")
                if paragraph is None:
                    continue
                raw_address = " ".join(paragraph.get_text(" ", strip=True).split())

                link = card.find("a", href=True)
                coords = place_coords(link["href"]) if link else None
                text = card.get_text(" ", strip=True).casefold()

                self.add(
                    raw_address,
                    status="coming_soon" if "coming soon" in text else "open",
                    coords=coords,
                    source_url=url,
                    fragment=" ".join(card.get_text(" ", strip=True).split()),
                )
