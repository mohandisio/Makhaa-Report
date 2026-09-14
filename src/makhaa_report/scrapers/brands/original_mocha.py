"""Original Mocha."""

from ..base import Scraper
from ..extract import LOOKS_LIKE_ADDRESS, drop_tags, one_line
from ...normalize import US_STATE_NAMES


class OriginalMocha(Scraper):
    """Original Mocha.

    One page per store, discovered from the home page by slug. Each page
    carries a single address; the site publishes no coordinates.
    """

    slug = "original_mocha"
    url = "https://originalmocha.com"
    quiet = True

    def _store_pages(self) -> list[str]:
        """Find store pages by their slug.

        The sitemap omits them and the home page carries no address, but
        each store has its own page slugged city-then-state
        ("/murphy-texas/", "/tinley-park-illinois/"). Matching the
        trailing state name finds new stores without fetching every page
        on the site.
        """
        soup = self.page(self.url)
        pages = set()
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if not href.startswith(self.url):
                continue
            slug = href[len(self.url) :].strip("/")
            if not slug or "/" in slug:
                continue
            words = slug.replace("-", " ")
            if any(words.endswith(state) for state in US_STATE_NAMES):
                pages.add(href)
        return sorted(pages)

    def collect(self) -> None:
        for url in self._store_pages():
            soup = self.page(url)
            drop_tags(soup, "script", "style")
            for node in soup.find_all(string=LOOKS_LIKE_ADDRESS):
                raw_address = one_line(str(node))
                if self.add(raw_address, source_url=url, fragment=raw_address):
                    break
