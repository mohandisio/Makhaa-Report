"""Yafa (yafabrooklyn.com) — a Brooklyn cafe, not the unrelated Oakland
business also trading as "Yafa Coffee"."""

import re

from ..base import Scraper
from ..extract import LOOKS_LIKE_ADDRESS, drop_tags

_MAPS_LINK = re.compile(r"maps\.app\.goo\.gl")

# The two neighborhoods are the only city this Brooklyn-only business
# has; a card publishes its street but never its city or state, so this
# is the fallback for the store that has no zip either.
_CITY_STATE = "Brooklyn, NY"


class Yafa(Scraper):
    """Yafa.

    The /locations page renders one heading per store as a Google Maps
    place link — "Sunset Park<br>4415 4th Ave" — with no city, state or
    ZIP alongside it, plus a photo tile linking to the same map pin with
    no text of its own. The sitewide footer, also present on this page,
    repeats the flagship's full mailing address including its ZIP; that
    is the only place a ZIP appears anywhere on the site, so Downtown
    Brooklyn (505 State St., in the Alloy Building) is recorded without
    one. A sitewide ld+json `LocalBusiness` block also names only the
    flagship and is not read here — using it as the location list would
    silently drop Downtown Brooklyn.

    The page carries no coming-soon wording, so every row is open.
    """

    slug = "yafa"
    url = "https://yafabrooklyn.com/locations"

    def collect(self) -> None:
        soup = self.page(self.url)
        drop_tags(soup, "script", "style")

        full_addresses: dict[str, str] = {}
        cards: list[tuple[str, str]] = []
        for anchor in soup.find_all("a", href=_MAPS_LINK):
            lines = anchor.get_text("\n", strip=True).split("\n")
            if len(lines) != 2:
                continue
            first, second = lines
            if LOOKS_LIKE_ADDRESS.search(second):
                # The footer's own entry: "street" / "city, state zip".
                full_addresses[first.casefold()] = second
            else:
                # A location card: "neighborhood" / "street".
                cards.append((first, second))

        for name, street in cards:
            tail = full_addresses.get(street.casefold(), _CITY_STATE)
            self.add(f"{street}, {tail}", fragment=f"{name}: {street}")
