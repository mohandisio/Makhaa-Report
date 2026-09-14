"""Moka & Co."""

from ..base import Scraper
from ..extract import text


class MokaAndCo(Scraper):
    """Moka & Co.

    One WordPress query block per store: title links to the store page,
    an excerpt holds the address, and a "Coming Soon" term marks the
    pipeline. The corporate contact block in the mobile menu carries HQ
    addresses that are not stores, so only post blocks are read.

    The listing repeats a store when it belongs to more than one grouping;
    the first entry for an address wins.
    """

    slug = "moka_and_co"
    # /pages/locations redirects here. Store detail pages live at
    # mokanco.com/<slug>/, but every address is already on this page, so
    # scraping the detail pages too would double-count.
    url = "https://mokanco.com/locations/"

    def collect(self) -> None:
        soup = self.page(self.url)

        for post in soup.select("li.wp-block-post"):
            excerpt = post.select_one("p.wp-block-post-excerpt__excerpt")
            if excerpt is None:
                continue
            raw_address = text(excerpt, "")

            title = post.select_one("h6.wp-block-post-title")
            link = title.find("a") if title else None
            terms = [
                t.get_text(strip=True).casefold()
                for t in post.select(".wp-block-post-terms a")
            ]

            self.add(
                raw_address,
                status="coming_soon" if "coming soon" in terms else "open",
                source_url=link["href"] if link and link.get("href") else self.url,
                fragment=text(post),
            )
