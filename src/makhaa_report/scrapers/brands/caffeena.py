"""Caffeena Coffee House."""

from ..base import Scraper
from ..extract import LOOKS_LIKE_ADDRESS, drop_tags, one_line

_HEADINGS = ["h1", "h2", "h3"]


def _caffeena_status(node) -> str:
    """Which section an address sits under.

    Caffeena splits the page into "Now Open Locations" and "Coming Soon
    Locations", with a per-store heading under each; walking back to the
    nearest section heading is what tells the two apart.
    """
    heading = node
    while True:
        heading = heading.find_previous(_HEADINGS)
        if heading is None:
            return "unknown"
        heading_text = heading.get_text(" ", strip=True).casefold()
        if "coming soon" in heading_text:
            return "coming_soon"
        if "now open" in heading_text:
            return "open"


class Caffeena(Scraper):
    """Caffeena Coffee House.

    Addresses sit in plain paragraphs under a per-store heading, split
    across a now-open and a coming-soon section. The site publishes
    neither coordinates nor phone numbers.
    """

    slug = "caffeena"
    url = "https://caffeena.com/locations"
    quiet = True

    def collect(self) -> None:
        soup = self.page(self.url)
        drop_tags(soup, "script", "style")

        for node in soup.find_all(string=LOOKS_LIKE_ADDRESS):
            raw = one_line(str(node))
            self.add(raw, status=_caffeena_status(node.parent))
